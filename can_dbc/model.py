"""In-memory data model for DBC messages and signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .layout import signal_bit_positions, ensure_in_bounds, find_overlap

INTEL = "intel"
MOTOROLA = "motorola"


@dataclass
class Signal:
    """A single signal inside a DBC message.

    Multiplexer fields:

    * ``mux_kind`` is one of ``None`` (plain signal), ``"switch"``
      (the multiplexer signal itself) or ``"multiplexed"`` (a signal that
      only exists for one switch value / extended mux condition).
    * ``mux_value`` is the selector value for a multiplexed signal.
    * ``mux_dependencies`` lists the ``(switch_name, value)`` conditions of
      extended multiplexers; basic DBC multiplexing uses one entry.
    """

    name: str
    start: int
    length: int
    byte_order: str = INTEL
    signed: bool = False
    scale: float = 1.0
    offset: float = 0.0
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    unit: str = ""
    receivers: list[str] = field(default_factory=list)
    mux_kind: Optional[str] = None
    mux_value: Optional[int] = None
    mux_dependencies: list[tuple[str, int]] = field(default_factory=list)

    def __post_init__(self):
        self.bit_positions = signal_bit_positions(
            self.start, self.length, self.byte_order
        )

    # ------------------------------------------------------------------
    # value domain
    # ------------------------------------------------------------------
    @property
    def raw_min(self) -> int:
        """Smallest legal raw value (respects sign)."""
        if self.signed:
            return -(1 << (self.length - 1))
        return 0

    @property
    def raw_max(self) -> int:
        """Largest legal raw value (respects sign)."""
        if self.signed:
            return (1 << (self.length - 1)) - 1
        return (1 << self.length) - 1

    @property
    def physical_min(self) -> float:
        lo = self.raw_min * self.scale + self.offset
        hi = self.raw_max * self.scale + self.offset
        return min(lo, hi)

    @property
    def physical_max(self) -> float:
        lo = self.raw_min * self.scale + self.offset
        hi = self.raw_max * self.scale + self.offset
        return max(lo, hi)

    def raw_to_physical(self, raw: int) -> float:
        return raw * self.scale + self.offset

    @property
    def is_switch(self) -> bool:
        return self.mux_kind == "switch"

    @property
    def is_multiplexed(self) -> bool:
        return self.mux_kind == "multiplexed"


@dataclass
class Message:
    """A DBC ``BO_`` frame plus its ``SG_`` signals."""

    frame_id: int
    name: str
    dlc: int
    sender: str = ""
    signals: list[Signal] = field(default_factory=list)
    extended: bool = False

    def signal(self, name: str) -> Signal:
        for sig in self.signals:
            if sig.name == name:
                return sig
        raise KeyError(name)

    def validate(self) -> None:
        """Verify DLC bounds and overlap rules for this message.

        Signals are grouped by the multiplexer branch in which they can
        appear simultaneously:

        * plain signals and multiplexer switch signals are present in
          every frame, so they are included in every group;
        * branch signals share a group only with signals that use the
          exact same ``(switch, value)`` dependency set.

        Signals in different groups (e.g. m0 vs m1) never coexist and may
        legally share bits.
        """
        for sig in self.signals:
            ensure_in_bounds(sig.bit_positions, self.dlc, sig.name)

        always = [
            s for s in self.signals
            if not s.is_multiplexed
        ]
        branches: dict[tuple, list[Signal]] = {}
        for sig in self.signals:
            if sig.is_multiplexed:
                key = tuple(sig.mux_dependencies)
                branches.setdefault(key, []).append(sig)

        if not branches:
            groups = [("always present", always)]
        else:
            groups = [
                (_label(key), always + sigs)
                for key, sigs in branches.items()
            ]

        overlap = find_overlap(groups)
        if overlap is not None:
            name_a, name_b, wire_bit, label = overlap
            from .errors import SignalOverlapError
            raise SignalOverlapError(
                f"message {self.name!r}: signals {name_a!r} and {name_b!r} "
                f"overlap at wire bit {wire_bit} "
                f"(multiplex context {label})"
            )


def _label(key: tuple) -> str:
    return ",".join(f"{name}={value}" for name, value in key)


@dataclass
class Database:
    """Parsed DBC database: a name-indexed collection of messages."""

    messages: list[Message] = field(default_factory=list)

    def by_id(self, frame_id: int) -> Message:
        for msg in self.messages:
            if msg.frame_id == frame_id:
                return msg
        raise KeyError(f"no message with CAN id 0x{frame_id:X} ({frame_id})")

    def by_name(self, name: str) -> Message:
        for msg in self.messages:
            if msg.name == name:
                return msg
        raise KeyError(name)

    def validate(self) -> None:
        for msg in self.messages:
            msg.validate()
