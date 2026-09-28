#!/usr/bin/env python3
"""Run the entire local DBC tool test-suite from the terminal.

Usage::

    python3 run_tests.py             # everything
    python3 run_tests.py -v          # verbose, prints every hex frame
    python3 run_tests.py layout      # only tests whose name contains ...

No CAN hardware, GUI or network access is required. cantools is used
only as an optional oracle inside one test module.
"""

import os
import sys
import unittest

# Allow running from any working directory.
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def main():
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    pattern_args = [a for a in sys.argv[1:] if not a.startswith("-")]

    loader = unittest.TestLoader()
    if pattern_args:
        loader.testNamePatterns = [f"*{p}*" for p in pattern_args]
    suite = loader.discover("tests", pattern="test_*.py")

    print("#" * 72)
    print("# Local CAN DBC tool - automated tests")
    print("# Every frame assertion prints its payload in hex; no CAN")
    print("# hardware or network service is used.")
    print("#" * 72)

    runner = unittest.TextTestRunner(
        verbosity=2 if verbose else 1,
        descriptions=True,
    )
    result = runner.run(suite)
    print()
    print(f"tests={result.testsRun} "
          f"failures={len(result.failures)} errors={len(result.errors)} "
          f"skipped={len(result.skipped)}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
