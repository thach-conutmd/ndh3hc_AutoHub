"""Resolves each variant's calibration HEX file before WebFlow job creation."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from autohub.core.a2l_hex import find_calibration_hex


def _valid_hex(path: str) -> bool:
    return bool(path) and Path(path).suffix.casefold() == ".hex" and Path(path).is_file()


def resolve_calibration_hex(
    variants: list[dict], symbol: str, choose_folder: Callable[[], str]
) -> tuple[list[dict], list[str]]:
    """Returns (variants with a valid `_calibration_hex_path`, error messages for the rest).

    Variants whose Master Sheet HEX link is missing, invalid or not a file are matched in the folder picked by
    `choose_folder`, which is called at most once per batch. Variants that cannot be resolved are excluded.
    """
    ready: list[dict] = []
    missing: list[dict] = []
    for variant in variants:
        if _valid_hex(str(variant.get("_calibration_hex_path") or "")):
            ready.append(variant)
        else:
            missing.append(variant)
    if not missing:
        return ready, []

    folder = choose_folder() if missing else ""
    errors: list[str] = []
    for variant in missing:
        part_number = variant.get("part_number", "?")
        if not folder:
            errors.append(f"{part_number}: no HEX file linked in the Master Sheet and no HEX folder selected.")
            continue
        try:
            hex_path = find_calibration_hex(folder, symbol, str(part_number))
        except (OSError, ValueError) as error:
            errors.append(f"{part_number}: {error}")
            continue
        ready.append({**variant, "_calibration_hex_path": str(hex_path)})
    return ready, errors
