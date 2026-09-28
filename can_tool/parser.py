"""DBC text parser.

Implements, locally and with no third-party dependency, the subset of the
DBC grammar needed for message/signal definitions:

* ``BO_`` message headers (id, name, DLC, sender), incl. extended ids
* ``SG_`` signal rows: start bit, length, byte order (@0/@1), sign (+/-),
  scale/offset, min/max, unit and receivers
* inline multiplexing (``M`` / ``mN``) and extended multiplex value
  tables (``SG_MUL_VAL_`` with ``a-b,c`` ranges)
* ``//`` comments and multi-line ``CM_`` blocks are tolerated

Everything else (``VAL_``, ``BA_``, ``BA_DEF_``, ``SIG_GROUP_`` ...) is
skipped without losing ordering of the rows we care about.
"""

import re

from .errors import DbcParseError, DbcValidationError
from .model import Signal, Message, Database

# DBC stores the extended-frame flag in the top bits of the 32-bit id.
EXTENDED_FLAG = 0x80000000
EXTENDED_MASK = 0x1FFFFFFF

_BO_RE = re.compile(
    r"^BO_\s+(\S+)\s+([A-Za-z_][\w]*)\s*:\s*(\d+)\s*(\S*)\s*$"
)
_SG_RE = re.compile(
    r"^SG_\s+([A-Za-z_][\w]*)"
    r"(?:\s+(M|m[0-9]+))?"
    r"\s*:\s*"
    r"(\d+)\|(\d+)@(0|1)([+-])"
    r"\s*\(([^,|]+)[,|]([^)]+)\)"
    r"\s*\[([^,|]*)[,|]([^\]]*)\]"
    r'\s*"([^"]*)"'
    r"\s*(.*)$"
)
# Canonical DBC: SG_MUL_VAL_ <frame_id> <signal> <multiplexor> <ranges>;
# (space-separated). A comma-separated, message-name form is accepted too.
_MUL_RE = re.compile(
    r"^SG_MUL_VAL_\s+"
    r"(\S+?)\s*[, ]\s*"
    r"([A-Za-z_][\w]*)\s*[, ]\s*"
    r"([A-Za-z_][\w]*)\s*[, ]\s*"
    r"([^;]+);"
)


def _as_int(token, line):
    try:
        return int(token.strip(), 0)
    except ValueError:
        raise DbcParseError(f"invalid integer {token!r}", line=line)


def _as_float(token, what, line):
    try:
        return float(token.strip())
    except ValueError:
        raise DbcParseError(f"invalid {what} {token!r}", line=line)


def _parse_ranges(text, line):
    """Parse ``0-2,4,7-9`` into ``[(0,2),(4,4),(7,9)]``."""
    ranges = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            lo, hi = _as_int(lo_s, line), _as_int(hi_s, line)
        else:
            lo = hi = _as_int(part, line)
        if lo > hi:
            raise DbcParseError(
                f"inverted multiplex range {lo}-{hi}", line=line
            )
        ranges.append((lo, hi))
    if not ranges:
        raise DbcParseError("empty multiplex value range", line=line)
    ranges.sort()
    # merge adjacent/overlapping ranges
    merged = [ranges[0]]
    for lo, hi in ranges[1:]:
        if lo <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def parse_dbc_text(text, path=None):
    """Parse DBC source text into a validated :class:`Database`."""
    messages = []
    current = None
    pending_mul = []  # (line, msg_name, sig_name, mux_name, ranges)
    in_block_string = False

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()

        # Track multi-line quoted strings (only CM_ blocks do this in DBC).
        if in_block_string:
            if line.count('"') % 2 == 1:
                in_block_string = False
            continue
        if line.startswith("CM_") and line.count('"') % 2 == 1:
            in_block_string = True
            continue

        if not line or line.startswith("//"):
            continue

        if line.startswith("BO_") and (len(line) <= 3 or line[3].isspace()):
            m = _BO_RE.match(line)
            if not m:
                raise DbcParseError(
                    f"malformed message definition: {line!r}",
                    line=lineno, path=path,
                )
            raw_id = _as_int(m.group(1), lineno)
            extended = bool(raw_id & EXTENDED_FLAG)
            frame_id = raw_id & EXTENDED_MASK
            dlc = int(m.group(3))
            current = Message(
                frame_id=frame_id,
                name=m.group(2),
                dlc=dlc,
                sender=m.group(4) or "",
                extended=extended,
            )
            messages.append(current)
            continue

        # An exact "SG_" / "BO_" token (no trailing content) appears in
        # the NS_ symbol list and is not a definition.
        if (
            line.startswith("SG_")
            and len(line) > 3
            and line[3].isspace()
        ):
            if current is None:
                raise DbcParseError(
                    "signal definition outside of any BO_ message",
                    line=lineno, path=path,
                )
            m = _SG_RE.match(line)
            if not m:
                raise DbcParseError(
                    f"malformed signal definition: {line!r}",
                    line=lineno, path=path,
                )
            mux_kind = None
            token = m.group(2)
            if token == "M":
                mux_kind = "multiplexor"
            elif token is not None:
                mux_kind = ("multiplexed", int(token[1:]))

            scale = _as_float(m.group(7), "scale", lineno)
            offset = _as_float(m.group(8), "offset", lineno)
            lo_text, hi_text = m.group(9).strip(), m.group(10).strip()
            minimum = float(lo_text) if lo_text else None
            maximum = float(hi_text) if hi_text else None
            # DBC convention: "[0|0]" means "no limits declared"
            # (Vector tools and cantools drop it to None for both signs).
            if minimum == 0.0 and maximum == 0.0:
                minimum = maximum = None

            sig = Signal(
                name=m.group(1),
                start_bit=int(m.group(3)),
                length=int(m.group(4)),
                byte_order="little_endian" if m.group(5) == "1" else "big_endian",
                signed=m.group(6) == "-",
                scale=scale,
                offset=offset,
                minimum=minimum,
                maximum=maximum,
                unit=m.group(11),
                mux_kind=mux_kind,
            )
            current.signals.append(sig)
            continue

        if line.startswith("SG_MUL_VAL_") and ";" in line:
            m = _MUL_RE.match(line)
            if not m:
                raise DbcParseError(
                    f"malformed SG_MUL_VAL_ definition: {line!r}",
                    line=lineno, path=path,
                )
            pending_mul.append((
                lineno,
                m.group(1),
                m.group(2),
                m.group(3),
                _parse_ranges(m.group(4), lineno),
            ))
            continue
        # Every other keyword (BS_, BU_, NS_, VAL_, BA_, CM_, SIG_GROUP_ ...)
        # is intentionally ignored.

    _apply_extended_mux(messages, pending_mul, path)
    db = Database(messages)
    _validate(db, path)
    return db


def _apply_extended_mux(messages, pending_mul, path):
    by_name = {m.name: m for m in messages}
    by_id = {m.frame_id: m for m in messages}
    for lineno, target, sig_name, mux_name, ranges in pending_mul:
        # First field is the frame id in canonical DBC, a message name in
        # the tolerated comma-separated variant.
        msg = by_name.get(target)
        if msg is None:
            try:
                msg = by_id.get(int(target, 0) & EXTENDED_MASK)
            except ValueError:
                msg = None
        if msg is None:
            raise DbcParseError(
                f"SG_MUL_VAL_ references unknown message {target!r}",
                line=lineno, path=path,
            )
        try:
            sig = msg.get(sig_name)
        except KeyError:
            raise DbcParseError(
                f"SG_MUL_VAL_ references unknown signal {sig_name!r} "
                f"in message {msg.name!r}",
                line=lineno, path=path,
            )
        if msg.multiplexor is None or msg.multiplexor.name != mux_name:
            raise DbcParseError(
                f"SG_MUL_VAL_ references unknown multiplexor {mux_name!r} "
                f"in message {msg.name!r}",
                line=lineno, path=path,
            )
        if not sig.is_multiplexed:
            raise DbcParseError(
                f"signal {sig_name!r} is not declared multiplexed "
                f"(expected an inline mN marker)",
                line=lineno, path=path,
            )
        sig.mux_kind = ("multiplexed", ranges)


def _validate(db, path):
    seen_ids = {}
    seen_names = {}
    for msg in db.messages:
        if msg.frame_id in seen_ids:
            raise DbcValidationError(
                f"duplicate message id 0x{msg.frame_id:X}: "
                f"{seen_ids[msg.frame_id]!r} and {msg.name!r}"
            )
        seen_ids[msg.frame_id] = msg.name
        if msg.name in seen_names:
            raise DbcValidationError(
                f"duplicate message name {msg.name!r}"
            )
        seen_names[msg.name] = True

        if not (0 <= msg.dlc <= 8):
            raise DbcValidationError(
                f"message {msg.name!r}: DLC {msg.dlc} is outside the "
                f"classic CAN range 0-8 (CAN FD DBCs are not supported)"
            )

        muxors = [s for s in msg.signals if s.is_multiplexor]
        if len(muxors) > 1:
            raise DbcValidationError(
                f"message {msg.name!r}: multiple multiplexor signals "
                f"({', '.join(s.name for s in muxors)})"
            )
        muxed = [s for s in msg.signals if s.is_multiplexed]
        if muxed and not muxors:
            raise DbcValidationError(
                f"message {msg.name!r}: multiplexed signals "
                f"({', '.join(s.name for s in muxed)}) without a "
                f"multiplexor (M) signal"
            )

        sig_names = set()
        for sig in msg.signals:
            if sig.name in sig_names:
                raise DbcValidationError(
                    f"message {msg.name!r}: duplicate signal name "
                    f"{sig.name!r}"
                )
            sig_names.add(sig.name)
            if not 1 <= sig.length <= 64:
                raise DbcValidationError(
                    f"signal {msg.name!r}.{sig.name}: length "
                    f"{sig.length} outside 1-64 bits"
                )
            if sig.scale == 0:
                raise DbcValidationError(
                    f"signal {msg.name!r}.{sig.name}: scale must be non-zero"
                )
            positions = _bit_positions(sig)
            for byte, bit in positions:
                if byte >= msg.dlc:
                    raise DbcValidationError(
                        f"signal {msg.name!r}.{sig.name}: bit at byte "
                        f"{byte} exceeds DLC {msg.dlc} "
                        f"(start_bit={sig.start_bit}, length={sig.length})"
                    )
        _check_overlaps(msg)


def _check_overlaps(msg):
    static, muxed = [], []
    for sig in msg.signals:
        group = set(_saw_positions(sig))
        if sig.is_multiplexed:
            muxed.append(sig)
        else:
            static.append((sig, group))  # includes the multiplexor

    # static vs static
    for i in range(len(static)):
        for j in range(i + 1, len(static)):
            s1, g1 = static[i]
            s2, g2 = static[j]
            hit = g1 & g2
            if hit:
                raise DbcValidationError(
                    f"message {msg.name!r}: signals {s1.name!r} and "
                    f"{s2.name!r} overlap at bit position(s) "
                    f"{_fmt_bits(sorted(hit))} (DBC sawtooth numbering)"
                )

    # static vs multiplexed
    for sig in muxed:
        g = set(_saw_positions(sig))
        for other, go in static:
            hit = g & go
            if hit:
                raise DbcValidationError(
                    f"message {msg.name!r}: multiplexed signal "
                    f"{sig.name!r} ({sig.mux_label()}) overlaps static "
                    f"signal {other.name!r} at bit position(s) "
                    f"{_fmt_bits(sorted(hit))}"
                )

    # multiplexed vs multiplexed: conflict only when both can be active
    for i in range(len(muxed)):
        for j in range(i + 1, len(muxed)):
            s1, s2 = muxed[i], muxed[j]
            if _mux_specs_intersect(s1, s2):
                hit = set(_saw_positions(s1)) & set(_saw_positions(s2))
                if hit:
                    raise DbcValidationError(
                        f"message {msg.name!r}: multiplexed signals "
                        f"{s1.name!r} ({s1.mux_label()}) and "
                        f"{s2.name!r} ({s2.mux_label()}) are both active "
                        f"for some multiplexor value and overlap at "
                        f"bit position(s) {_fmt_bits(sorted(hit))}"
                    )


def _mux_specs_intersect(s1, s2):
    def as_ranges(sig):
        spec = sig.mux_kind[1]
        return [(spec, spec)] if isinstance(spec, int) else spec

    for a_lo, a_hi in as_ranges(s1):
        for b_lo, b_hi in as_ranges(s2):
            if a_lo <= b_hi and b_lo <= a_hi:
                return True
    return False


def _fmt_bits(bits):
    shown = ", ".join(str(b) for b in bits[:8])
    if len(bits) > 8:
        shown += ", ..."
    return shown


# ---------------------------------------------------------------------
# Bit layout
# ---------------------------------------------------------------------

def _bit_positions(signal):
    """Physical (byte, wirebit) coordinates occupied by a signal.

    Coordinates use network/linear bit numbering, verified against the
    DBC sawtooth convention (cantools' ``sawtooth_to_network_bitnum``):

    =====  =================  =================
    byte   saw numbers        wire bits (LSB=0)
    =====  =================  =================
    0      7 6 ... 0          0 1 ... 7
    1      15 14 ... 8        0 1 ... 7
    2      23 22 ... 16       0 1 ... 7
    =====  =================  =================

    Linear bit number is ``n = byte*8 + wirebit``.  The DBC start bit is
    exactly:

    * Intel (``@1``): the linear position of the value's **LSB**; higher
      value bits simply occupy ``S, S+1, ...`` (a cross-byte field jumps
      from wire 7 of one byte to wire 0 of the next).
    * Motorola (``@0``): the linear position of the value's **MSB**; the
      next-less-significant bit is ``n-1``, and when a walk reaches wire
      bit 0 (``n % 8 == 0``) it wraps to wire bit 7 of the *next* byte
      (``n + 15``).

    The returned list is ordered from value LSB to value MSB so that the
    codec can place/extract bit ``k`` directly at index ``k``.
    """
    start = signal.start_bit
    if signal.byte_order == "little_endian":
        linears = range(start, start + signal.length)
    else:
        # MSB -> LSB sawtooth walk, then reversed for LSB-first return.
        msb_to_lsb = [start]
        for _ in range(signal.length - 1):
            n = msb_to_lsb[-1]
            # From wire bit 0 of a byte the next-less-significant bit is
            # wire bit 7 of the following byte (n -> n+15); anywhere else
            # the walk simply descends n -> n-1. A byte-aligned Motorola
            # field therefore starts at the *last* saw number of its
            # first byte (e.g. 7|8 for one byte, 15|16 for two).
            msb_to_lsb.append(n + 15 if n % 8 == 0 else n - 1)
        linears = reversed(msb_to_lsb)
    return [(n // 8, n % 8) for n in linears]


def _saw_positions(signal):
    """Same bits as DBC sawtooth bit numbers (for diagnostics).

    saw = 8*byte + (7 - wirebit); saw numbers *descend* inside a byte.
    """
    return [byte * 8 + (7 - bit) for byte, bit in _bit_positions(signal)]


def parse_dbc(path):
    """Read a local ``.dbc`` file and return a validated Database."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return parse_dbc_text(text, path=path)


def load_dbc(path):
    """Convenience alias for :func:`parse_dbc`."""
    return parse_dbc(path)
