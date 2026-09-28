"""Run the whole test suite without pytest: ``python run_tests.py``.

Every check prints a PASS/FAIL line and hex CAN frames are rendered
inline; the process exits non-zero if anything failed.
"""

import sys

from tests import (
    test_layout,
    test_decode,
    test_encode,
    test_mux,
    test_errors,
    test_cantools_xcheck,
)

SUITES = [
    ("bit layout (endianness, cross-byte, bounds)", test_layout.run),
    ("decode (signed, scale/offset, known vectors)", test_decode.run),
    ("encode + round-trip + range errors", test_encode.run),
    ("multiplexing", test_mux.run),
    ("DBC diagnostics / DLC / corrupt input", test_errors.run),
    ("cantools randomized cross-check", test_cantools_xcheck.run),
]


def main() -> int:
    print("can_dbc local test suite (no CAN hardware, no network)")
    failures = 0
    for name, runner in SUITES:
        print("\n" + "#" * 72)
        print(f"# {name}")
        print("#" * 72)
        failures += runner()
    total = len(SUITES)
    print("\n" + "=" * 72)
    if failures:
        print(f"SUITES WITH FAILURES: {failures}")
        return 1
    print(f"ALL {total} TEST SUITES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
