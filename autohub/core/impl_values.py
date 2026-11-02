"""Turns a raw WebFlow Target value into the representation the Master Sheet already uses (no I/O, no Qt).

Rules are explicit per parameter kind; a Master value that already says the same thing is kept as it is.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from autohub.core.normalizers import clean_text
from autohub.core.webflow_options import normalize_option_value

CHECKBOX = "checkbox"
TP_LEVEL = "tp_level"
OPTION_PREFIX = "option:"  # unordered multi-value field, e.g. "option:immobilizer"

_TRUE_WORDS = {"true": True, "false": False, "yes": True, "no": False, "1": True, "0": False, "x": True}
_STYLES = (("yes", "no"), ("true", "false"), ("1", "0"))
_TP = re.compile(r"^(tp)?\s*(\d+)$", re.IGNORECASE)


def option_kind(field: str) -> str:
    return f"{OPTION_PREFIX}{field}"


def _blank(value: object) -> bool:
    return clean_text(value) in ("", "---")


def _bool_of(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return _TRUE_WORDS.get(clean_text(value).casefold())


def _case_like(sample: str, word: str) -> str:
    if sample.isupper():
        return word.upper()
    return word.capitalize() if sample[:1].isupper() else word


def _checkbox(raw: str, candidates: Sequence[object]) -> str | bool:
    wanted = _bool_of(raw)
    if wanted is None:
        return raw
    for current in candidates:
        if isinstance(current, bool):
            return wanted
        text = clean_text(current)
        if _bool_of(text) is None:
            continue
        for pair in _STYLES:
            if text.casefold() in pair:
                return _case_like(text, pair[0 if wanted else 1])
        if text.casefold() == "x":
            return "x" if wanted else ""
    return wanted


def _tp_level(raw: str, candidates: Sequence[object]) -> str:
    match = _TP.match(clean_text(raw))
    if match is None:
        return raw
    number = match.group(2)
    for current in candidates:
        known = _TP.match(clean_text(current if not isinstance(current, float) else int(current)))
        if known is None:
            continue
        if known.group(1):
            return _case_like(clean_text(current)[:2], "tp") + number
        return number
    return f"TP{number}"


def _tokens(field: str, value: object) -> set[str]:
    return {token.casefold() for token in normalize_option_value(field, value).split("|") if token}


def _option(field: str, raw: str, candidates: Sequence[object]) -> str:
    for current in candidates:
        if not _blank(current) and _tokens(field, current) == _tokens(field, raw):
            return clean_text(current)  # same values in another order: keep the Master representation
    return raw


def normalize_impl_value(kind: str, raw: str, candidates: Sequence[object] = ()) -> str | bool:
    """`candidates`: the Master cells (IMPL row first, then REQ row) whose representation is to be followed."""
    candidates = [value for value in candidates if not _blank(value)]
    if kind == CHECKBOX:
        return _checkbox(raw, candidates)
    if kind == TP_LEVEL:
        return _tp_level(raw, candidates)
    if kind.startswith(OPTION_PREFIX):
        return _option(kind[len(OPTION_PREFIX):], raw, candidates)
    return raw
