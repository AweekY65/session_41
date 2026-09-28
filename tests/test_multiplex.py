"""Multiplexed signal tests (basic inline mux + SG_MUL_VAL_ ranges)."""

import unittest

from tests._helpers import make_db, show_frame
from can_tool import encode_frame, decode_frame, decode_frame_raw
from can_tool.errors import EncodeError, DecodeError

MID = 0x200

MUX_DBC = """\
 SG_ Mode M : 0|4@1+ (1,0) [0|15] "" N
 SG_ Voltage m0 : 8|16@1+ (0.001,0) [0|65.535] "V" N
 SG_ Current m0 : 24|16@1- (0.001,0) [-32.768|32.767] "A" N
 SG_ Pressure m1 : 23|16@0+ (0.01,0) [0|655.35] "kPa" N
 SG_ PumpRpm m1 : 39|16@0+ (1,0) [0|65535] "rpm" N
 SG_ ErrorCode m2 : 8|12@1+ (1,0) [0|4095] "" N
"""


class MultiplexTests(unittest.TestCase):
    def setUp(self):
        self.db = make_db(MUX_DBC, mid=MID, dlc=8)

    def test_mode0_selects_electrical_signals(self):
        frame = encode_frame(self.db, MID, {
            "Mode": 0, "Voltage": 13.7, "Current": -5.123})
        show_frame("mux mode 0 (electrical)", MID, frame)
        self.assertEqual(frame[0], 0x00)
        decoded = decode_frame(self.db, MID, frame)
        self.assertEqual(set(decoded), {"Mode", "Voltage", "Current"})
        self.assertAlmostEqual(decoded["Voltage"], 13.7, places=3)
        self.assertAlmostEqual(decoded["Current"], -5.123, places=3)

    def test_mode1_selects_pump_signals(self):
        frame = encode_frame(self.db, MID, {
            "Mode": 1, "Pressure": 400.0, "PumpRpm": 3000})
        show_frame("mux mode 1 (pump)", MID, frame)
        self.assertEqual(frame[0], 0x01)
        decoded = decode_frame(self.db, MID, frame)
        self.assertEqual(set(decoded), {"Mode", "Pressure", "PumpRpm"})
        self.assertAlmostEqual(decoded["Pressure"], 400.0, places=2)
        self.assertEqual(decoded["PumpRpm"], 3000.0)

    def test_mode2_selects_error_code(self):
        frame = encode_frame(self.db, MID, {"Mode": 2, "ErrorCode": 4095})
        show_frame("mux mode 2 (error)", MID, frame)
        decoded = decode_frame(self.db, MID, frame)
        self.assertEqual(set(decoded), {"Mode", "ErrorCode"})
        self.assertEqual(decoded["ErrorCode"], 4095.0)

    def test_encoding_inactive_signal_rejected(self):
        with self.assertRaises(EncodeError) as ctx:
            encode_frame(self.db, MID, {"Mode": 1, "Voltage": 12.0})
        self.assertIn("Voltage", str(ctx.exception))
        print(f"    [mux inactive rejection] {ctx.exception}")

    def test_missing_required_active_signal_rejected(self):
        with self.assertRaises(EncodeError) as ctx:
            encode_frame(self.db, MID, {"Mode": 0, "Voltage": 12.0})
        self.assertIn("Current", str(ctx.exception))
        print(f"    [mux missing rejection] {ctx.exception}")

    def test_missing_multiplexor_rejected(self):
        with self.assertRaises(EncodeError) as ctx:
            encode_frame(self.db, MID, {"Voltage": 12.0, "Current": 1.0})
        self.assertIn("multiplexor", str(ctx.exception))
        print(f"    [mux switch rejection] {ctx.exception}")

    def test_same_payload_bits_mean_different_things_by_mode(self):
        """The classic multiplex property: identical signal bits in the
        payload decode to different signal names depending on Mode."""
        f0 = encode_frame(self.db, MID, {"Mode": 0,
                                         "Voltage": 1.0, "Current": 0.0})
        # mode 1 frame that happens to share the m0 data bytes
        f1 = bytearray(f0)
        f1[0] = 0x01
        d0 = decode_frame(self.db, MID, bytes(f0))
        d1 = decode_frame(self.db, MID, bytes(f1))
        show_frame("mux shared payload mode 0", MID, bytes(f0))
        show_frame("mux shared payload mode 1", MID, bytes(f1))
        self.assertIn("Voltage", d0)
        self.assertIn("Pressure", d1)
        self.assertNotIn("Voltage", d1)


class ExtendedMuxRangeTests(unittest.TestCase):
    """SG_MUL_VAL_ range tables: a signal active for mux 3-5,7."""

    DBC = (
        ' SG_ Mode M : 0|4@1+ (1,0) [0|15] "" N\n'
        ' SG_ Lo m0 : 8|8@1+ (1,0) [0|255] "" N\n'
        ' SG_ Mid m3 : 8|8@1+ (1,0) [0|255] "" N\n'
        f"SG_MUL_VAL_ {MID} Mid Mode 3-5,7;\n"
    )

    def test_range_membership(self):
        db = make_db(self.DBC, mid=MID)
        mid_sig = db.messages[0].get("Mid")
        self.assertTrue(mid_sig.matches_mux_value(3))
        self.assertTrue(mid_sig.matches_mux_value(5))
        self.assertTrue(mid_sig.matches_mux_value(7))
        self.assertFalse(mid_sig.matches_mux_value(6))
        self.assertFalse(mid_sig.matches_mux_value(0))
        frame = encode_frame(db, MID, {"Mode": 4, "Mid": 0x5A})
        show_frame("range mux mode 4 -> Mid", MID, frame)
        self.assertEqual(decode_frame_raw(db, MID, frame)[1]["Mid"], 0x5A)
        frame7 = encode_frame(db, MID, {"Mode": 7, "Mid": 0x6B})
        show_frame("range mux mode 7 -> Mid", MID, frame7)
        self.assertEqual(decode_frame_raw(db, MID, frame7)[1]["Mid"], 0x6B)


if __name__ == "__main__":
    unittest.main(verbosity=2)
