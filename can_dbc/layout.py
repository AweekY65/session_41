"""Bit-layout math: map a DBC signal onto CAN payload wire positions.

Numbering conventions (DBC / Vector style)
------------------------------------------

* A CAN frame payload is ``dlc`` bytes.  This module numbers *wire* bits
  linearly as ``wire = byte_index * 8 + bit_index_in_byte`` where
  ``bit_index_in_byte`` counts from the byte's LSB (bit 0)::

      byte 0: wire  7  6  5  4  3  2  1  0
      byte 1: wire 15 14 13 12 11 10  9  8
      ...

* DBC start bits use the same numeric space ("sawtooth" numbering in
  CANdb editors): within byte B the MSB is 8B+7 and the LSB is 8B.  The
  name refers to how a big-endian field walks through that space; the
  number itself is identical to the linear wire bit.

* Intel / little-endian signals (``@1``): the DBC start bit numbers the
  signal's **LSB**.  Remaining bits are laid out upward in wire space
  (low wire bit = least-significant value bit), crossing byte boundaries
  at multiples of 8.

* Motorola / big-endian signals (``@0``): the DBC start bit numbers the
  signal's **MSB**, which always lies in the field's lowest-numbered
  byte.  From the MSB each following value bit walks one sawtooth
  position down (MSB -> ... -> LSB within a byte); after a byte's LSB
  (number 8B) the next bit wraps to the *following* byte's MSB (8B+15),
  not the previous byte.  The returned list is MSB-first; for example
  ``11|12@0`` maps to wire bits ``[11,10,9,8, 23..16]``.
"""

from .errors import BitOutOfBoundsError

#: signals are at most 64 bits wide (Classic/CAN-FD payload max)
MAX_SIGNAL_LENGTH = 64


def signal_bit_positions(start: int, length: int, byte_order: str) -> list[int]:
    """Return the linear wire bits a signal occupies, MSB-first.

    :param start: the DBC start bit (sawtooth numbering).
    :param length: signal width in bits.
    :param byte_order: ``"intel"``/``"little_endian"`` or
        ``"motorola"``/``"big_endian"``.
    :returns: wire bit positions, ordered from the value MSB to LSB.
    :raises ValueError: for a bad byte order or non-positive length.
    """
    if length <= 0:
        raise ValueError(f"signal length must be positive, got {length}")
    if start < 0:
        raise ValueError(f"start bit must be >= 0, got {start}")

    bo = byte_order.lower()
    if bo in ("intel", "little_endian", "little"):
        # start numbers the LSB; bits then run upward in wire space.
        return [start + (length - 1 - i) for i in range(length)]

    if bo in ("motorola", "big_endian", "big"):
        # Walk sawtooth positions from MSB to LSB.  Sawtooth and wire
        # numbers coincide numerically; the Motorola quirk is purely the
        # order: after a byte's LSB (8B) the next bit wraps to the
        # following byte's MSB (8B+15), not to the previous byte.
        positions = []
        saw = start
        for i in range(length):
            positions.append(saw)
            if i == length - 1:
                break
            saw -= 1
            if saw % 8 == 7:  # decrement crossed a byte boundary
                saw += 16
        return positions

    raise ValueError(f"unknown byte order: {byte_order!r}")


def ensure_in_bounds(positions, dlc: int, signal_name: str) -> None:
    """Raise :class:`BitOutOfBoundsError` if any bit exceeds the DLC."""
    max_bit = dlc * 8 - 1
    for wire_bit in positions:
        if wire_bit < 0 or wire_bit > max_bit:
            byte_index = wire_bit // 8
            raise BitOutOfBoundsError(
                f"signal {signal_name!r} reaches byte {byte_index} "
                f"(wire bit {wire_bit}) but message DLC is only {dlc} "
                f"bytes (bits 0..{max_bit})"
            )


def find_overlap(groups):
    """Check bit overlap within groups of simultaneously-active signals.

    :param groups: iterable of ``(label, signals)`` pairs.  Signals in
        different groups are never compared (used for multiplexed branches
        that can never be present in the same frame).  ``label`` is only
        used to build a readable error message.
    :returns: a tuple ``(name_a, name_b, wire_bit, label)`` for the first
        overlap found, or ``None``.
    """
    for label, signals in groups:
        owner: dict[int, str] = {}
        for sig in signals:
            for wire_bit in sig.bit_positions:
                previous = owner.get(wire_bit)
                if previous is not None and previous != sig.name:
                    return previous, sig.name, wire_bit, label
                owner[wire_bit] = sig.name
    return None
