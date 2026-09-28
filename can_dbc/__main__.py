"""Command-line interface: decode/encode CAN frames against a local DBC.

Everything runs locally on the given files/arguments; no CAN hardware,
socket, or network is involved.

Usage:
    python -m can_dbc decode file.dbc 0x123 aabbccdd...
    python -m can_dbc encode file.dbc 0x123 Speed=12.5 Mode=1
    python -m can_dbc show   file.dbc [0x123]
"""

from __future__ import annotations

import argparse
import sys

from .errors import DbcError
from .parser import parse_file
from .codec import decode, encode


def _parse_frame_id(text: str) -> int:
    return int(text, 0)


def _parse_payload(text: str) -> bytes:
    cleaned = text.replace(" ", "").replace("0x", "")
    if len(cleaned) % 2:
        cleaned = "0" + cleaned
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise SystemExit(f"invalid hex payload {text!r}: {exc}")


def _fmt_physical(value: float) -> str:
    if isinstance(value, float) and value.is_integer():
        return f"{value:.1f}"
    return f"{value:.10g}"


def cmd_decode(args) -> int:
    db = parse_file(args.dbc)
    frame_id = _parse_frame_id(args.frame_id)
    payload = _parse_payload(args.payload)
    msg = db.by_id(frame_id)
    values = decode(payload, msg)
    print(f"frame 0x{frame_id:X} [{len(payload)}] {payload.hex()}")
    for name, value in values.items():
        sig = msg.signal(name)
        unit = f" {sig.unit}" if sig.unit else ""
        print(f"  {name} = {_fmt_physical(value)}{unit}")
    return 0


def cmd_encode(args) -> int:
    db = parse_file(args.dbc)
    frame_id = _parse_frame_id(args.frame_id)
    msg = db.by_id(frame_id)
    values = {}
    for pair in args.assignments:
        if "=" not in pair:
            raise SystemExit(f"expected NAME=VALUE, got {pair!r}")
        name, _, raw = pair.partition("=")
        values[name.strip()] = float(raw)
    payload = encode(values, msg)
    print(f"frame 0x{frame_id:X} [{len(payload)}] {payload.hex()}")
    return 0


def cmd_show(args) -> int:
    db = parse_file(args.dbc)
    messages = db.messages
    if args.frame_id is not None:
        messages = [db.by_id(_parse_frame_id(args.frame_id))]
    for msg in messages:
        kind = "ext" if msg.extended else "std"
        print(f"BO_ 0x{msg.frame_id:X} {msg.name} dlc={msg.dlc} ({kind})")
        for sig in msg.signals:
            mux = ""
            if sig.is_switch:
                mux = " M"
            elif sig.is_multiplexed:
                mux = f" m{sig.mux_value}"
            print(
                f"  SG_ {sig.name}{mux}: {sig.start}|{sig.length}"
                f"@{1 if sig.byte_order == 'intel' else 0}"
                f"{'-' if sig.signed else '+'} "
                f"({sig.scale:.10g},{sig.offset:.10g}) "
                f"[{sig.minimum:.10g}|{sig.maximum:.10g}] \"{sig.unit}\""
            )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="can_dbc",
        description="Local CAN DBC signal encoder/decoder (no hardware, "
                    "no network).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("decode", help="decode a hex CAN payload")
    p.add_argument("dbc")
    p.add_argument("frame_id", help="e.g. 0x123 or 291")
    p.add_argument("payload", help="hex bytes, e.g. aabbccdd")
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser("encode", help="encode NAME=VALUE pairs to hex")
    p.add_argument("dbc")
    p.add_argument("frame_id")
    p.add_argument("assignments", nargs="+")
    p.set_defaults(func=cmd_encode)

    p = sub.add_parser("show", help="print parsed message/signal layout")
    p.add_argument("dbc")
    p.add_argument("frame_id", nargs="?", default=None)
    p.set_defaults(func=cmd_show)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except DbcError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
