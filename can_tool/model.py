"""In-memory model of a (subset of a) DBC database."""


class Signal:
    """A single signal definition (one ``SG_`` row).

    Byte order:
        ``"little_endian"`` -> DBC ``@1`` Intel layout
        ``"big_endian"``    -> DBC ``@0`` Motorola sawtooth layout
    Sign:
        ``@1+`` / ``@0+`` -> unsigned, ``@1-`` / ``@0-`` -> signed.

    ``mux_kind`` is one of:
        None               - plain (non-multiplexed) signal
        "multiplexor"      - the ``M`` switch signal
        ("multiplexed", v) - signal present when the switch raw value == v
        ("multiplexed", ranges) - a sorted, merged list of inclusive int
                                  ranges (used for extended ``SG_MUL_VAL_``)
    """

    def __init__(
        self,
        name,
        start_bit,
        length,
        byte_order="little_endian",
        signed=False,
        scale=1.0,
        offset=0.0,
        minimum=None,
        maximum=None,
        unit="",
        mux_kind=None,
    ):
        self.name = name
        self.start_bit = start_bit
        self.length = length
        self.byte_order = byte_order
        self.signed = signed
        self.scale = scale
        self.offset = offset
        # Raw value span implied purely by the bit length.
        if signed:
            self.raw_min = -(1 << (length - 1))
            self.raw_max = (1 << (length - 1)) - 1
        else:
            self.raw_min = 0
            self.raw_max = (1 << length) - 1
        # Optional GEN_SIG_SEND_EXT_TYPE / SIG_VALTYPE independent of DBC value.
        self.minimum = minimum
        self.maximum = maximum
        self.unit = unit
        self.mux_kind = mux_kind

    # -- mux helpers -----------------------------------------------------
    @property
    def is_multiplexor(self):
        return self.mux_kind == "multiplexor"

    @property
    def is_multiplexed(self):
        return isinstance(self.mux_kind, tuple) and self.mux_kind[0] == "multiplexed"

    def matches_mux_value(self, value):
        """True if this signal is present for the given mux switch raw value."""
        if not self.is_multiplexed:
            return False
        spec = self.mux_kind[1]
        if isinstance(spec, int):
            return value == spec
        return any(lo <= value <= hi for lo, hi in spec)

    def mux_label(self):
        """Compact label used in diagnostics and dumps."""
        if self.is_multiplexor:
            return "M"
        if self.is_multiplexed:
            spec = self.mux_kind[1]
            if isinstance(spec, int):
                return f"m{spec}"
            return "m" + ",".join(
                str(lo) if lo == hi else f"{lo}-{hi}" for lo, hi in spec
            )
        return ""

    def physical_range(self):
        """(lo, hi) physical values reachable through the raw bit range."""
        lo = self.raw_min * self.scale + self.offset
        hi = self.raw_max * self.scale + self.offset
        if self.scale < 0:
            lo, hi = hi, lo
        return lo, hi

    def __repr__(self):
        return (
            f"Signal({self.name!r}, start={self.start_bit}, len={self.length}, "
            f"{self.byte_order}, signed={self.signed})"
        )


class Message:
    """A CAN message definition (one ``BO_`` block)."""

    def __init__(self, frame_id, name, dlc, sender="", extended=None):
        # frame_id always holds the *bare* CAN arbitration id (32-bit mask
        # stripped); ``extended`` records whether the DBC set the flag.
        self.frame_id = frame_id
        self.name = name
        self.dlc = dlc
        self.sender = sender
        self.extended = extended if extended is not None else frame_id > 0x7FF
        self.signals = []

    @property
    def multiplexor(self):
        return next((s for s in self.signals if s.is_multiplexor), None)

    def signals_for_mux(self, mux_value):
        """Return the signals active for a given multiplexor raw value."""
        out = []
        for sig in self.signals:
            if sig.is_multiplexed:
                if sig.matches_mux_value(mux_value):
                    out.append(sig)
            elif not sig.is_multiplexor:
                out.append(sig)
        return out

    def get(self, name):
        for sig in self.signals:
            if sig.name == name:
                return sig
        raise KeyError(name)

    def __repr__(self):
        return f"Message(0x{self.frame_id:X}, {self.name!r}, DLC={self.dlc})"


class Database:
    """Parsed DBC: lookup messages by bare id or name."""

    def __init__(self, messages=None):
        self.messages = list(messages or [])

    def get_message_by_id(self, frame_id):
        # Accept raw ids that may still carry the DBC extended flag.
        bare = frame_id & 0x1FFFFFFF
        for msg in self.messages:
            if msg.frame_id == bare:
                return msg
        raise KeyError(f"no message with id 0x{bare:X} in database")

    def get_message_by_name(self, name):
        for msg in self.messages:
            if msg.name == name:
                return msg
        raise KeyError(name)

    def decode(self, frame_id, data):
        from .codec import decode_frame
        return decode_frame(self, frame_id, data)

    def encode(self, name_or_id, values):
        from .codec import encode_frame
        return encode_frame(self, name_or_id, values)

    def __repr__(self):
        return f"Database({[m.name for m in self.messages]})"
