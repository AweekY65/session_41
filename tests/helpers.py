"""Tiny assertion/hex reporting used by every test module.

The test files are plain Python (no pytest dependency) and can be executed
through either ``python run_tests.py`` or ``pytest``.  Every check prints
a ``[PASS]``/``[FAIL]`` line, and frames are rendered in hex so the test
log doubles as a manual trace.
"""

from __future__ import annotations

import traceback
from typing import Callable, TypeVar

T = TypeVar("T")


class Reporter:
    def __init__(self):
        self.passed = 0
        self.failed = 0

    def section(self, title: str) -> None:
        print()
        print(f"== {title} ==")

    def frame(self, label: str, payload: bytes, extra: str = "") -> None:
        print(f"   frame {label}: {bytes(payload).hex(' ')} {extra}".rstrip())

    def check(self, label: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"   [PASS] {label}{(' - ' + detail) if detail else ''}")
        else:
            self.failed += 1
            print(f"   [FAIL] {label}{(' - ' + detail) if detail else ''}")

    def eq(self, label: str, actual, expected) -> None:
        self.check(label, actual == expected,
                   f"actual={actual!r} expected={expected!r}")

    def expect_raises(
        self, label: str, exc_type: type[BaseException], fn: Callable,
        *args, **kwargs
    ) -> None:
        try:
            fn(*args, **kwargs)
        except exc_type as exc:
            self.passed += 1
            print(f"   [PASS] {label} - raised {type(exc).__name__}: {exc}")
            return exc
        except BaseException as exc:  # wrong exception type
            self.failed += 1
            print(f"   [FAIL] {label} - expected {exc_type.__name__}, "
                  f"got {type(exc).__name__}: {exc}")
            return None
        self.failed += 1
        print(f"   [FAIL] {label} - expected {exc_type.__name__} "
              f"but nothing was raised")
        return None

    def guard(self, label: str, fn: Callable, *args, **kwargs):
        """Run fn, treating any unexpected exception as a failed check."""
        try:
            return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 - tests report, do not stop
            self.failed += 1
            print(f"   [FAIL] {label} - unexpected exception:")
            for line in traceback.format_exc().splitlines():
                print("          " + line)
            return None

    def summary(self, name: str) -> int:
        total = self.passed + self.failed
        print()
        print(f"-- {name}: {self.passed}/{total} passed"
              + (f", {self.failed} FAILED" if self.failed else ""))
        return self.failed
