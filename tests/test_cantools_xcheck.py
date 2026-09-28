"""Cross-check our codec against the third-party cantools reference.

cantools is used ONLY as a test oracle here; the implementation under
test (can_dbc) is fully self-contained.  This module is skipped silently
when cantools is not installed.
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from can_dbc import load_string, encode, decode
from tests.helpers import Reporter
from tests.sample_dbc import DBC

try:
    import cantools
except ImportError:  # pragma: no cover - environment dependent
    cantools = None


def run() -> int:
    r = Reporter()
    if cantools is None:
        print("cantools not installed - cross-check skipped")
        return 0

    ours = load_string(DBC)
    theirs = cantools.database.load_string(DBC, database_format="dbc")

    r.section("Randomized encode cross-check vs cantools")
    rng = random.Random(20240926)
    frames = 0
    for msg in ours.messages:
        tmsg = theirs.get_message_by_frame_id(msg.frame_id)
        for _ in range(25):
            values = {}
            for sig in msg.signals:
                if sig.is_multiplexed or sig.is_switch:
                    continue  # switches/branches handled below
                # cantools enforces the declared [minimum, maximum], so
                # sample raw values whose scaled value lies inside it.
                if sig.scale > 0:
                    lo = math.ceil((sig.minimum - sig.offset) / sig.scale)
                    hi = math.floor((sig.maximum - sig.offset) / sig.scale)
                else:
                    lo = math.ceil((sig.maximum - sig.offset) / sig.scale)
                    hi = math.floor((sig.minimum - sig.offset) / sig.scale)
                lo = max(sig.raw_min, lo)
                hi = min(sig.raw_max, hi)
                raw = rng.randint(lo, hi)
                values[sig.name] = sig.raw_to_physical(raw)
            # pick a switch value for which at least one branch exists
            for sig in msg.signals:
                if not sig.is_switch:
                    continue
                defined = sorted({
                    dep[1] for other in msg.signals
                    if other.is_multiplexed
                    for dep in other.mux_dependencies
                    if dep[0] == sig.name
                })
                branch = rng.choice(defined)
                values[sig.name] = sig.raw_to_physical(branch)
                for other in msg.signals:
                    if (other.is_multiplexed and
                            other.mux_dependencies == [(sig.name, int(branch))]):
                        if other.scale > 0:
                            lo = math.ceil((other.minimum - other.offset)
                                           / other.scale)
                            hi = math.floor((other.maximum - other.offset)
                                            / other.scale)
                        else:
                            lo = math.ceil((other.maximum - other.offset)
                                           / other.scale)
                            hi = math.floor((other.minimum - other.offset)
                                            / other.scale)
                        raw = rng.randint(max(other.raw_min, lo),
                                          min(other.raw_max, hi))
                        values[other.name] = other.raw_to_physical(raw)
            mine = encode(values, msg, strict=False)
            ref = tmsg.encode(values)
            frames += 1
            if mine != ref:
                r.failed += 1
                print(f"   [FAIL] {msg.name} {values}")
                print(f"          ours:     {mine.hex()}")
                print(f"          cantools: {ref.hex()}")
    r.check(f"{frames} random frames encode identically", r.failed == 0)

    r.section("Randomized decode cross-check vs cantools")
    frames = 0
    skipped_undefined_mux = 0
    for msg in ours.messages:
        tmsg = theirs.get_message_by_frame_id(msg.frame_id)
        attempts = 0
        done = 0
        while done < 25:
            attempts += 1
            payload = bytes(rng.randrange(256) for _ in range(msg.dlc))
            # Undefined mux switch values make cantools raise; our decoder
            # simply returns no branch signals, so compare on frames where
            # the switch selects a defined branch (or no mux at all).
            if any(s.is_switch for s in msg.signals):
                raws = decode(payload, msg)  # noqa: F811 - read-only probe
                ok = True
                for s in msg.signals:
                    if not s.is_switch:
                        continue
                    defined = {dep[1] for other in msg.signals
                               if other.is_multiplexed
                               for dep in other.mux_dependencies
                               if dep[0] == s.name}
                    if int(raws[s.name]) not in defined:
                        ok = False
                        break
                if not ok:
                    skipped_undefined_mux += 1
                    if attempts > 2000:  # pathological safety bound
                        break
                    continue
            mine = decode(payload, msg)
            ref = tmsg.decode(payload, decode_choices=False)
            frames += 1
            done += 1
            if mine != ref:
                r.failed += 1
                print(f"   [FAIL] {msg.name} payload {payload.hex()}")
                print(f"          ours:     {mine}")
                print(f"          cantools: {ref}")
    print(f"   (skipped {skipped_undefined_mux} frames with undefined "
          f"mux switch values)")
    r.check(f"{frames} random frames decode identically", r.failed == 0)

    return r.summary("cantools cross-check")


def test_cantools_xcheck():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
