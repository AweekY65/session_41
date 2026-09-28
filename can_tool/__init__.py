"""Local CAN Bus DBC signal encoder/decoder.

Everything in this package works on local files and in-memory data only.
It never touches a real CAN bus, a vehicle, SocketCAN or any network service.

Public API:

    from can_tool import parse_dbc, decode_frame, encode_frame, load_dbc
"""

from .errors import DbcError, DbcParseError, DbcValidationError
from .errors import EncodeError, DecodeError
from .model import Signal, Message, Database
from .parser import parse_dbc, parse_dbc_text, load_dbc
from .codec import encode_frame, decode_frame, decode_frame_raw, encode_signal, decode_signal, Raw
from .frame import hex_dump

__all__ = [
    "DbcError",
    "DbcParseError",
    "DbcValidationError",
    "EncodeError",
    "DecodeError",
    "Signal",
    "Message",
    "Database",
    "parse_dbc",
    "parse_dbc_text",
    "load_dbc",
    "encode_frame",
    "decode_frame",
    "decode_frame_raw",
    "encode_signal",
    "decode_signal",
    "Raw",
    "hex_dump",
]

__version__ = "1.0.0"
