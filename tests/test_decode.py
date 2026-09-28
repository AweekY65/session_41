"""Decode tests against known byte vectors (cross-checked with cantools)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from can_dbc import load_string, decode, decode_raw
from tests.helpers import Reporter
from tests.sample_dbc import DBC, DBC_SHORT


def run() -> int:
    r = Reporter()
    db = load_string(DBC)
    engine = db.by_id(100)
    cross = db.by_id(101)

    r.section("Decode known Motorola/Intel frames (cantools vectors)")
    p = bytes.fromhex("2ee0802005f40100")
    r.frame("EngineData", p)
    r.eq("RPM 0.25-scale Motorola", decode(p, engine)["RPM"], 3000.0)
    r.eq("Temp signed Intel with -40 offset", decode(p, engine)["Temp"], 25.0)
    r.eq("Flags 4-bit nibble", decode(p, engine)["Flags"], 5.0)
    r.eq("Throttle 12-bit scale 0.1", decode(p, engine)["Throttle"], 50.0)
    r.eq("RPM raw before scaling", decode_raw(p, engine)["RPM"], 12000)

    p = bytes.fromhex("ffff803f0fff0f00")
    r.frame("EngineData max values", p)
    v = decode(p, engine)
    r.eq("RPM at max raw", v["RPM"], 16383.75)
    r.eq("Temp signed raw=127 -> 87", v["Temp"], 87.0)
    r.eq("Throttle max 409.5", v["Throttle"], 409.5)

    r.section("Cross-byte fields")
    p = bytes.fromhex("c0ab000123000000")
    r.frame("CrossByte", p)
    v = decode(p, cross)
    r.eq("IntelCross 12-bit LSB-first", v["IntelCross"], 0xABC)
    r.eq("MotoCross 12-bit big-endian walk", v["MotoCross"], 0x123)
    r.eq("SignedMoto (raw 0 -> -10)", v["SignedMoto"], -10.0)

    p = bytes.fromhex("f0ff000fff7fff00")
    r.frame("CrossByte max", p)
    v = decode(p, cross)
    r.eq("IntelCross all ones", v["IntelCross"], 4095)
    r.eq("MotoCross all ones", v["MotoCross"], 4095)
    r.eq("SignedMoto raw=32767 -> 16373.5", v["SignedMoto"], 16373.5)

    p = bytes.fromhex("1000000001800000")
    r.frame("CrossByte negative", p)
    v = decode(p, cross)
    r.eq("SignedMoto raw=-32768 -> -16394.0", v["SignedMoto"], -16394.0)

    r.section("Signed interpretation on both endians")
    short_db = load_string(DBC_SHORT)
    basic = short_db.by_id(256)
    # LE16 signed raw=-1 (0xFFFF), BES8 signed raw=-1 (byte2), BEU8=0xFF
    p = bytes.fromhex("ffffffff")
    r.frame("Basic (LE=-1 scaled, BES8=-1, BEU8=255)", p)
    v = decode(p, basic)
    r.eq("LE16 signed raw -1 -> -2+100=98", v["LE16"], 98.0)
    r.eq("BES8 signed raw -1 -> -51", v["BES8"], -51.0)
    r.eq("BEU8 unsigned 255", v["BEU8"], 255.0)

    return r.summary("decode")


def test_decode_suite():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
