"""Core signal encode/decode on raw CAN payloads.

All operations are local: payloads are ``bytes``/``bytearray`` and no I/O
of any kind happens here.

Wire layout recap (see :mod:`can_dbc.layout`): bit position ``p`` is
``byte p//8``, bit ``p%8`` inside that byte (LSB = 0).  Each signal knows
its positions ordered MSB-first, so packing/unpacking is a simple bit
walk independent of endianness.
"""

from __future__ import annotations

import math
from typing import Mapping

from .errors import DlcError, EncodeError, DecodeError
from .model import Database, Message, Signal


# ----------------------------------------------------------------------
# bit-level primitives
# ----------------------------------------------------------------------
def _extract_raw(payload: bytes, sig: Signal) -> int:
    value = 0
    for wire_bit in sig.bit_positions:           # MSB first
        value = (value << 1) | (
            (payload[wire_bit >> 3] >> (wire_bit & 7)) & 1
        )
    if sig.signed:
        sign_bit = 1 << (sig.length - 1)
        if value & sign_bit:
            value -= 1 << sig.length
    return value


def _inject_raw(buf: bytearray, sig: Signal, raw: int) -> None:
    length = sig.length
    # Normalize negative values to their two's-complement bit pattern.
    if raw < 0:
        raw += 1 << length
    for i, wire_bit in enumerate(sig.bit_positions):  # MSB first
        bit = (raw >> (length - 1 - i)) & 1
        byte, bit_in_byte = wire_bit >> 3, wire_bit & 7
        if bit:
            buf[byte] |= 1 << bit_in_byte
        else:
            buf[byte] &= ~(1 << bit_in_byte)


def _check_raw_range(sig: Signal, raw: int) -> None:
    if not isinstance(raw, int):
        raise EncodeError(
            f"signal {sig.name!r}: raw value must be int, got "
            f"{type(raw).__name__}"
        )
    if not (sig.raw_min <= raw <= sig.raw_max):
        raise EncodeError(
            f"signal {sig.name!r}: raw value {raw} outside "
            f"[{sig.raw_min}, {sig.raw_max}] for {sig.length}-bit "
            f"{'signed' if sig.signed else 'unsigned'} signal"
        )


# ----------------------------------------------------------------------
# raw (integer) interface
# ----------------------------------------------------------------------
def decode_raw(payload: bytes, message: Message) -> dict[str, int]:
    """Decode a payload to ``{signal_name: raw_integer}``.

    Multiplexed branches are selected by first decoding every switch
    signal, then including only branch signals whose dependency matches.
    """
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise DecodeError("payload must be bytes-like")
    if len(payload) != message.dlc:
        raise DlcError(
            f"message {message.name!r}: payload is {len(payload)} bytes "
            f"but DBC DLC is {message.dlc}"
        )

    payload = bytes(payload)
    switch_values: dict[str, int] = {}
    result: dict[str, int] = {}

    # switches are always present
    for sig in message.signals:
        if sig.is_switch:
            switch_values[sig.name] = _extract_raw(payload, sig)

    for sig in message.signals:
        if sig.is_multiplexed:
            if not all(
                switch_values.get(switch) == value
                for switch, value in sig.mux_dependencies
            ):
                continue
        result[sig.name] = _extract_raw(payload, sig)

    return result


def encode_raw(raw_values: Mapping[str, int], message: Message) -> bytes:
    """Pack raw integer signal values into a zero-initialized payload.

    Only signals relevant to the selected multiplexer branch need be
    present; the switch value is taken from the inputs as usual.
    """
    buf = bytearray(message.dlc)
    provided = dict(raw_values)

    unknown = set(provided) - {s.name for s in message.signals}
    if unknown:
        raise EncodeError(
            f"message {message.name!r}: unknown signal(s): {sorted(unknown)}"
        )

    # Validate branch consistency before touching the buffer.
    for sig in message.signals:
        if sig.name not in provided:
            continue
        if sig.is_multiplexed:
            for switch_name, required in sig.mux_dependencies:
                if switch_name in provided and provided[switch_name] != required:
                    raise EncodeError(
                        f"signal {sig.name!r} belongs to multiplexer branch "
                        f"{switch_name}={required} but provided switch value "
                        f"is {provided[switch_name]}"
                    )

    for sig in message.signals:
        if sig.name not in provided:
            continue
        if sig.is_multiplexed:
            # Skip silently when the governing switch value was not given;
            # the caller is simply not encoding that branch.
            if sig.mux_dependencies[0][0] not in provided:
                continue
        raw = provided[sig.name]
        _check_raw_range(sig, raw)
        _inject_raw(buf, sig, raw)

    return bytes(buf)


# ----------------------------------------------------------------------
# physical (scaled) interface
# ----------------------------------------------------------------------
def decode(
    payload: bytes,
    message: Message | Database,
    frame_id: int | None = None,
) -> dict[str, float]:
    """Decode to ``{signal_name: physical_value}`` applying scale/offset.

    Pass either a :class:`Message` or a :class:`Database` plus ``frame_id``.
    """
    msg = _resolve_message(message, frame_id)
    raws = decode_raw(payload, msg)
    return {
        name: msg.signal(name).raw_to_physical(raw)
        for name, raw in raws.items()
    }


def encode(
    values: Mapping[str, float],
    message: Message | Database,
    frame_id: int | None = None,
    *,
    strict: bool = True,
) -> bytes:
    """Encode physical signal values to a CAN payload.

    :param values: mapping signal name -> physical value.
    :param message: target message, or a database with ``frame_id``.
    :param strict: when True (default), a physical value that does not map
        to an integral raw value raises :class:`EncodeError`; otherwise the
        nearest representable raw value is used.
    :raises EncodeError: unknown signal, out-of-range value, or
        non-representable value under strict mode.
    """
    msg = _resolve_message(message, frame_id)
    raws: dict[str, int] = {}
    selected: set[str] = set()

    for name, value in values.items():
        try:
            sig = msg.signal(name)
        except KeyError:
            raise EncodeError(
                f"message {msg.name!r}: unknown signal {name!r}"
            ) from None
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise EncodeError(
                f"signal {name!r}: physical value must be finite, got {value}"
            )

        exact = (value - sig.offset) / sig.scale
        candidate = round(exact)
        if strict and exact != candidate:
            raise EncodeError(
                f"signal {name!r}: physical value {value:.10g} is not "
                f"representable: ({value:.10g} - {sig.offset:.10g}) / "
                f"{sig.scale:.10g} = {exact:.10g}, not an integer "
                f"(nearest raw is {candidate})"
            )
        raw = candidate
        if not (sig.raw_min <= raw <= sig.raw_max):
            raise EncodeError(
                f"signal {name!r}: physical value {_fmt(value)} maps to raw "
                f"{raw}, outside [{sig.raw_min}, {sig.raw_max}] "
                f"(physical range "
                f"[{_fmt(sig.physical_min)}, {_fmt(sig.physical_max)}])"
            )
        raws[name] = raw
        selected.add(name)

    # multiplexer branch consistency (same checks as encode_raw)
    for name in selected:
        sig = msg.signal(name)
        if sig.is_multiplexed:
            for switch_name, required in sig.mux_dependencies:
                if switch_name in raws and raws[switch_name] != required:
                    raise EncodeError(
                        f"signal {name!r} belongs to multiplexer branch "
                        f"{switch_name}={required} but switch value given "
                        f"is {raws[switch_name]}"
                    )

    return encode_raw(raws, msg)


def _fmt(value: float) -> str:
    """Format a physical bound without losing trailing precision."""
    text = f"{value:.10g}"
    return text


def _resolve_message(
    message: Message | Database, frame_id: int | None
) -> Message:
    if isinstance(message, Message):
        return message
    if frame_id is None:
        raise ValueError("frame_id is required when passing a Database")
    try:
        return message.by_id(frame_id)
    except KeyError:
        raise DecodeError(
            f"database contains no message with id 0x{frame_id:X}"
        ) from None
