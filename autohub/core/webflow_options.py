"""Resolve sheet values to real WebFlow General-info list labels."""
from __future__ import annotations

import re
from collections.abc import Iterable

from autohub.core.normalizers import clean_text, normalize_model_year

GENERAL_OPTION_FIELDS = frozenset({"model_year", "emission_norm", "transmission", "immobilizer", "market"})

_ALIASES = {
    "transmission": {
        "manual": "MT",
        "manual transmission": "MT",
        "automatic": "AT",
        "automatic transmission": "AT",
        "continuously variable transmission": "CVT",
        "cvt with paddle shift": "CVT with Paddle shift",
    },
    "immobilizer": {
        "active": "active",
        "inactive": "Without",
        "not active": "Without",
        "without": "Without",
        "immo 3": "IMMO3",
        "immo 4": "IMMO4",
        "immo 5": "IMMO5",
        "immo 6": "IMMO6",
    },
    "market": {
        "uk": "GB",
        "united kingdom": "GB",
        "argentina": "Argentine",
    },
}


def normalize_option_value(field: str, value) -> str:
    """Canonical spelling of individual values; preserve unknown values and multiple selections."""
    result = []
    for item in re.split(r"[|\r\n]+", clean_text(value)):
        item = " ".join(item.split())
        if not item:
            continue
        if field == "model_year":
            item = normalize_model_year(item)
        item = _ALIASES.get(field, {}).get(item.casefold(), item)
        if field == "transmission" and item.casefold() in {"at", "mt", "cvt", "dct", "amt"}:
            item = item.upper()
        result.append(item)
    return "|".join(dict.fromkeys(result))


def _option_key(field: str, value: str) -> str:
    text = normalize_option_value(field, value).casefold()
    if field == "emission_norm":
        text = re.sub(r"\bbharat\s*stage\s*", "bs", text)
        text = re.sub(r"\beuro\s*", "eu", text)
        return re.sub(r"[\s-]+", "", text)
    return text


def resolve_option_values(field: str, value: str, labels: Iterable[str]) -> set[str]:
    """Return actual labels, never a guessed option. Resolve all requests before anything is clicked.

    Exact labels win over aliases. Combined labels win over splitting on slashes/commas.
    Unsupported or ambiguous values raise ValueError instead of dropping a selection.
    """
    labels = list(labels)

    def match(request: str) -> str | None:
        if request in labels:
            return request
        matches = [label for label in labels if label.strip().casefold() == request.strip().casefold()]
        if not matches and field in GENERAL_OPTION_FIELDS:
            key = _option_key(field, request)
            matches = [label for label in labels if _option_key(field, label) == key]
        if len(matches) > 1:
            raise ValueError(f"WebFlow {field} value {request!r} is ambiguous: {matches}.")
        return matches[0] if matches else None

    resolved = set()
    for request in re.split(r"[|\r\n]+", value):
        request = request.strip()
        if not request:
            continue
        label = match(request)
        if label is not None:
            resolved.add(label)
            continue
        parts = re.split(r"\s*[/,;]\s*", request) if field in GENERAL_OPTION_FIELDS else [request]
        if len(parts) > 1:
            for part in parts:
                label = match(part)
                if label is None:
                    raise ValueError(f"WebFlow {field} does not offer {part!r}; available values: {labels}.")
                resolved.add(label)
        else:
            raise ValueError(f"WebFlow {field} does not offer {request!r}; available values: {labels}.")
    return resolved
