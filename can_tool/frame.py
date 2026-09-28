"""Hex formatting helpers for CAN frames (local output only)."""


def hex_dump(data, sep=" "):
    """Render bytes as an uppercase hex string, e.g. ``"01 02 FF"``."""
    return sep.join(f"{b:02X}" for b in bytes(data))


def describe_frame(frame_id, data, extended=False):
    """One-line frame description used by the CLI and tests."""
    flag = "X" if extended else " "
    return f"{frame_id:08X}{flag} [{len(bytes(data))}] {hex_dump(data)}"
