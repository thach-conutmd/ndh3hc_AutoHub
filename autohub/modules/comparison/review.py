"""Manual review of a comparison result row; the calculated status stays on the ComparisonRow."""
from __future__ import annotations

from dataclasses import dataclass

from .comparison import Status


@dataclass(frozen=True)
class Review:
    status: Status | None = None  # manual override; None keeps the calculated status
    comment: str = ""
