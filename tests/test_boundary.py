"""Boundary value tests: min/max raw and physical limits, error paths."""

import unittest

from tests._helpers import make_db, show_frame
from can_tool import encode_frame, decode_frame, Raw
from can_tool.errors import EncodeError

MID = 0x300


class BoundaryTests(unittest.TestCase):
    def test_unsigned_boundaries(self):
        db = make_db(' SG_ S : 0|8@1+ (1,0) [0|255] "" N\n', mid=MID)
        for value, hexs in [(0, "00"), (255, "FF")]:
            frame = encode_frame(db, MID, {"S": value})
            show_frame(f"u8 boundary {value}", MID, frame)
            self.assertEqual(frame[0:1], bytes.fromhex(hexs))

    def test_signed_boundaries(self):
        db = make_db(' SG_ S : 0|16@1- (1,0) [-32768|32767] "" N\n',
                     mid=MID)
        for value, hexs in [(-32768, "0080"), (32767, "FF7F")]:
            frame = encode_frame(db, MID, {"S": value})
            show_frame(f"s16 boundary {value}", MID, frame)
            self.assertEqual(frame[0:2], bytes.fromhex(hexs))
            self.assertEqual(decode_frame(db, MID, frame)["S"], float(value))

    def test_scaled_physical_boundaries(self):
        # 0.25 rpm: physical max = 0x3FFF * 0.25 = 4095.75
        db = make_db(' SG_ S : 0|14@1+ (0.25,0) [0|4095.75] "rpm" N\n',
                     mid=MID)
        frame = encode_frame(db, MID, {"S": 4095.75})
        show_frame("scaled upper boundary 4095.75 rpm", MID, frame)
        # raw 16383 = 0x3FFF little-endian at bits 0..13
        self.assertEqual(frame[0:2], bytes.fromhex("FF3F"))
        frame0 = encode_frame(db, MID, {"S": 0.0})
        self.assertEqual(frame0[0:2], b"\x00\x00")

    def test_raw_above_max_rejected(self):
        db = make_db(' SG_ S : 0|8@1+ (1,0) [0|255] "" N\n', mid=MID)
        with self.assertRaises(EncodeError) as ctx:
            encode_frame(db, MID, {"S": Raw(256)})
        self.assertIn("outside", str(ctx.exception))
        print(f"    [boundary raw>max] {ctx.exception}")
        with self.assertRaises(EncodeError) as ctx:
            encode_frame(db, MID, {"S": Raw(-1)})
        self.assertIn("outside", str(ctx.exception))
        print(f"    [boundary raw<min] {ctx.exception}")

    def test_physical_above_range_rejected(self):
        db = make_db(' SG_ S : 0|8@1+ (1,0) [0|100] "%" N\n', mid=MID)
        with self.assertRaises(EncodeError) as ctx:
            encode_frame(db, MID, {"S": 100.5})
        self.assertIn("above DBC maximum", str(ctx.exception))
        print(f"    [boundary phys>max] {ctx.exception}")
        with self.assertRaises(EncodeError) as ctx:
            encode_frame(db, MID, {"S": -0.5})
        self.assertIn("below DBC minimum", str(ctx.exception))
        print(f"    [boundary phys<min] {ctx.exception}")

    def test_unsigned_physical_overflow_rejected(self):
        db = make_db(' SG_ S : 0|8@1+ (1,0) [0|0] "" N\n', mid=MID)
        with self.assertRaises(EncodeError) as ctx:
            encode_frame(db, MID, {"S": 300})
        self.assertIn("outside the 8-bit unsigned range", str(ctx.exception))
        print(f"    [boundary overflow] {ctx.exception}")

    def test_signed_physical_overflow_rejected(self):
        db = make_db(' SG_ S : 0|8@1- (1,-40) [0|0] "degC" N\n',
                     mid=MID)
        with self.assertRaises(EncodeError) as ctx:
            encode_frame(db, MID, {"S": 88})
        self.assertIn("8-bit signed range", str(ctx.exception))
        print(f"    [boundary signed overflow] {ctx.exception}")

    def test_value_off_quantization_grid_rejected(self):
        db = make_db(' SG_ S : 0|16@1+ (0.25,0) [0|16383.75] "rpm" N\n',
                     mid=MID)
        # 1/8 rpm cannot be expressed in 0.25 steps
        with self.assertRaises(EncodeError) as ctx:
            encode_frame(db, MID, {"S": 1.125})
        self.assertIn("cannot be exactly represented", str(ctx.exception))
        print(f"    [boundary quantization] {ctx.exception}")

    def test_grid_value_round_trips(self):
        db = make_db(' SG_ S : 0|16@1+ (0.25,0) [0|16383.75] "rpm" N\n',
                     mid=MID)
        for rpm in (0.25, 1.0, 123.75, 16383.75):
            frame = encode_frame(db, MID, {"S": rpm})
            self.assertAlmostEqual(decode_frame(db, MID, frame)["S"], rpm)
            show_frame(f"grid {rpm} rpm", MID, frame)

    def test_nan_and_inf_rejected(self):
        db = make_db(' SG_ S : 0|8@1+ (1,0) [0|255] "" N\n', mid=MID)
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(EncodeError) as ctx:
                encode_frame(db, MID, {"S": bad})
            self.assertIn("finite", str(ctx.exception))
            print(f"    [boundary {bad}] rejected")

    def test_non_numeric_rejected(self):
        db = make_db(' SG_ S : 0|8@1+ (1,0) [0|255] "" N\n', mid=MID)
        with self.assertRaises(EncodeError) as ctx:
            encode_frame(db, MID, {"S": "hot"})
        self.assertIn("must be a number", str(ctx.exception))
        print(f"    [boundary non-numeric] {ctx.exception}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
