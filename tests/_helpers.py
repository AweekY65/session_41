"""Shared helpers for the test suite."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from can_tool.parser import parse_dbc_text  # noqa: E402
from can_tool.frame import hex_dump  # noqa: E402

HEADER = "\n" + "=" * 72 + "\n{title}\n" + "-" * 72


def make_db(signals_text, mid=100, name="M", dlc=8, header=""):
    """Build a one-message in-memory DBC from SG_ rows."""
    dbc = (
        'VERSION ""\n'
        "NS_ :\n"
        "BS_:\n"
        "BU_: N\n"
        f"{header}"
        f"BO_ {mid} {name}: {dlc} N\n"
        f"{signals_text}\n"
    )
    return parse_dbc_text(dbc)


def show_frame(testcase, frame_id, payload, note=""):
    """Print the hex frame that a test just asserted on."""
    print(f"    [{testcase}] id=0x{frame_id:X} {hex_dump(payload)} {note}")
