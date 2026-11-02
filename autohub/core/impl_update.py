"""Values to write into a variant's IMPL row of the Master Sheet, and what happened to each variant (no I/O)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ImplUpdate:
    software: str  # SW Part Number the sheet row must still carry, so the right variant is written
    values: dict[str, str] = field(default_factory=dict)  # sheet column letter -> raw WebFlow Target value
    kinds: dict[str, str] = field(default_factory=dict)  # sheet column letter -> normalization kind (core.impl_values)


@dataclass(frozen=True)
class ImplOutcome:
    written: int = 0
    skipped: int = 0  # formula cells are never overwritten
    error: str = ""


@runtime_checkable
class ImplValueWriter(Protocol):
    def write_impl_values(self, updates: dict[str, ImplUpdate], save: bool = True) -> dict[str, ImplOutcome]:
        """Part number -> outcome; a variant that cannot be matched unambiguously is reported, never written."""
        ...
