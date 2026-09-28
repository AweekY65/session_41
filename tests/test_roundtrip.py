"""Encode/decode round-trip tests with hex frame output."""

import random
import unittest

from tests._helpers import make_db, show_frame
from can_tool import encode_frame, decode_frame, decode_frame_raw, Raw

MID = 0x123


def _sg(name, spec, mux=""):
    token = f" {mux}" if mux else ""
    return f" SG_ {name}{token} : {spec}\n"


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        random.seed(1234)

    def _roundtrip(self, start, length, bo, signed, scale, offset):
        sign = "-" if signed else "+"
        db = make_db(
            f' SG_ S : {start}|{length}@{bo}{sign} '
            f'({scale},{offset}) [0|0] "u" N\n',
            mid=MID,
        )
        sig = db.messages[0].signals[0]
        # cover the whole raw range
        candidates = {sig.raw_min, sig.raw_max, 0}
        for _ in range(30):
            candidates.add(random.randint(sig.raw_min, sig.raw_max))
        for raw in sorted(candidates):
            phys = raw * scale + offset
            frame = encode_frame(db, MID, {"S": phys})
            decoded_phys = decode_frame(db, MID, frame)["S"]
            decoded_raw = decode_frame_raw(db, MID, frame)[1]["S"]
            self.assertEqual(
                decoded_raw, raw,
                msg=f"raw mismatch {start}|{length}@{bo} {signed} "
                    f"frame={frame.hex()}",
            )
            self.assertAlmostEqual(decoded_phys, phys, places=6)
        show_frame(
            f"roundtrip {start}|{length}@{bo} "
            f"{'s' if signed else 'u'} x{len(candidates)}",
            MID, frame, f"last raw={raw}",
        )

    def test_intel_unsigned_sizes(self):
        for length in (1, 2, 5, 8, 11, 16, 24, 32):
            with self.subTest(length=length):
                self._roundtrip(0, length, "1", False, 1, 0)

    def test_intel_signed_sizes_and_scales(self):
        for length in (2, 8, 12, 16, 32):
            with self.subTest(length=length):
                self._roundtrip(0, length, "1", True, 0.5, -10)

    def test_motorola_unsigned_sizes(self):
        # byte-aligned Motorola starts: 7, 15, 23, ...
        for start, length in [(7, 8), (7, 16), (15, 16), (23, 16),
                              (31, 16), (39, 32), (7, 32)]:
            with self.subTest(start=start, length=length):
                self._roundtrip(start, length, "0", False, 0.01, 100)

    def test_motorola_signed_unaligned(self):
        for start, length in [(8, 16), (12, 12), (24, 13), (40, 9)]:
            with self.subTest(start=start, length=length):
                self._roundtrip(start, length, "0", True, 1, 0)

    def test_full_message_roundtrip(self):
        """Several signals, both endiannesses, packed in one 8-byte frame."""
        db = make_db(
            _sg("Rpm", '0|16@1+ (0.25,0) [0|16383.75] "rpm" N')
            + _sg("Temp", '16|8@1- (1,-40) [-40|87] "degC" N')
            + _sg("Speed", '39|16@0+ (0.01,0) [0|655.35] "km/h" N')
            + _sg("Angle", '55|8@1- (1,0) [-128|127] "deg" N')
            + _sg("Flag", '63|1@1+ (1,0) [0|1] "" N'),
            mid=MID,
        )
        values = {"Rpm": 2400.5, "Temp": 85, "Speed": 123.45,
                  "Angle": -45, "Flag": 1}
        frame = encode_frame(db, MID, values)
        show_frame("full mixed-endian message", MID, frame)
        decoded = decode_frame(db, MID, frame)
        self.assertAlmostEqual(decoded["Rpm"], 2400.5)
        self.assertEqual(decoded["Temp"], 85.0)
        self.assertAlmostEqual(decoded["Speed"], 123.45, places=2)
        self.assertEqual(decoded["Angle"], -45.0)
        self.assertEqual(decoded["Flag"], 1.0)

    def test_raw_wrapper_roundtrip(self):
        db = make_db(' SG_ S : 0|16@1+ (0.5,10) [0|0] "" N\n', mid=MID)
        frame = encode_frame(db, MID, {"S": Raw(1234)})
        show_frame("raw wrapper encode", MID, frame)
        self.assertEqual(decode_frame_raw(db, MID, frame)[1]["S"], 1234)

    def test_hex_string_decode_input(self):
        db = make_db(' SG_ S : 0|16@1+ (1,0) [0|0] "" N\n', mid=MID)
        frame = encode_frame(db, MID, {"S": Raw(0xABCD)})
        self.assertEqual(decode_frame_raw(db, MID, frame.hex())[1]["S"], 0xABCD)
        show_frame("hex string decode", MID, frame)


if __name__ == "__main__":
    unittest.main(verbosity=2)
