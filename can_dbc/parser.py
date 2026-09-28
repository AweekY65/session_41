"""Hand-written parser for the subset of DBC used by this tool.

Supported grammar (one construct per physical line; ``BA_DEF_``/``VAL_``
etc. are accepted and skipped)::

    VERSION "..."
    NS_ : ...
    BS_:
    BU_: ECU1 ECU2
    BO_ <id> <name>: <dlc> <sender>
     SG_ <name> [M | m<x> | m<x>,<switch-name>] : <start>|<length>@<ord><sign>
               (<scale>,<offset>) [<min>|<max>] "<unit>" <receivers>
    BO_TX_BU_ ...
    CM_ "..." / CM_ BO_ id "..." / CM_ SG_ id sig "..."
    BA_ ...
    VAL_ ...
    SIG_VALTYPE_ ...

Line-continuations are not part of the DBC grammar for these constructs;
``CM_`` and ``BA_`` string values may contain escaped quotes but never raw
newlines.
"""

from __future__ import annotations

import re

from .errors import (
    DbcParseError,
    DuplicateMessageIdError,
)
from .model import Signal, Message, Database, INTEL, MOTOROLA

# BO_ 2365475321 DRM: 8 VCS
_BO_RE = re.compile(r"^BO_\s+(\d+)\s+(\S+?)\s*:\s*(\d+)\s+(\S*)\s*$")

# SG_ NAME M  : start|len@ordSign (scale,off) [min|max] "unit" Rx
# mux token: absent | "M" | "m0" | "m12,OtherSwitch" (extended, rare)
_NUM = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_SG_RE = re.compile(
    r"^SG_\s+(\S+?)(?:\s+([mM])(\d*)(?:,(\S+?))?)?\s*:"
    r"\s*(\d+)\s*\|\s*(\d+)\s*@\s*([01])\s*([+-])\s*"
    rf"\(\s*({_NUM})\s*,\s*({_NUM})\s*\)"
    rf"\s*\[\s*({_NUM})\s*\|\s*({_NUM})\s*\]"
    r'\s*"((?:[^"\\]|\\.)*)"'
    r"\s*(.*)$"
)

_EXTENDED_ID_FLAG = 1 << 31

# DBC keywords this tool accepts without interpreting.
_KNOWN_KEYWORDS = {
    "VERSION", "NS_", "NS_DESC_", "BS_", "BU_", "BO_TX_BU_",
    "BA_DEF_", "BA_DEF_REL_", "BA_", "BA_REL_", "BA_DEF_DEF_",
    "BA_DEF_DEF_REL_", "VAL_", "VAL_TABLE_", "SIG_VALTYPE_",
    "SGTYPE_", "SIG_GROUP_", "EV_", "ENVVAR_DATA_", "CAT_DEF_",
    "CAT_", "FILTER", "SGTYPE_VAL_", "BA_DEF_SGTYPE_", "BA_SGTYPE_",
    "SIG_TYPE_REF_", "SG_MUL_VAL_", "EV_DATA_", "SGTYPE_REL_",
}


def _strip_comment(line: str) -> str:
    """Remove a trailing ``// ...`` line comment (respecting strings)."""
    in_string = False
    escape = False
    for i, ch in enumerate(line):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
        elif ch == '"':
            in_string = not in_string
        elif not in_string and line[i:i + 2] == "//":
            return line[:i]
    return line


def _parse_receivers(tail: str) -> list[str]:
    tail = tail.strip()
    if tail.endswith(";"):
        tail = tail[:-1].strip()
    return [r for r in tail.split(",") if r]


def _parse_message_id(raw: str, lineno: int) -> tuple[int, bool]:
    value = int(raw)
    extended = bool(value & _EXTENDED_ID_FLAG)
    if extended:
        value &= ~_EXTENDED_ID_FLAG
    if value > 0x1FFFFFFF:
        raise DbcParseError(
            f"line {lineno}: CAN id {value:#x} exceeds 29-bit extended range"
        )
    return value, extended


def _parse_signal(m: re.Match, lineno: int) -> tuple[Signal, str | None]:
    name = m.group(1)
    mux_letter = m.group(2)        # 'M' (switch) or 'm' (multiplexed)
    mux_value_raw = m.group(3)     # digits after 'm'
    ext_switch = m.group(4)        # name after comma (extended mux)
    start = int(m.group(5))
    length = int(m.group(6))
    byte_order = INTEL if m.group(7) == "1" else MOTOROLA
    signed = m.group(8) == "-"
    scale = float(m.group(9))
    offset = float(m.group(10))
    minimum = float(m.group(11))
    maximum = float(m.group(12))
    unit = m.group(13)
    receivers = _parse_receivers(m.group(14))

    if length < 1 or length > 64:
        raise DbcParseError(
            f"line {lineno}: signal {name!r} length {length} outside 1..64"
        )

    mux_kind = None
    mux_value = None
    if mux_letter == "M":
        mux_kind = "switch"
        if mux_value_raw != "":
            raise DbcParseError(
                f"line {lineno}: multiplexer switch {name!r} must be 'M', "
                f"not M{mux_value_raw}"
            )
    elif mux_letter == "m":
        mux_kind = "multiplexed"
        if mux_value_raw == "":
            raise DbcParseError(
                f"line {lineno}: multiplexed signal {name!r} needs a switch "
                f"value, e.g. m0"
            )
        mux_value = int(mux_value_raw)

    sig = Signal(
        name=name,
        start=start,
        length=length,
        byte_order=byte_order,
        signed=signed,
        scale=scale,
        offset=offset,
        minimum=minimum,
        maximum=maximum,
        unit=unit,
        receivers=receivers,
        mux_kind=mux_kind,
        mux_value=mux_value,
    )
    return sig, ext_switch


def parse_string(text: str) -> Database:
    """Parse DBC source text into a validated :class:`Database`.

    :raises DbcError: on any malformed input, duplicate id, overlap,
        out-of-bounds bit, or dangling multiplexer reference.
    """
    db = Database()
    seen_ids: set[int] = set()
    current: Message | None = None
    in_ns_block = False
    # (message_name, signal_name) -> extended-mux switch name
    ext_switch_map: dict[tuple[str, str], str] = {}

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        stripped = _strip_comment(raw_line)
        if in_ns_block:
            # The NS_ block is an indented list of symbol names ending at
            # the first non-indented line.
            if raw_line.startswith((" ", "\t")) or not stripped.strip():
                continue
            in_ns_block = False
        line = stripped.strip()
        if not line:
            continue

        if line.startswith("NS_"):
            # Multi-line form "NS_ :" followed by an indented symbol list;
            # a one-line "NS_ : SYM SYM" has no continuation block.
            _, _, tail = line.partition(":")
            in_ns_block = not tail.strip()
            continue

        if line.startswith("BO_"):
            m = _BO_RE.match(line)
            if not m:
                raise DbcParseError(
                    f"line {lineno}: malformed BO_ definition: {raw_line!r}"
                )
            frame_id, extended = _parse_message_id(m.group(1), lineno)
            if frame_id in seen_ids:
                raise DuplicateMessageIdError(
                    f"line {lineno}: duplicate message id "
                    f"0x{frame_id:X} ({frame_id})"
                )
            seen_ids.add(frame_id)
            dlc = int(m.group(3))
            if not 0 <= dlc <= 64:
                raise DbcParseError(
                    f"line {lineno}: DLC {dlc} outside 0..64"
                )
            current = Message(
                frame_id=frame_id,
                name=m.group(2),
                dlc=dlc,
                sender=m.group(4) or "",
                extended=extended,
            )
            db.messages.append(current)
            continue

        if line.startswith("SG_"):
            if current is None:
                raise DbcParseError(
                    f"line {lineno}: SG_ without an enclosing BO_"
                )
            m = _SG_RE.match(line)
            if not m:
                raise DbcParseError(
                    f"line {lineno}: malformed SG_ definition: {raw_line!r}"
                )
            sig, ext_switch = _parse_signal(m, lineno)
            if any(s.name == sig.name for s in current.signals):
                raise DbcParseError(
                    f"line {lineno}: duplicate signal {sig.name!r} in "
                    f"message {current.name!r}"
                )
            current.signals.append(sig)
            if ext_switch is not None:
                ext_switch_map[(current.name, sig.name)] = ext_switch
            continue

        if line.startswith("CM_"):
            # Comments are informational; their text may contain anything.
            continue

        head = line.split(None, 1)[0].rstrip(":")
        if head not in _KNOWN_KEYWORDS:
            raise DbcParseError(
                f"line {lineno}: unrecognized DBC token {head!r} "
                f"(line: {raw_line.strip()!r})"
            )

    # ------------------------------------------------------------------
    # Resolve multiplexer dependencies now that every switch is known.
    # ------------------------------------------------------------------
    for msg in db.messages:
        switches = [s for s in msg.signals if s.is_switch]
        switch_names = {s.name for s in switches}
        for sig in msg.signals:
            if not sig.is_multiplexed:
                continue
            ext = ext_switch_map.get((msg.name, sig.name))
            if ext is not None:
                if ext not in switch_names:
                    raise DbcParseError(
                        f"signal {sig.name!r}: extended multiplexer switch "
                        f"{ext!r} not found in message {msg.name!r}"
                    )
                sig.mux_dependencies.append((ext, sig.mux_value))
            else:
                if not switches:
                    raise DbcParseError(
                        f"signal {sig.name!r} in message {msg.name!r} is "
                        f"multiplexed (m{sig.mux_value}) but no 'M' "
                        f"multiplexer signal exists"
                    )
                if len(switches) > 1:
                    raise DbcParseError(
                        f"signal {sig.name!r}: message {msg.name!r} has "
                        f"multiple multiplexer switches; extended mux "
                        f"syntax 'm<val>,<switch>' is required"
                    )
                sig.mux_dependencies.append((switches[0].name, sig.mux_value))

    db.validate()
    return db


def parse_file(path: str) -> Database:
    """Read and parse a ``.dbc`` file from the local filesystem."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse_string(fh.read())
