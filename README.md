# Local CAN Bus DBC Encoder/Decoder

A small, dependency-free Python tool that parses Vector **DBC** files locally
and encodes/decodes CAN signal values to/from payload bytes. It is entirely
off-line:

- DBC definitions, frames, parsing state and test data live in **local files
  or in memory only**;
- it never opens a CAN interface, SocketCAN, a vehicle, a cloud service or any
  network connection;
- the parser and the signal encode/decode logic are implemented **inside this
  project** (`can_tool/`). The third-party [`cantools`](https://pypi.org/project/cantools/)
  package is used only as an independent reference oracle in one optional test
  module and is not required to run the tool.

## Features

- Parses the core DBC constructs:
  - `BO_` messages: **id**, **name**, **DLC**, sender, extended (29-bit) ids;
  - `SG_` signals: **start bit, length, byte order, sign, scale, offset,
    unit, min/max**, receivers;
  - inline multiplexing (`M` / `mN`) and extended multiplex value tables
    (`SG_MUL_VAL_` with `a-b,c` ranges);
  - tolerant of `//` comments, multi-line `CM_` blocks, `VAL_`, `BA_`,
    `SIG_GROUP_` and the rest of the DBC boilerplate.
- **Intel little-endian (`@1`) and Motorola big-endian (`@0`)** signal
  layouts, including non-byte-aligned and **cross-byte (sawtooth) fields**.
- **Signed and unsigned** signals with two's-complement handling.
- Physical conversion:
  `physical = raw * scale + offset` (decode) and its inverse with
  quantization/range validation (encode).
- **Multiplexed messages**: the multiplexor raw value selects exactly which
  signal set is encoded or decoded.
- Clear diagnostics for: duplicate message ids/names, duplicate signal names,
  bit overlap between signals (including Motorola sawtooth overlap and
  multiplexed branches that collide for a shared mux value), signals that run
  past the DLC, bad DLC (outside classic CAN 0–8), zero scale, corrupted DBC
  lines, and values that cannot be represented.
- Command line and Python API. No GUI, no hardware.

## Project layout

```
can_tool/
  errors.py     exception hierarchy with file:line diagnostics
  model.py      Signal / Message / Database
  parser.py     DBC text parser, validation and bit-layout math
  codec.py      raw<->physical conversion, frame encode/decode
  frame.py      hex formatting helpers
  cli.py        `python -m can_tool ...`
examples/
  example.dbc   Intel + Motorola + signed + scaled + multiplexed + extended
tests/          automated unittest suite (prints hex frames)
run_tests.py    terminal test runner
```

## Requirements

- Python 3.8+; standard library only.
- Optional: `cantools` to run the differential cross-check test
  (the test self-skips if it is not installed).

## Quick start

```bash
# inspect a DBC
python3 -m can_tool info examples/example.dbc

# encode physical values to a hex frame
python3 -m can_tool encode --dbc examples/example.dbc --message EngineData \
    --set EngineSpeed=2400.5 --set EngineTemp=85 \
    --set ThrottlePos=37.5 --set OdometerLarge=4660 --set CheckEngine=1
# frame: 100#82 25 7D 77 01 34 12 01

# decode a hex frame back to physical signal values
python3 -m can_tool decode --dbc examples/example.dbc --id 0x100 \
    --data "82 25 7D 77 01 34 12 01"
```

`--set NAME=VALUE` gives a physical value. Use `--set NAME=r5` to force a raw
integer (useful for multiplexor switches).

### Python API

```python
from can_tool import parse_dbc, encode_frame, decode_frame, Raw

db = parse_dbc("examples/example.dbc")

payload = encode_frame(db, "EngineData", {
    "EngineSpeed": 2400.5, "EngineTemp": 85,
    "ThrottlePos": 37.5, "OdometerLarge": 4660, "CheckEngine": 1,
})
print(payload.hex(" "))          # 82 25 7D 77 01 34 12 01

values = decode_frame(db, 0x100, payload)
# {'EngineSpeed': 2400.5, 'EngineTemp': 85.0, ...}

# multiplexed message: pick the branch with the multiplexor value
p = encode_frame(db, "DiagnosticMessage",
                 {"ServiceMode": 1, "Pressure": 400.0, "PumpRpm": 3000})
# or force the switch raw value: {"ServiceMode": Raw(1), ...}
```

## DBC support scope

| DBC feature                                   | Support |
|-----------------------------------------------|---------|
| `BO_` id / name / DLC / sender                | ✅ |
| Standard 11-bit and extended 29-bit (`0x80000000` flag) ids | ✅ |
| `SG_` start bit, length, `@0/@1`, `+/-`       | ✅ |
| scale, offset, unit, `[min|max]`              | ✅ |
| inline multiplexing `M` / `mN`                | ✅ |
| `SG_MUL_VAL_` value ranges (`0-2,4`)          | ✅ |
| multiple receivers                            | ✅ (ignored beyond parsing) |
| `VAL_` named value tables / choices           | Ⓜ️ parsed/skipped, values stay numeric |
| `BA_` / attributes, `CM_` comments            | Ⓜ️ tolerated/skipped |
| Signal groups, float (`SIG_VALTYPE_`) signals | ❌ |
| CAN FD (DLC > 8), J1939, container PDUs       | ❌ |

## Bit numbering rules

The wire payload is addressed in **linear/network bit numbering**:

```
byte:          0                  1                  2
wire bit:   .---------.        .---------.        .---------.
            |7 6 ... 0|        |7 6 ... 0|        |7 6 ... 0|
linear n:    7 ... 0          15 ... 8          23 ... 16
```

DBC uses a **sawtooth** numbering inside each byte (bit 7 is the first saw
number of the byte). In linear coordinates the rules are:

- **Intel (`@1`)** — start bit = linear position of the value's **LSB**;
  successive value bits occupy `S, S+1, S+2, ...`. A cross-byte field steps
  from wire bit 7 of one byte to wire bit 0 of the next (e.g. `7|9@1` puts
  its lowest bit on byte 0 wire 7 and the remaining 8 bits in byte 1).
- **Motorola (`@0`)** — start bit = linear position of the value's **MSB**;
  walking toward the LSB goes `n → n-1`, and when it reaches wire bit 0
  (`n % 8 == 0`) it wraps to wire bit 7 of the *following* byte (`n → n+15`).
  A byte-aligned Motorola field therefore starts at the *last* saw number of
  its first byte — `7|8`, `7|16`, `15|16`, ... — while `8|16@0` is the
  classic diagonal cross-byte layout.

The implementation (`can_tool/parser.py::_bit_positions`) was verified bit by
bit against cantools across ~7,000 randomized layouts by the test suite.

## Conversion formulas

```
decode:   raw      = bits extracted per the byte-order walk above
          physical = raw * scale + offset
          (signed: two's complement over the signal length, sign-extended)

encode:   raw      = round((physical - offset) / scale)
          physical = raw * scale + offset   # must reproduce the input
                                             # within a tight tolerance
```

Encoding raises an explicit error when:

1. the rounded raw value is outside the signal's bit span
   (`0..2^N-1` unsigned, `-2^(N-1)..2^(N-1)-1` signed),
2. the input lies off the quantization grid (e.g. `1.125` with scale `0.25`),
3. the input violates an explicit DBC `[min|max]` limit,
4. the value is not a finite number, or
5. a required signal (or the multiplexor) is missing / an inactive
   multiplexed signal is supplied.

Per DBC convention `[0|0]` means "no limits declared" and is ignored.

## Multiplexing

The signal marked `M` is the switch. Its **raw** value determines the active
set: signals marked `mN` exist only when the switch equals `N`; plain signals
always exist. Decoding returns only the active branch. Overlap validation
understands the branches: two multiplexed signals may share payload bits if
they can never be active for the same switch value, but conflicting branches
are rejected. `SG_MUL_VAL_` extends a branch to a set/range of switch values.

## Running the tests

```bash
# everything, summary
python3 run_tests.py

# verbose: prints every asserted frame in hex plus diagnostic messages
python3 run_tests.py -v

# filter by name, e.g. only Motorola tests
python3 run_tests.py Motorola

# or plain unittest
python3 -m unittest discover -s tests -v
```

The suite covers Intel and Motorola layouts, cross-byte fields, signed and
unsigned boundaries (`min`/`max`/`0`), scale/offset conversions, encode→decode
round-trips over randomized raw ranges, multiplexing (including shared bits
between branches and `SG_MUL_VAL_`), corrupted/invalid DBCs with message text
checks, DLC mismatches, non-representable values, CLI end-to-end behavior, and
a randomized differential comparison against cantools (skipped automatically
if cantools is absent). All tests run in a terminal, print hex frames, and
need no CAN hardware or GUI.
