"""Encode tests: known vectors, round-trips, boundaries and range errors."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from can_dbc import load_string, encode, decode, encode_raw, decode_raw
from can_dbc.errors import EncodeError
from tests.helpers import Reporter
from tests.sample_dbc import DBC


def run() -> int:
    r = Reporter()
    db = load_string(DBC)
    engine = db.by_id(100)
    cross = db.by_id(101)

    r.section("Encode matches cantools reference hex")
    cases = [
        (engine,
         {"RPM": 3000.0, "Temp": 25.0, "Flags": 5, "Throttle": 50.0},
         "2ee0802005f40100"),
        (engine,
         {"RPM": 0.0, "Temp": -40.0, "Flags": 0, "Throttle": 0.0},
         "0000000000000000"),
        (engine,
         {"RPM": 16383.75, "Temp": 87.0, "Flags": 15, "Throttle": 409.5},
         "ffff803f0fff0f00"),
        (cross,
         {"IntelCross": 0xABC, "MotoCross": 0x123, "SignedMoto": -10.0},
         "c0ab000123000000"),
        (cross,
         {"IntelCross": 4095, "MotoCross": 4095, "SignedMoto": 16373.5},
         "f0ff000fff7fff00"),
        (cross,
         {"IntelCross": 1, "MotoCross": 1, "SignedMoto": -16394.0},
         "1000000001800000"),
    ]
    for msg, values, expected in cases:
        payload = r.guard(f"encode {msg.name}", encode, values, msg)
        if payload is not None:
            r.frame(msg.name, payload, f"expected {expected}")
            r.eq(f"{msg.name} {values} -> {expected}",
                 payload.hex(), expected)

    r.section("Physical round-trip on boundary values")
    boundary_sets = [
        (engine, {"RPM": 0.0, "Temp": -40.0, "Flags": 0, "Throttle": 0.0}),
        (engine, {"RPM": 16383.75, "Temp": 87.0, "Flags": 15,
                  "Throttle": 409.5}),
        (cross, {"IntelCross": 0, "MotoCross": 0, "SignedMoto": -16394.0}),
        (cross, {"IntelCross": 4095, "MotoCross": 4095,
                 "SignedMoto": 16373.5}),
    ]
    for msg, values in boundary_sets:
        payload = encode(values, msg)
        r.frame(msg.name + " round-trip", payload)
        back = decode(payload, msg)
        r.eq(f"{msg.name} {values} round-trips", back, values)

    r.section("Raw interface round-trip")
    raws = {"RPM": 65535, "Temp": -128, "Flags": 15, "Throttle": 4095}
    payload = encode_raw(raws, engine)
    r.frame("raw extremes (incl. negative Intel Temp)", payload)
    r.eq("raw decode returns same ints", decode_raw(payload, engine), raws)

    r.section("Value-domain error reporting")
    r.expect_raises("RPM above representable range", EncodeError,
                    encode, {"RPM": 16384.0}, engine)
    r.expect_raises("RPM below 0", EncodeError,
                    encode, {"RPM": -0.5}, engine)
    r.expect_raises("Temp above signed max", EncodeError,
                    encode, {"Temp": 88.0}, engine)
    r.expect_raises("Flags above 15", EncodeError,
                    encode, {"Flags": 16}, engine)
    r.expect_raises("non-representable 3000.1 (scale 0.25)", EncodeError,
                    encode, {"RPM": 3000.1}, engine)
    r.expect_raises("unknown signal name", EncodeError,
                    encode, {"Nope": 1}, engine)
    # non-strict mode quantizes to nearest raw
    payload = encode({"RPM": 3000.1}, engine, strict=False)
    r.frame("quantized RPM 3000.1 (non-strict)", payload)
    r.eq("3000.1 quantizes to raw 12000 (3000.0)",
         decode(payload, engine)["RPM"], 3000.0)

    return r.summary("encode")


def test_encode_suite():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
