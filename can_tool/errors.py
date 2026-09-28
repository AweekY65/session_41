"""Exception hierarchy for the local DBC tool.

All diagnostics carry a clear human-readable message; parse errors also
record the 1-based line number (and source file, when known).
"""


class DbcError(Exception):
    """Base class for every error raised by this package."""


class DbcParseError(DbcError):
    """The DBC text is malformed or contains an unsupported construct."""

    def __init__(self, message, line=None, path=None):
        self.line = line
        self.path = path
        location = ""
        if path is not None:
            location = str(path)
            if line is not None:
                location += f":{line}"
        elif line is not None:
            location = f"line {line}"
        if location:
            message = f"{location}: {message}"
        super().__init__(message)


class DbcValidationError(DbcError):
    """A DBC parsed fine but its definitions are invalid.

    Examples: duplicated message ids, signals running past the message
    payload, bit overlap between signals, a multiplexer value that
    references an unknown multiplexor, etc.
    """


class EncodeError(DbcError):
    """Physical values cannot be represented in the requested payload."""


class DecodeError(DbcError):
    """A raw CAN payload cannot be decoded with the given database."""
