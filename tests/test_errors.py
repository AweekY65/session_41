"""Diagnostics: duplicate ids, overlaps, bad bits, corrupt DBC, wrong DLC."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from can_dbc import load_string, decode, encode
from can_dbc.errors import (
    DbcParseError, DuplicateMessageIdError, SignalOverlapError,
    BitOutOfBoundsError, DlcError, DecodeError, EncodeError,
)
from tests.helpers import Reporter
from tests.sample_dbc import DBC


def run() -> int:
    r = Reporter()

    r.section("Duplicate message id")
    dup = r'''VERSION ""

BO_ 100 A: 8 ECU
BO_ 100 B: 8 ECU
'''
    r.expect_raises("two BO_ with id 100", DuplicateMessageIdError,
                    load_string, dup)

    dup_ext = r'''VERSION ""

BO_ 100 A: 8 ECU
BO_ 2147483748 B: 8 ECU
'''
    # 2147483748 = 0x80000064 -> extended flag set, id 100 again
    r.expect_raises("extended-flag id collides with standard 100",
                    DuplicateMessageIdError, load_string, dup_ext)

    r.section("Signal overlap")
    overlap = r'''VERSION ""

BO_ 100 A: 8 ECU
 SG_ X : 0|16@1+ (1,0) [0|65535] "" ECU
 SG_ Y : 8|8@1+ (1,0) [0|255] "" ECU
'''
    r.expect_raises("X (bits 0-15) overlaps Y (bits 8-15)",
                    SignalOverlapError, load_string, overlap)

    r.section("Bit out of bounds")
    oob = r'''VERSION ""

BO_ 100 A: 2 ECU
 SG_ X : 8|16@1+ (1,0) [0|65535] "" ECU
'''
    r.expect_raises("16-bit signal at byte 1 exceeds DLC=2",
                    BitOutOfBoundsError, load_string, oob)

    oob_moto = r'''VERSION ""

BO_ 100 A: 1 ECU
 SG_ X : 7|16@0+ (1,0) [0|65535] "" ECU
'''
    r.expect_raises("Motorola 16-bit signal exceeds DLC=1",
                    BitOutOfBoundsError, load_string, oob_moto)

    r.section("Corrupt DBC text")
    r.expect_raises("garbage token", DbcParseError,
                    load_string, "BO_ 100 A: 8 ECU\n WAT_ 1 2 3\n")
    r.expect_raises("SG_ before BO_", DbcParseError,
                    load_string, ' SG_ X : 0|8@1+ (1,0) [0|255] "" ECU\n')
    r.expect_raises("truncated SG_ line", DbcParseError,
                    load_string, "BO_ 100 A: 8 ECU\n SG_ X : 0|8@1+ (1,0)\n")
    r.expect_raises("DLC 65", DbcParseError,
                    load_string, "BO_ 100 A: 65 ECU\n")
    r.expect_raises("signal length 0", DbcParseError,
                    load_string,
                    'BO_ 100 A: 8 ECU\n SG_ X : 0|0@1+ (1,0) [0|1] "" ECU\n')
    r.expect_raises("duplicate signal name", DbcParseError,
                    load_string,
                    'BO_ 100 A: 8 ECU\n'
                    ' SG_ X : 0|8@1+ (1,0) [0|255] "" ECU\n'
                    ' SG_ X : 8|8@1+ (1,0) [0|255] "" ECU\n')
    r.expect_raises("CAN id beyond 29 bits", DbcParseError,
                    load_string, "BO_ 3221225472 A: 8 ECU\n")

    r.section("DLC mismatch at decode time")
    db = load_string(DBC)
    engine = db.by_id(100)
    r.expect_raises("7-byte payload for DLC=8", DlcError,
                    decode, bytes(7), engine)
    r.expect_raises("9-byte payload for DLC=8", DlcError,
                    decode, bytes(9), engine)
    r.expect_raises("non-bytes payload", DecodeError,
                    decode, "not-bytes", engine)

    r.section("Unknown frame id")
    r.expect_raises("id 0x999 not in database", DecodeError,
                    decode, bytes(8), db, 0x999)

    r.section("Encode diagnostics")
    r.expect_raises("NaN physical value", EncodeError,
                    encode, {"RPM": float("nan")}, engine)
    r.expect_raises("inf physical value", EncodeError,
                    encode, {"RPM": float("inf")}, engine)

    return r.summary("diagnostics")


def test_diagnostics_suite():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
