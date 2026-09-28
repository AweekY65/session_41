"""Tests for malformed DBCs and invalid definitions.

Every case must produce a clear, specific diagnostic - never a raw
stack trace or a silent acceptance.
"""

import unittest

from can_tool.parser import parse_dbc_text
from can_tool import encode_frame, decode_frame_raw
from can_tool.errors import (
    DbcParseError,
    DbcValidationError,
    EncodeError,
    DecodeError,
)
from tests._helpers import show_frame

BASE = 'VERSION ""\nNS_ :\nBS_:\nBU_: N\n'


def dbc(body):
    return BASE + body


class CorruptDbcTests(unittest.TestCase):
    def _expect(self, text, fragment, exc=DbcParseError):
        with self.assertRaises(exc) as ctx:
            parse_dbc_text(text)
        message = str(ctx.exception)
        self.assertIn(fragment, message,
                      msg=f"expected {fragment!r} in {message!r}")
        print(f"    [invalid dbc] {message}")

    def test_malformed_signal_row(self):
        self._expect(
            dbc("BO_ 100 M: 8 N\n SG_ S 0|8@1+ (1,0) [0|0] \"\" N\n"),
            "malformed signal definition",
        )

    def test_signal_outside_message(self):
        self._expect(
            dbc(' SG_ S : 0|8@1+ (1,0) [0|0] "" N\n'),
            "outside of any BO_",
        )

    def test_garbled_scale(self):
        self._expect(
            dbc("BO_ 100 M: 8 N\n SG_ S : 0|8@1+ (x,0) [0|0] \"\" N\n"),
            "invalid scale",
        )

    def test_garbled_bo_row(self):
        self._expect(
            dbc("BO_ notanumber M: 8 N\n"),
            "invalid integer",
        )

    def test_garbled_bo_syntax(self):
        self._expect(
            dbc("BO_ 100 M 8 N\n"),
            "malformed message definition",
        )

    def test_garbled_mul_range(self):
        self._expect(
            dbc("BO_ 100 M: 8 N\n"
                ' SG_ Mode M : 0|4@1+ (1,0) [0|0] "" N\n'
                ' SG_ A m0 : 8|8@1+ (1,0) [0|0] "" N\n'
                "SG_MUL_VAL_ 100 A Mode 5-x;\n"),
            "invalid integer",
        )

    def test_mul_range_unknown_multiplexor(self):
        self._expect(
            dbc("BO_ 100 M: 8 N\n"
                ' SG_ A m0 : 8|8@1+ (1,0) [0|0] "" N\n'
                "SG_MUL_VAL_ 100 A Mode 5;\n"),
            "unknown multiplexor",
        )


class ValidationTests(unittest.TestCase):
    def _expect(self, text, fragment):
        with self.assertRaises(DbcValidationError) as ctx:
            parse_dbc_text(text)
        self.assertIn(fragment, str(ctx.exception))
        print(f"    [invalid definition] {ctx.exception}")

    def test_duplicate_message_id(self):
        self._expect(
            dbc("BO_ 100 A: 8 N\n SG_ x : 0|8@1+ (1,0) [0|0] \"\" N\n"
                "BO_ 100 B: 8 N\n SG_ y : 0|8@1+ (1,0) [0|0] \"\" N\n"),
            "duplicate message id",
        )

    def test_duplicate_signal_name(self):
        self._expect(
            dbc("BO_ 100 M: 8 N\n"
                ' SG_ S : 0|8@1+ (1,0) [0|0] "" N\n'
                ' SG_ S : 8|8@1+ (1,0) [0|0] "" N\n'),
            "duplicate signal name",
        )

    def test_bit_runs_past_dlc_intel(self):
        self._expect(
            dbc("BO_ 100 M: 2 N\n"
                ' SG_ S : 8|16@1+ (1,0) [0|0] "" N\n'),
            "exceeds DLC 2",
        )

    def test_bit_runs_past_dlc_motorola(self):
        # 56|8@0 wraps the sawtooth into byte 8 - invalid in an 8-byte DLC
        self._expect(
            dbc("BO_ 100 M: 8 N\n"
                ' SG_ S : 56|8@0+ (1,0) [0|0] "" N\n'),
            "exceeds DLC 8",
        )

    def test_signal_length_outside_1_64(self):
        self._expect(
            dbc("BO_ 100 M: 8 N\n"
                ' SG_ S : 0|0@1+ (1,0) [0|0] "" N\n'),
            "length 0 outside 1-64",
        )

    def test_zero_scale(self):
        self._expect(
            dbc("BO_ 100 M: 8 N\n"
                ' SG_ S : 0|8@1+ (0,0) [0|0] "" N\n'),
            "scale must be non-zero",
        )

    def test_dlc_outside_classic_range(self):
        self._expect(
            dbc('BO_ 100 M: 12 N\n SG_ S : 0|8@1+ (1,0) [0|0] "" N\n'),
            "DLC 12 is outside the classic CAN range 0-8",
        )

    def test_static_overlap_detected(self):
        self._expect(
            dbc("BO_ 100 M: 8 N\n"
                ' SG_ A : 0|12@1+ (1,0) [0|0] "" N\n'
                ' SG_ B : 8|8@1+ (1,0) [0|0] "" N\n'),
            "overlap",
        )

    def test_motorola_overlap_detected(self):
        self._expect(
            dbc("BO_ 100 M: 8 N\n"
                ' SG_ A : 7|16@0+ (1,0) [0|0] "" N\n'
                ' SG_ B : 8|8@1+ (1,0) [0|0] "" N\n'),
            "overlap",
        )

    def test_muxed_without_multiplexor(self):
        self._expect(
            dbc("BO_ 100 M: 8 N\n"
                ' SG_ A m0 : 0|8@1+ (1,0) [0|0] "" N\n'),
            "without a multiplexor",
        )

    def test_multiple_multiplexors(self):
        self._expect(
            dbc("BO_ 100 M: 8 N\n"
                ' SG_ A M : 0|4@1+ (1,0) [0|0] "" N\n'
                ' SG_ B M : 4|4@1+ (1,0) [0|0] "" N\n'),
            "multiple multiplexor",
        )

    def test_muxed_signals_overlapping_for_same_value(self):
        self._expect(
            dbc("BO_ 100 M: 8 N\n"
                ' SG_ Mode M : 0|4@1+ (1,0) [0|0] "" N\n'
                ' SG_ A m0 : 8|16@1+ (1,0) [0|0] "" N\n'
                ' SG_ B m0 : 8|16@1+ (1,0) [0|0] "" N\n'),
            "overlap",
        )

    def test_muxed_signals_same_bits_different_values_are_allowed(self):
        db = parse_dbc_text(dbc(
            "BO_ 100 M: 8 N\n"
            ' SG_ Mode M : 0|4@1+ (1,0) [0|0] "" N\n'
            ' SG_ A m0 : 8|16@1+ (1,0) [0|0] "" N\n'
            ' SG_ B m1 : 8|16@1+ (1,0) [0|0] "" N\n'))
        names = [s.name for s in db.messages[0].signals]
        self.assertEqual(names, ["Mode", "A", "B"])
        print("    [mux same bits different value] accepted, as required")


class FrameLevelErrorTests(unittest.TestCase):
    def setUp(self):
        self.db = parse_dbc_text(dbc(
            "BO_ 100 M: 8 N\n"
            ' SG_ S : 0|8@1+ (1,0) [0|255] "" N\n'))

    def test_decode_wrong_dlc(self):
        with self.assertRaises(DecodeError) as ctx:
            decode_frame_raw(self.db, 100, bytes.fromhex("0102"))
        self.assertIn("DLC mismatch", str(ctx.exception))
        print(f"    [wrong DLC] {ctx.exception}")

    def test_decode_unknown_id(self):
        with self.assertRaises(DecodeError) as ctx:
            decode_frame_raw(self.db, 0x7FF, bytes(8))
        self.assertIn("no message with id", str(ctx.exception))
        print(f"    [unknown id] {ctx.exception}")

    def test_encode_unknown_message(self):
        with self.assertRaises(EncodeError) as ctx:
            encode_frame(self.db, "Nope", {"S": 1})
        self.assertIn("no message", str(ctx.exception))
        print(f"    [unknown message] {ctx.exception}")

    def test_lenient_dlc_accepts_shorter_frame(self):
        # strict=False: padding/truncation tolerated instead of erroring
        phys = decode_frame_raw(self.db, 100, bytes.fromhex("2A"),
                                strict=False)[0]
        show_frame("lenient decode of 1-byte frame", 100, bytes.fromhex("2A"))
        self.assertEqual(phys["S"], 42.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
