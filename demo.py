#!/usr/bin/env python3
"""Local demo: parse examples/example.dbc, encode/decode frames and print hex.

Nothing here touches a CAN bus; it only builds payloads in memory and prints
them. Run:  python3 demo.py
"""

import os

from can_tool import parse_dbc, encode_frame, decode_frame_raw
from can_tool.frame import hex_dump

HERE = os.path.dirname(os.path.abspath(__file__))


def banner(title):
    print("\n" + "=" * 68)
    print(title)
    print("-" * 68)


def main():
    db = parse_dbc(os.path.join(HERE, "examples", "example.dbc"))

    banner(f"Parsed {len(db.messages)} message(s) from the local DBC")
    for msg in db.messages:
        ext = " [extended 29-bit]" if msg.extended else ""
        print(f"  0x{msg.frame_id:03X} {msg.name:20s} DLC={msg.dlc}{ext}")
        for sig in msg.signals:
            bo = "Motorola" if sig.byte_order == "big_endian" else "Intel"
            mux = f" {sig.mux_label()}" if sig.mux_label() else ""
            print(f"      {sig.name:16s} start={sig.start_bit:<3d} "
                  f"len={sig.length:<2d} {bo:8s} "
                  f"{'signed' if sig.signed else 'unsigned':8s}{mux}")

    banner("Encode/decode: EngineData (Intel, signed + scaled)")
    values = {"EngineSpeed": 2400.5, "EngineTemp": 85,
              "ThrottlePos": 37.5, "OdometerLarge": 4660, "CheckEngine": 1}
    frame = encode_frame(db, "EngineData", values)
    print(f"  frame 100# {hex_dump(frame)}")
    phys, raw = decode_frame_raw(db, 0x100, frame)
    for name, value in phys.items():
        sig = db.get_message_by_id(0x100).get(name)
        print(f"  {name:16s} = {value:g} {sig.unit:<5s} (raw={raw[name]})")

    banner("Encode/decode: BodyStatus (Motorola cross-byte fields)")
    frame = encode_frame(db, "BodyStatus", {
        "VehicleSpeed": 123.45, "SteeringAngle": -45.7,
        "GearLever": 5, "HighBeam": 1})
    print(f"  frame 101# {hex_dump(frame)}")
    phys, _ = decode_frame_raw(db, 0x101, frame)
    for name, value in phys.items():
        sig = db.get_message_by_id(0x101).get(name)
        print(f"  {name:16s} = {value:g} {sig.unit}")

    banner("Multiplexing: DiagnosticMessage, three switch values")
    for mode, branch in [
        (0, {"Voltage": 13.7, "Current": -5.123}),
        (1, {"Pressure": 400.0, "PumpRpm": 3000}),
        (2, {"ErrorCode": 4095}),
    ]:
        frame = encode_frame(db, "DiagnosticMessage",
                             {"ServiceMode": mode, **branch})
        phys, _ = decode_frame_raw(db, 0x102, frame)
        print(f"  ServiceMode={mode}  frame 102# {hex_dump(frame)}")
        print(f"      active signals: {sorted(phys)}")

    banner("Range error example (88 degC cannot fit an 8-bit signed -40 offset)")
    try:
        encode_frame(db, "EngineData", {
            "EngineSpeed": 0, "EngineTemp": 88, "ThrottlePos": 0,
            "OdometerLarge": 0, "CheckEngine": 0})
    except Exception as exc:
        print(f"  EncodeError: {exc}")


if __name__ == "__main__":
    main()
