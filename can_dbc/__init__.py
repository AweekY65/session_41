"""can_dbc: a local, dependency-free CAN Bus DBC signal codec.

Everything in this package works on local files or in-memory data only.
It never opens a socket, talks to a CAN interface, or contacts a remote
service.  The public surface is re-exported here for convenience:

    from can_dbc import load_file, load_string, Database, DbcError
"""

from .errors import (
    DbcError,
    DbcParseError,
    DuplicateMessageIdError,
    SignalOverlapError,
    BitOutOfBoundsError,
    DlcError,
    EncodeError,
    DecodeError,
)
from .model import Signal, Message, Database
from .parser import parse_string, parse_file
from .codec import encode, decode, encode_raw, decode_raw

__all__ = [
    "Signal",
    "Message",
    "Database",
    "parse_string",
    "parse_file",
    "load_string",
    "load_file",
    "encode",
    "decode",
    "encode_raw",
    "decode_raw",
    "DbcError",
    "DbcParseError",
    "DuplicateMessageIdError",
    "SignalOverlapError",
    "BitOutOfBoundsError",
    "DlcError",
    "EncodeError",
    "DecodeError",
]

__version__ = "1.0.0"


def load_string(text: str) -> Database:
    """Parse DBC text and return a :class:`Database`."""
    return parse_string(text)


def load_file(path: str) -> Database:
    """Parse a ``.dbc`` file from the local filesystem."""
    return parse_file(path)
