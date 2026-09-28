"""Basic multiplexer tests: branch selection on decode and encode."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from can_dbc import load_string, encode, decode, encode_raw, decode_raw
from can_dbc.errors import EncodeError, SignalOverlapError
from tests.helpers import Reporter
from tests.sample_dbc import DBC


def run() -> int:
    r = Reporter()
    db = load_string(DBC)
    mux = db.by_id(200)

    r.section("Encode/decode each multiplexer branch")
    p0 = encode({"Mode": 0, "ModeA": 4660}, mux)
    r.frame("Mode=0 (ModeA)", p0, "expected 0012340000000000")
    r.eq("branch 0 hex matches cantools", p0.hex(), "0012340000000000")
    v0 = decode(p0, mux)
    r.eq("decode branch 0 has Mode+ModeA only",
         v0, {"Mode": 0.0, "ModeA": 4660.0})

    p1 = encode({"Mode": 1, "ModeB": -5, "ModeB2": 200}, mux)
    r.frame("Mode=1 (ModeB/ModeB2)", p1, "expected 10fbc80000000000")
    r.eq("branch 1 hex matches cantools", p1.hex(), "10fbc80000000000")
    v1 = decode(p1, mux)
    r.eq("decode branch 1", v1,
         {"Mode": 1.0, "ModeB": -5.0, "ModeB2": 200.0})

    r.section("Only active branch decodes, stale bytes ignored")
    # Hand-craft a frame whose branch-0 slot contains 0x1234, switch=1.
    stale = bytes.fromhex("1012340000000000")
    r.frame("Mode=1 with branch-0 bytes still set", stale)
    v = decode(stale, mux)
    r.eq("ModeA must not be decoded for Mode=1", "ModeA" in v, False)
    r.eq("ModeB decodes from shared slot", v.get("ModeB"), 18.0)
    # Conversely, ModeB bytes absent for Mode=0
    v = decode(bytes.fromhex("00abcdef00000000"), mux)
    r.eq("ModeB excluded for Mode=0", "ModeB" in v, False)
    r.eq("ModeA decodes 0xABCD for Mode=0", v.get("ModeA"), 0xABCD)

    r.section("Raw multiplexer encoding")
    p = encode_raw({"Mode": 1, "ModeB": -1, "ModeB2": 255}, mux)
    r.frame("raw branch 1 extremes", p)
    r.eq("raw round-trip",
         decode_raw(p, mux),
         {"Mode": 1, "ModeB": -1, "ModeB2": 255})

    r.section("Branch consistency errors")
    r.expect_raises(
        "ModeA encoded while Mode=1", EncodeError,
        encode, {"Mode": 1, "ModeA": 1}, mux)
    r.expect_raises(
        "ModeB encoded while Mode=0", EncodeError,
        encode, {"Mode": 0, "ModeB": 1}, mux)

    r.section("Overlap across branches is allowed; within branch rejected")
    ok = load_string(DBC)  # ModeA and ModeB share bits, different branches
    r.eq("sample DBC loads despite branch overlap", True, ok is not None)

    bad = r'''VERSION ""

BO_ 300 BadMux: 2 ECU1
 SG_ Sel M : 0|4@1+ (1,0) [0|15] "" ECU2
 SG_ A m0 : 4|8@1+ (1,0) [0|255] "" ECU2
 SG_ B m1 : 6|8@1+ (1,0) [0|255] "" ECU2
'''
    # A (bits 4..11) and B (bits 6..13) never coexist -> allowed
    r.guard("non-overlapping-at-runtime branches parse", load_string, bad)
    r.check("cross-branch overlap accepted", r.failed == 0)

    bad2 = r'''VERSION ""

BO_ 301 BadMux2: 2 ECU1
 SG_ Sel M : 0|4@1+ (1,0) [0|15] "" ECU2
 SG_ A m0 : 4|8@1+ (1,0) [0|255] "" ECU2
 SG_ C m0 : 8|8@1+ (1,0) [0|255] "" ECU2
'''
    r.expect_raises("A and C collide inside branch m0",
                    SignalOverlapError, load_string, bad2)

    bad3 = r'''VERSION ""

BO_ 302 BadMux3: 2 ECU1
 SG_ Sel M : 0|4@1+ (1,0) [0|15] "" ECU2
 SG_ Always : 4|8@1+ (1,0) [0|255] "" ECU2
 SG_ A m0 : 7|8@1+ (1,0) [0|255] "" ECU2
'''
    r.expect_raises("always-present signal collides with m0 branch",
                    SignalOverlapError, load_string, bad3)

    bad4 = r'''VERSION ""

BO_ 303 BadMux4: 2 ECU1
 SG_ Sel M : 0|8@1+ (1,0) [0|255] "" ECU2
 SG_ A m0 : 4|8@1+ (1,0) [0|255] "" ECU2
'''
    r.expect_raises("switch itself overlaps branch signal",
                    SignalOverlapError, load_string, bad4)

    r.section("Missing switch diagnostic")
    no_switch = r'''VERSION ""

BO_ 302 Oops: 2 ECU1
 SG_ A m0 : 0|8@1+ (1,0) [0|255] "" ECU2
'''
    from can_dbc.errors import DbcParseError
    r.expect_raises("m0 without M switch", DbcParseError,
                    load_string, no_switch)

    return r.summary("multiplexing")


def test_mux_suite():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
