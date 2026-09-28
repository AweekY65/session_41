"""Command line front-end for the local DBC tool.

Runs entirely against local files. Examples::

    python -m can_tool info examples/example.dbc
    python -m can_tool encode --dbc examples/example.dbc --message EngineData \
        --set EngineSpeed=2400.5 --set EngineTemp=88
    python -m can_tool decode --dbc examples/example.dbc --id 0x100 \
        --data "40 06 58 00 00 00 00 00"

Everything is printed as hex frames plus decoded values; no hardware,
GUI or network access is involved.
"""

import argparse
import sys

from . import parse_dbc, encode_frame, decode_frame_raw
from .errors import DbcError
from .frame import hex_dump


def _parse_set(tokens):
    values = {}
    for token in tokens:
        if "=" not in token:
            raise SystemExit(
                f"--set expects NAME=VALUE (physical) or NAME=rN (raw), "
                f"got {token!r}"
            )
        name, value = token.split("=", 1)
        name, value = name.strip(), value.strip()
        if value.startswith("r") and value[1:].lstrip("-").isdigit():
            from .codec import Raw
            values[name] = Raw(int(value[1:]))
        else:
            try:
                num = float(value)
            except ValueError:
                raise SystemExit(f"value for {name!r} is not a number: {value!r}")
            values[name] = int(num) if num.is_integer() and "." not in value else num
    return values


def _cmd_info(args):
    db = parse_dbc(args.dbc)
    print(f"# {args.dbc}: {len(db.messages)} message(s)")
    for msg in db.messages:
        flag = " (extended)" if msg.extended else ""
        print(f"BO_ {msg.frame_id} (0x{msg.frame_id:X}) "
              f"{msg.name} DLC={msg.dlc}{flag}")
        for sig in msg.signals:
            mux = f" [{sig.mux_label()}]" if sig.mux_label() else ""
            lo, hi = sig.physical_range()
            print(
                f"   SG_ {sig.name}{mux}: start={sig.start_bit} "
                f"len={sig.length} "
                f"{'Motorola' if sig.byte_order == 'big_endian' else 'Intel'} "
                f"{'signed' if sig.signed else 'unsigned'} "
                f"scale={sig.scale:g} offset={sig.offset:g} "
                f"unit={sig.unit!r} physical=[{lo:g}, {hi:g}]"
            )
    return 0


def _cmd_encode(args):
    db = parse_dbc(args.dbc)
    values = _parse_set(args.set)
    payload = encode_frame(db, args.message, values)
    msg = db.get_message_by_name(args.message)
    print(f"encoded {msg.name} (id=0x{msg.frame_id:X}, DLC={msg.dlc})")
    print(f"frame: {msg.frame_id:03X}#{' '.join(f'{b:02X}' for b in payload)}")
    print("hex  :", hex_dump(payload))
    return 0


def _cmd_decode(args):
    db = parse_dbc(args.dbc)
    data = bytes.fromhex(args.data.replace(" ", "").replace("#", ""))
    frame_id = int(args.id, 0)
    physical, raw = decode_frame_raw(db, frame_id, data)
    msg = db.get_message_by_id(frame_id)
    print(f"decoded {msg.name} (id=0x{msg.frame_id:X})")
    print("frame:", f"{msg.frame_id:03X}#{hex_dump(data)}")
    for name, value in physical.items():
        sig = msg.get(name)
        print(f"  {name:24s} = {value:g} {sig.unit:<6s}  (raw={raw[name]})")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m can_tool",
        description="Local CAN DBC encoder/decoder (no bus, no network).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="parse a DBC and print its contents")
    p_info.add_argument("dbc")
    p_info.set_defaults(func=_cmd_info)

    p_enc = sub.add_parser("encode", help="encode physical values to a hex frame")
    p_enc.add_argument("--dbc", required=True)
    p_enc.add_argument("--message", required=True,
                       help="message name (or id with --id)")
    p_enc.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                       help="physical value, or raw integer as NAME=r5")
    p_enc.set_defaults(func=_cmd_encode)

    p_dec = sub.add_parser("decode", help="decode a hex frame into signals")
    p_dec.add_argument("--dbc", required=True)
    p_dec.add_argument("--id", required=True, help="frame id, e.g. 0x100")
    p_dec.add_argument("--data", required=True,
                       help="hex payload, e.g. '40 06 58 00 00 00 00 00'")
    p_dec.set_defaults(func=_cmd_decode)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except DbcError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
