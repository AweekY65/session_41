"""Typed exception hierarchy for the can_dbc package.

All errors raised by this package derive from :class:`DbcError`, so callers
can catch the whole family with a single ``except`` clause.
"""


class DbcError(Exception):
    """Base class for every error raised by :mod:`can_dbc`."""


class DbcParseError(DbcError):
    """The DBC text is malformed or references unknown constructs."""


class DuplicateMessageIdError(DbcError):
    """Two ``BO_`` definitions in the same file share the same CAN id."""


class SignalOverlapError(DbcError):
    """Two simultaneously-active signals claim the same payload bits."""


class BitOutOfBoundsError(DbcError):
    """A signal uses bit positions outside its message's DLC."""


class DlcError(DbcError):
    """A CAN payload length does not match the message DLC."""


class EncodeError(DbcError):
    """A physical/raw value cannot legally be encoded into a signal."""


class DecodeError(DbcError):
    """A raw CAN frame cannot be decoded as the claimed message."""
