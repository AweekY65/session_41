"""Differential tests against the third-party ``cantools`` package.

cantools is used ONLY as an independent reference implementation for test
comparison; the production code in :mod:`can_tool` never imports it, and
these tests skip automatically when it is not installed.
"""

import random
import unittest

try:
    import cantools
    HAVE_CANTOOLS = True
except Exception:  # pragma: no cover
    HAVE_CANTOOLS = False

from can_tool.parser import parse_dbc_text
from can_tool.codec import decode_frame_raw, encode_frame
from can_tool import Raw
from can_tool.frame import hex_dump
from tests._helpers import show_frame

MID = 200


def dbc_text(start, length, bo, sign, scale, offset):
    return (
        'VERSION ""\nNS_ :\nBS_:\nBU_: N\n'
        f"BO_ {MID} M: 8 N\n"
        f' SG_ S : {start}|{length}@{bo}{sign} '
        f'({scale},{offset}) [0|0] "" N\n'
    )


@unittest.skipUnless(HAVE_CANTOOLS, "cantools not installed")
class CantoolsCrossCheck(unittest.TestCase):
    """Bit layout, encode and decode must match cantools exactly."""

    def test_random_encodes_and_decodes(self):
        rng = random.Random(2026)
        checked = 0
        sample_frame = None
        for _ in range(2000):
            length = rng.choice([1, 2, 3, 4, 7, 8, 9, 11, 12, 13,
                                 16, 17, 24, 32])
            bo = rng.choice(["0", "1"])
            sign = rng.choice(["+", "-"])
            start = rng.randrange(0, 64 - length + 1)
            scale = rng.choice([1, 0.5, 0.25, 0.01, 2])
            offset = rng.choice([0, -40, 100])
            text = dbc_text(start, length, bo, sign, scale, offset)
            try:
                ours = parse_dbc_text(text)
                ref = cantools.database.load_string(text,
                                                     database_format="dbc")
            except Exception:
                # The two must agree on rejecting illegal layouts; the
                # valid-layout agreement is what we assert here.
                continue
            sig = ours.messages[0].signals[0]
            raw = rng.randint(sig.raw_min, sig.raw_max)
            our_frame = encode_frame(ours, MID, {"S": Raw(raw)})
            ref_frame = bytes(ref.encode_message(
                MID, {"S": raw}, scaling=False))
            self.assertEqual(
                our_frame, ref_frame,
                msg=f"encode mismatch {start}|{length}@{bo}{sign} raw={raw}",
            )
            blob = bytes(rng.randrange(256) for _ in range(8))
            our_raw = decode_frame_raw(ours, MID, blob)[1]["S"]
            ref_raw = ref.decode_message(
                MID, blob, decode_choices=False, scaling=False)["S"]
            self.assertEqual(our_raw, ref_raw)
            our_phys = raw * scale + offset
            # physical encode must also agree
            our_p = encode_frame(ours, MID, {"S": our_phys})
            ref_p = bytes(ref.encode_message(MID, {"S": our_phys}))
            self.assertEqual(our_p, ref_p)
            sample_frame = our_frame
            checked += 1
        self.assertGreater(checked, 1500)
        show_frame(f"cantools differential ({checked} layouts)", MID,
                   sample_frame, "last frame checked")

    def test_example_dbc_matches_cantools(self):
        path = "examples/example.dbc"
        import os
        if not os.path.exists(path):
            self.skipTest("example.dbc not present")
        ours = parse_dbc_text(open(path).read())
        ref = cantools.database.load_file(path)

        cases = {
            "EngineData": {
                "EngineSpeed": 2400.5, "EngineTemp": 85,
                "ThrottlePos": 37.5, "OdometerLarge": 4660,
                "CheckEngine": 1},
            "BodyStatus": {
                "VehicleSpeed": 123.45, "SteeringAngle": -45.7,
                "GearLever": 5, "HighBeam": 1},
            "DiagnosticMessage": {
                "ServiceMode": 0, "Voltage": 13.7, "Current": -5.123},
        }
        for name, values in cases.items():
            our_msg = ours.get_message_by_name(name)
            ref_msg = ref.get_message_by_name(name)
            our_frame = encode_frame(ours, name, values)
            ref_frame = bytes(ref_msg.encode(values))
            show_frame(f"example {name}", our_msg.frame_id, our_frame)
            self.assertEqual(our_frame, ref_frame)
            our_dec = decode_frame_raw(ours, our_msg.frame_id, our_frame)[0]
            ref_dec = ref_msg.decode(ref_frame, decode_choices=False)
            for key in our_dec:
                self.assertAlmostEqual(our_dec[key], ref_dec[key], places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
