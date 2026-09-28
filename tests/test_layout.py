"""Intel/Motorola layout, cross-byte and signed tests.

Every test prints the hex frame it checks. Expected bytes are computed by
hand from the DBC sawtooth bit-numbering rules.
"""

import unittest

from tests._helpers import make_db, show_frame
from can_tool import encode_frame, decode_frame_raw, Raw
from can_tool.frame import hex_dump

MID = 100


class IntelLayoutTests(unittest.TestCase):
    def test_byte_aligned_16bit(self):
        """0|16@1: little endian, value 0x3412 -> 12 34 ..."""
        db = make_db(' SG_ S : 0|16@1+ (1,0) [0|0] "" N\n')
        frame = encode_frame(db, MID, {"S": Raw(0x3412)})
        show_frame("Intel 0|16", MID, frame)
        self.assertEqual(frame[:2], bytes.fromhex("1234"))
        self.assertEqual(decode_frame_raw(db, MID, frame)[1]["S"], 0x3412)

    def test_cross_byte_9bit(self):
        """7|9@1: 1 bit in byte 0 (wire 7), 8 bits in byte 1."""
        db = make_db(' SG_ S : 7|9@1+ (1,0) [0|0] "" N\n')
        # raw = 0x101 -> low bit at linear 7 (byte0 wire7),
        # high byte 0x01 at byte 1 (linear 8..15).
        frame = encode_frame(db, MID, {"S": Raw(0x101)})
        show_frame("Intel 7|9 raw=0x101", MID, frame)
        self.assertEqual(frame[:2], bytes.fromhex("8080"))
        # raw = 0x0FE -> byte0 bit7=0, byte1 = 0x7F
        frame2 = encode_frame(db, MID, {"S": Raw(0x0FE)})
        show_frame("Intel 7|9 raw=0x0FE", MID, frame2)
        self.assertEqual(frame2[:2], bytes.fromhex("007F"))
        self.assertEqual(decode_frame_raw(db, MID, frame2)[1]["S"], 0x0FE)

    def test_cross_byte_offset_13_8bit(self):
        """13|8@1 starts mid byte 1 and ends mid byte 2."""
        db = make_db(' SG_ S : 13|8@1+ (1,0) [0|0] "" N\n')
        frame = encode_frame(db, MID, {"S": Raw(0xD7)})
        show_frame("Intel 13|8 raw=0xD7", MID, frame)
        # raw 0xD7 = 11010111 -> low 3 bits 0x7 at linear 13..15
        # (byte1 wire 5..7 -> 0xE0), high 5 bits 0x1A at linear
        # 16..20 (byte2 wire 0..4 -> 0x1A).
        self.assertEqual(frame[1], 0xE0)
        self.assertEqual(frame[2], 0x1A)
        self.assertEqual(decode_frame_raw(db, MID, frame)[1]["S"], 0xD7)


class MotorolaLayoutTests(unittest.TestCase):
    def test_byte_aligned_16bit(self):
        """7|16@0: classic big endian, 0x1234 -> 12 34."""
        db = make_db(' SG_ S : 7|16@0+ (1,0) [0|0] "" N\n')
        frame = encode_frame(db, MID, {"S": Raw(0x1234)})
        show_frame("Motorola 7|16 raw=0x1234", MID, frame)
        self.assertEqual(frame[:2], bytes.fromhex("1234"))
        self.assertEqual(decode_frame_raw(db, MID, frame)[1]["S"], 0x1234)

    def test_start8_16bit_sawtooth(self):
        """8|16@0: MSB sits at linear bit 8 (byte 1 wire bit 0); a
        non-byte-aligned Motorola field wraps the sawtooth twice."""
        db = make_db(' SG_ S : 8|16@0+ (1,0) [0|0] "" N\n')
        frame = encode_frame(db, MID, {"S": Raw(0x8001)})
        show_frame("Motorola 8|16 raw=0x8001", MID, frame)
        # Linear walk, value MSB->LSB (verified bit by bit against
        # cantools): 8 | 23 22 21 20 19 18 17 16 | 31 30 29 28 27 26 25
        #   val bit15 -> linear 8  = byte1 wire0 -> byte1 = 0x01
        #   val bit0  -> linear 25 = byte3 wire1 -> byte3 = 0x02
        self.assertEqual(frame[1], 0x01)
        self.assertEqual(frame[2], 0x00)
        self.assertEqual(frame[3], 0x02)
        self.assertEqual(decode_frame_raw(db, MID, frame)[1]["S"], 0x8001)

        frame2 = encode_frame(db, MID, {"S": Raw(0xFFFF)})
        show_frame("Motorola 8|16 raw=0xFFFF", MID, frame2)
        self.assertEqual(frame2[1:4], bytes.fromhex("01FFFE"))
        self.assertEqual(decode_frame_raw(db, MID, frame2)[1]["S"], 0xFFFF)

    def test_12bit_cross_byte(self):
        """12|12@0 straddles bytes 1 and 2 diagonally."""
        db = make_db(' SG_ S : 12|12@0+ (1,0) [0|0] "" N\n')
        frame = encode_frame(db, MID, {"S": Raw(0xABC)})
        show_frame("Motorola 12|12 raw=0xABC", MID, frame)
        # Saw positions, MSB->LSB: 12 11 10 9 8 | 15 14 13 12 11 10 9
        #   val bits11..7 (10101) -> byte1 wire 4..0 -> byte1 = 0x15
        #   val bits6..0  (0111100) -> byte2 wire7..1 -> byte2 = 0x78
        self.assertEqual(frame[1], 0x15)
        self.assertEqual(frame[2], 0x78)
        self.assertEqual(decode_frame_raw(db, MID, frame)[1]["S"], 0xABC)

    def test_8bit_byte_aligned(self):
        """7|8@0 is a plain byte."""
        db = make_db(' SG_ S : 7|8@0+ (1,0) [0|0] "" N\n')
        frame = encode_frame(db, MID, {"S": Raw(0xC3)})
        show_frame("Motorola 7|8 raw=0xC3", MID, frame)
        self.assertEqual(frame[0], 0xC3)

    def test_signed_motorola_negative(self):
        """39|16@0- negative value two's complement."""
        db = make_db(' SG_ S : 39|16@0- (1,0) [0|0] "" N\n')
        frame = encode_frame(db, MID, {"S": Raw(-1)})
        show_frame("Motorola 39|16 signed=-1", MID, frame)
        # Linear walk MSB->LSB: 39..32 then 47..40, i.e. byte4 wire7..0
        # holds val bits15..8 and byte5 wire7..0 holds val bits7..0.
        # All ones -> bytes 4 and 5 are FF.
        self.assertEqual(frame[4:6], bytes.fromhex("FFFF"))
        self.assertEqual(decode_frame_raw(db, MID, frame)[1]["S"], -1)
        frame2 = encode_frame(db, MID, {"S": Raw(-32768)})
        show_frame("Motorola 39|16 signed=-32768", MID, frame2)
        # only val bit15 set -> linear 39 = byte4 wire7
        self.assertEqual(frame2[4:6], bytes.fromhex("8000"))
        self.assertEqual(decode_frame_raw(db, MID, frame2)[1]["S"], -32768)


class SignedTests(unittest.TestCase):
    def test_signed_intel_negative(self):
        db = make_db(' SG_ S : 0|8@1- (1,0) [0|0] "" N\n')
        for raw, byte in [(-1, "FF"), (-128, "80"), (127, "7F"), (-5, "FB")]:
            frame = encode_frame(db, MID, {"S": Raw(raw)})
            show_frame(f"Intel 0|8 signed={raw}", MID, frame)
            self.assertEqual(frame[0:1], bytes.fromhex(byte))
            self.assertEqual(decode_frame_raw(db, MID, frame)[1]["S"], raw)

    def test_signed_intel_16bit_minmax(self):
        db = make_db(' SG_ S : 0|16@1- (1,0) [0|0] "" N\n')
        for raw, hexs in [(-32768, "0080"), (32767, "FF7F"), (-4660, "CCED")]:
            frame = encode_frame(db, MID, {"S": Raw(raw)})
            show_frame(f"Intel 0|16 signed={raw}", MID, frame)
            self.assertEqual(frame[0:2], bytes.fromhex(hexs))
            self.assertEqual(decode_frame_raw(db, MID, frame)[1]["S"], raw)

    def test_unsigned_never_sign_extends(self):
        db = make_db(' SG_ S : 0|8@1+ (1,0) [0|0] "" N\n')
        frame = encode_frame(db, MID, {"S": Raw(255)})
        show_frame("Intel 0|8 unsigned=255", MID, frame)
        self.assertEqual(frame[0], 0xFF)
        self.assertEqual(decode_frame_raw(db, MID, frame)[1]["S"], 255)


class ScaleOffsetTests(unittest.TestCase):
    def test_scale_quarter_rpm(self):
        db = make_db(' SG_ S : 0|16@1+ (0.25,0) [0|16383.75] "rpm" N\n')
        frame = encode_frame(db, MID, {"S": 2400.5})
        show_frame("scale 0.25 -> 2400.5 rpm", MID, frame)
        self.assertEqual(frame[0:2], bytes.fromhex("8225"))  # raw 9602
        phys, raw = decode_frame_raw(db, MID, frame)
        self.assertEqual(raw["S"], 9602)
        self.assertAlmostEqual(phys["S"], 2400.5)

    def test_offset_minus40(self):
        db = make_db(' SG_ S : 0|8@1- (1,-40) [-40|87] "degC" N\n')
        frame = encode_frame(db, MID, {"S": 85})
        show_frame("offset -40 -> 85 degC", MID, frame)
        self.assertEqual(frame[0], 125)
        phys, raw = decode_frame_raw(db, MID, frame)
        self.assertEqual(raw["S"], 125)
        self.assertEqual(phys["S"], 85.0)
        frame_cold = encode_frame(db, MID, {"S": -40})
        self.assertEqual(frame_cold[0], 0)
        show_frame("offset -40 -> -40 degC", MID, frame_cold)

    def test_signed_scaled_negative(self):
        db = make_db(' SG_ S : 7|16@0- (0.1,0) [-3276.8|3276.7] "deg" N\n')
        frame = encode_frame(db, MID, {"S": -45.7})
        show_frame("Motorola signed scale -45.7 deg", MID, frame)
        phys, raw = decode_frame_raw(db, MID, frame)
        self.assertEqual(raw["S"], -457)
        self.assertAlmostEqual(phys["S"], -45.7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
