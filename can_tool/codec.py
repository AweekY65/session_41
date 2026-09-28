"""Signal and frame encode/decode over fixed, local byte buffers.

No I/O of any kind happens here: a frame is a plain ``bytes`` object that
the caller stores in memory or writes to a local file themselves.
"""

import math

from .errors import EncodeError, DecodeError
from .parser import _bit_positions

# Floating-point tolerance shared by range/quantization checks.
_QUANT_ABS_TOL = 1e-9
_QUANT_REL_TOL = 1e-9


# ---------------------------------------------------------------------
# raw <-> physical
# ---------------------------------------------------------------------

def raw_to_physical(signal, raw):
    """``physical = raw * scale + offset``."""
    return raw * signal.scale + signal.offset


def physical_to_raw(signal, value):
    """Convert a physical value to the integer raw value.

    Raises :class:`EncodeError` when the value is NaN/infinite, does not
    land on the signal's quantization grid, or exceeds the raw bit span
    / the DBC ``[min|max]`` limits.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EncodeError(
            f"signal {signal.name!r}: value must be a number, got "
            f"{type(value).__name__}"
        )
    if math.isnan(value) or math.isinf(value):
        raise EncodeError(f"signal {signal.name!r}: value must be finite")

    raw_float = (value - signal.offset) / signal.scale
    raw = int(round(raw_float))

    # Explicit DBC [min|max] bounds are checked before quantization:
    # a value past the declared limit should report that, not a grid error.
    if signal.minimum is not None and value < signal.minimum - _QUANT_ABS_TOL:
        raise EncodeError(
            f"signal {signal.name!r}: value {value:g} below DBC minimum "
            f"{signal.minimum:g}"
        )
    if signal.maximum is not None and value > signal.maximum + _QUANT_ABS_TOL:
        raise EncodeError(
            f"signal {signal.name!r}: value {value:g} above DBC maximum "
            f"{signal.maximum:g}"
        )

    # Raw bit span.
    if not signal.raw_min <= raw <= signal.raw_max:
        lo, hi = signal.physical_range()
        raise EncodeError(
            f"signal {signal.name!r}: raw value {raw} (physical {value}) "
            f"is outside the {signal.length}-bit "
            f"{'signed' if signal.signed else 'unsigned'} range "
            f"[{signal.raw_min}, {signal.raw_max}]; physical range is "
            f"[{lo:g}, {hi:g}]"
        )

    # Grid check: the rounded raw value must reproduce the requested
    # physical value within a relative floating-point tolerance.
    recovered = raw_to_physical(signal, raw)
    tol = _QUANT_ABS_TOL + _QUANT_REL_TOL * abs(value)
    if abs(recovered - value) > tol:
        raise EncodeError(
            f"signal {signal.name!r}: physical value {value} cannot be "
            f"exactly represented (scale={signal.scale:g}, "
            f"offset={signal.offset:g}); nearest raw {raw} gives "
            f"{recovered:g}"
        )

    return raw


# ---------------------------------------------------------------------
# single signal bit operations (used directly by the tests)
# ---------------------------------------------------------------------

def decode_signal(signal, data):
    """Return the unsigned/signed raw integer of one signal in ``data``."""
    raw = 0
    for k, (byte, bit) in enumerate(_bit_positions(signal)):
        if byte >= len(data):
            raise DecodeError(
                f"signal {signal.name!r}: needs byte {byte} but payload "
                f"only has {len(data)} bytes"
            )
        if data[byte] & (1 << bit):
            raw |= 1 << k
    if signal.signed and raw & (1 << (signal.length - 1)):
        raw -= 1 << signal.length
    return raw


def encode_signal(signal, value, payload=None):
    """Encode one physical value into a fresh payload (or a given bytearray).

    Returns the payload. Existing bits occupied by the signal are
    overwritten; all other bits are left untouched.
    """
    if payload is None:
        # Conservative: one byte per bit position we touch.
        max_byte = max(b for b, _ in _bit_positions(signal))
        payload = bytearray(max_byte + 1)
    raw = value.value if isinstance(value, Raw) else physical_to_raw(signal, value)
    for k, (byte, bit) in enumerate(_bit_positions(signal)):
        if byte >= len(payload):
            raise EncodeError(
                f"signal {signal.name!r}: bit at byte {byte} exceeds "
                f"payload length {len(payload)}"
            )
        mask = 1 << bit
        if (raw >> k) & 1:
            payload[byte] |= mask
        else:
            payload[byte] &= ~mask
    return payload


class Raw:
    """Wrapper that lets :func:`encode_signal`/``encode_frame`` take a raw
    integer instead of a physical value (handy for multiplexor switches)."""

    __slots__ = ("value",)

    def __init__(self, value):
        self.value = int(value)


# ---------------------------------------------------------------------
# whole frames
# ---------------------------------------------------------------------

def _resolve_message(db, name_or_id):
    if isinstance(name_or_id, int):
        try:
            return db.get_message_by_id(name_or_id)
        except KeyError:
            raise DecodeError(
                f"no message with id 0x{name_or_id & 0x1FFFFFFF:X} in database"
            )
    try:
        return db.get_message_by_name(name_or_id)
    except KeyError:
        raise EncodeError(f"no message named {name_or_id!r} in database")


def encode_frame(db, name_or_id, values, strict=True):
    """Encode physical signal values into a CAN payload (``bytes``).

    ``values`` maps signal name -> physical value. For multiplexed
    messages the multiplexor value selects the active signal set; the
    switch may be supplied either as a physical value or wrapped with
    :class:`Raw` to force a raw integer.

    With ``strict=True`` (default) every signal active for the selected
    multiplexor value must be given, and signals that are inactive for
    it are rejected.
    """
    msg = _resolve_message(db, name_or_id)
    values = dict(values)
    payload = bytearray(msg.dlc)

    muxor = msg.multiplexor
    mux_raw = None
    if muxor is not None:
        if muxor.name not in values:
            raise EncodeError(
                f"message {msg.name!r}: multiplexor signal "
                f"{muxor.name!r} is required"
            )
        mux_raw = _as_raw(muxor, values.pop(muxor.name))
        if not muxor.raw_min <= mux_raw <= muxor.raw_max:
            raise EncodeError(
                f"message {msg.name!r}: multiplexor raw value {mux_raw} "
                f"outside {muxor.raw_min}..{muxor.raw_max}"
            )

    active = []
    for sig in msg.signals:
        if sig is muxor:
            continue
        if sig.is_multiplexed:
            if not sig.matches_mux_value(mux_raw):
                if strict and sig.name in values:
                    raise EncodeError(
                        f"message {msg.name!r}: signal {sig.name!r} "
                        f"({sig.mux_label()}) is not active for multiplexor "
                        f"raw value {mux_raw}"
                    )
                continue
            active.append(sig)
        else:
            active.append(sig)

    if strict:
        extra = set(values) - {s.name for s in active}
        if extra:
            raise EncodeError(
                f"message {msg.name!r}: unknown or inactive signal(s): "
                f"{sorted(extra)}"
            )
        missing = [s.name for s in active if s.name not in values]
        if missing:
            raise EncodeError(
                f"message {msg.name!r}: missing value(s) for active "
                f"signal(s): {missing}"
            )

    if muxor is not None:
        _write_raw(muxor, mux_raw, payload)
    for sig in active:
        given = values.get(sig.name)
        if given is None and not strict:
            continue
        raw = _as_raw(sig, given)
        _write_raw(sig, raw, payload)

    return bytes(payload)


def _as_raw(signal, value):
    if isinstance(value, Raw):
        raw = value.value
        if not signal.raw_min <= raw <= signal.raw_max:
            raise EncodeError(
                f"signal {signal.name!r}: raw value {raw} outside "
                f"{signal.raw_min}..{signal.raw_max}"
            )
        return raw
    return physical_to_raw(signal, value)


def _write_raw(signal, raw, payload):
    for k, (byte, bit) in enumerate(_bit_positions(signal)):
        if byte >= len(payload):
            raise EncodeError(
                f"signal {signal.name!r}: bit at byte {byte} exceeds DLC "
                f"{len(payload)}"
            )
        mask = 1 << bit
        if (raw >> k) & 1:
            payload[byte] |= mask
        else:
            payload[byte] &= ~mask


def decode_frame(db, frame_id, data, strict=True):
    """Decode a raw payload into ``{signal_name: physical_value}``.

    With ``strict=True`` the payload length must equal the message DLC
    and the frame id must exist in the database. Only signals active for
    the multiplexor value are decoded/returned.
    """
    return decode_frame_raw(db, frame_id, data, strict=strict)[0]


def decode_frame_raw(db, frame_id, data, strict=True):
    """Like :func:`decode_frame` but return ``(physical, raw)`` dicts."""
    if isinstance(data, str):
        data = bytes.fromhex(data)
    data = bytes(data)

    try:
        msg = db.get_message_by_id(frame_id)
    except KeyError:
        raise DecodeError(
            f"no message with id 0x{frame_id & 0x1FFFFFFF:X} in database"
        )

    if strict and len(data) != msg.dlc:
        raise DecodeError(
            f"message {msg.name!r}: DLC mismatch, frame carries "
            f"{len(data)} bytes but DBC declares {msg.dlc}"
        )
    if len(data) > 8:
        raise DecodeError(
            f"message {msg.name!r}: frame of {len(data)} bytes exceeds "
            f"classic CAN 8-byte payload"
        )

    physical, raw_values = {}, {}
    mux_raw = None
    muxor = msg.multiplexor
    if muxor is not None:
        mux_raw = decode_signal(muxor, data)
        physical[muxor.name] = raw_to_physical(muxor, mux_raw)
        raw_values[muxor.name] = mux_raw

    for sig in msg.signals:
        if sig is muxor:
            continue
        if sig.is_multiplexed and not sig.matches_mux_value(mux_raw):
            continue
        raw = decode_signal(sig, data)
        raw_values[sig.name] = raw
        physical[sig.name] = raw_to_physical(sig, raw)

    return physical, raw_values
