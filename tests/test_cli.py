"""End-to-end tests for the command line front-end."""

import io
import unittest
from contextlib import redirect_stdout, redirect_stderr

from can_tool.cli import main


DBC = "examples/example.dbc"


class CliTests(unittest.TestCase):
    def _run(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def test_info_lists_messages_and_signals(self):
        rc, out, err = self._run("info", DBC)
        self.assertEqual(rc, 0)
        self.assertIn("EngineData", out)
        self.assertIn("Motorola", out)
        self.assertIn("Intel", out)
        self.assertIn("DLC=8", out)
        print(out.strip().splitlines()[0])

    def test_encode_prints_hex_frame(self):
        rc, out, err = self._run(
            "encode", "--dbc", DBC, "--message", "EngineData",
            "--set", "EngineSpeed=2400.5", "--set", "EngineTemp=85",
            "--set", "ThrottlePos=37.5", "--set", "OdometerLarge=4660",
            "--set", "CheckEngine=1")
        self.assertEqual(rc, 0, msg=err)
        self.assertIn("82 25 7D 77 01 34 12 01", out)
        print("    [cli encode]", out.strip().splitlines()[-1])

    def test_decode_prints_signals(self):
        rc, out, err = self._run(
            "decode", "--dbc", DBC, "--id", "0x100",
            "--data", "82 25 7D 77 01 34 12 01")
        self.assertEqual(rc, 0, msg=err)
        self.assertIn("EngineSpeed", out)
        self.assertIn("2400.5", out)
        print("    [cli decode] frame parsed to physical values")

    def test_encode_error_returns_code_2(self):
        rc, out, err = self._run(
            "encode", "--dbc", DBC, "--message", "EngineData",
            "--set", "EngineSpeed=2400.5", "--set", "EngineTemp=999",
            "--set", "ThrottlePos=37.5", "--set", "OdometerLarge=4660",
            "--set", "CheckEngine=0")
        self.assertEqual(rc, 2)
        self.assertTrue("outside" in err or "maximum" in err)
        print(f"    [cli error] {err.strip()}")

    def test_mux_encode_via_raw_switch(self):
        rc, out, err = self._run(
            "encode", "--dbc", DBC, "--message", "DiagnosticMessage",
            "--set", "ServiceMode=r2", "--set", "ErrorCode=4095")
        self.assertEqual(rc, 0, msg=err)
        self.assertIn("02 FF 0F 00 00 00 00 00", out)
        print("    [cli mux raw]", out.strip().splitlines()[-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
