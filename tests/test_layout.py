"""Bit-layout tests: Intel/Motorola positions and cross-byte walks."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from can_dbc.layout import signal_bit_positions, ensure_in_bounds
from can_dbc.errors import BitOutOfBoundsError
from tests.helpers import Reporter


def run() -> int:
    r = Reporter()

    r.section("Intel (little-endian) positions")
    # start = linear LSB, returned MSB-first
    r.eq("intel 0|8", signal_bit_positions(0, 8, "intel"),
         [7, 6, 5, 4, 3, 2, 1, 0])
    r.eq("intel 4|12 spans bytes 0-1", signal_bit_positions(4, 12, "intel"),
         [15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4])
    r.eq("intel 35|12 crosses byte 4/5",
         signal_bit_positions(35, 12, "intel"),
         list(range(46, 34, -1)))
    r.guard("intel bits inside DLC=6",
            lambda: ensure_in_bounds(signal_bit_positions(35, 12, "intel"),
                                     6, "S"))
    r.check("intel DLC=6 bounds ok", r.failed == 0)

    r.section("Motorola (big-endian) positions, MSB-first")
    r.eq("motorola 7|8 fills byte 0", signal_bit_positions(7, 8, "motorola"),
         [7, 6, 5, 4, 3, 2, 1, 0])
    r.eq("motorola 7|16 fills bytes 0-1",
         signal_bit_positions(7, 16, "motorola"),
         [7, 6, 5, 4, 3, 2, 1, 0, 15, 14, 13, 12, 11, 10, 9, 8])
    r.eq("motorola 11|12 classic cross-byte",
         signal_bit_positions(11, 12, "motorola"),
         [11, 10, 9, 8, 23, 22, 21, 20, 19, 18, 17, 16])
    r.eq("motorola 27|12 cross-byte",
         signal_bit_positions(27, 12, "motorola"),
         [27, 26, 25, 24, 39, 38, 37, 36, 35, 34, 33, 32])
    r.eq("motorola 35|12 cross-byte (cantools vector)",
         signal_bit_positions(35, 12, "motorola"),
         [35, 34, 33, 32, 47, 46, 45, 44, 43, 42, 41, 40])
    r.eq("motorola 15|16 spans bytes 1-2",
         signal_bit_positions(15, 16, "motorola"),
         [15, 14, 13, 12, 11, 10, 9, 8, 23, 22, 21, 20, 19, 18, 17, 16])
    r.eq("motorola 23|16 spans bytes 2-3",
         signal_bit_positions(23, 16, "motorola"),
         [23, 22, 21, 20, 19, 18, 17, 16, 31, 30, 29, 28, 27, 26, 25, 24])
    r.eq("motorola 63|8 fills byte 7",
         signal_bit_positions(63, 8, "motorola"),
         [63, 62, 61, 60, 59, 58, 57, 56])

    r.section("Out-of-bounds diagnostics")
    r.expect_raises("intel 60|8 in DLC=8", BitOutOfBoundsError,
                    ensure_in_bounds,
                    signal_bit_positions(60, 8, "intel"), 8, "LateIntel")
    r.expect_raises("motorola 56|8 wraps past DLC=8", BitOutOfBoundsError,
                    ensure_in_bounds,
                    signal_bit_positions(56, 8, "motorola"), 8, "LateMoto")
    r.expect_raises("motorola 7|16 in DLC=1", BitOutOfBoundsError,
                    ensure_in_bounds,
                    signal_bit_positions(7, 16, "motorola"), 1, "WideMoto")

    r.section("Bad layout arguments")
    r.expect_raises("zero length", ValueError,
                    signal_bit_positions, 0, 0, "intel")
    r.expect_raises("unknown endianness", ValueError,
                    signal_bit_positions, 0, 8, "weird")

    return r.summary("layout")


def test_layout_suite():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
