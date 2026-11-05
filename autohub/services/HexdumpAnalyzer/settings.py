"""Settings for a capture run: parse and validate the TOML document into immutable dataclasses.

Pure logic. Filesystem checks are injected, and the TOML text is read by `load_settings`.
Legacy source: Hexdump/Capture_Auto/get_input.py (load_settings, apply_common, apply_file, apply_shot).
"""
from __future__ import annotations

import os
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .exceptions import HexdumpSettingsError
from .range_finder import FINDERS

COMMON_KEYS = frozenset({"OUT", "PAD_X", "MIN_W", "SCROLL_W", "FIT_W", "FIT_H", "RECALIBRATE", "DEBUG"})
FILE_KEYS = frozenset({"FILE", "APP", "MODE", "FORCE_NO_WRAP", "INCLUDE_HEADER", "INCLUDE_MARGIN",
                       "FIT_W", "FIT_H", "enabled", "shot"})
SHOT_KEYS = frozenset({"name", "key", "FIT_W", "FIT_H", "enabled"})
FIXED_IN_CODE = frozenset({"NPP_EXE", "CALIB_FILE"})
FORBIDDEN_NAME_CHARS = '\\/:*?"<>|'


@dataclass(frozen=True)
class CommonSettings:
    out_dir: str = "out"
    pad_x: int = 20
    min_w: int = 400
    scroll_w: int = 30
    fit_w: int = 0
    fit_h: int = 0
    recalibrate: bool = False
    debug: bool = False


@dataclass(frozen=True)
class ShotSettings:
    name: str
    key: str
    fit_w: int
    fit_h: int


@dataclass(frozen=True)
class FileSettings:
    path: str
    app: str
    mode: str
    force_no_wrap: bool
    include_header: bool
    include_margin: bool
    fit_w: int
    fit_h: int
    shots: tuple[ShotSettings, ...]


@dataclass(frozen=True)
class HexdumpSettings:
    common: CommonSettings
    files: tuple[FileSettings, ...]


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_ints(errors: list[str], where: str, data: Mapping[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        if key in data and not (_is_int(data[key]) and data[key] >= 0):
            errors.append(f"{where}: {key} must be an integer >= 0")


def _check_common(errors: list[str], common: Mapping[str, Any]) -> None:
    for key in common:
        if key in FIXED_IN_CODE:
            errors.append(f"[common]: {key} is fixed in the code (get_input.py) and cannot be set here")
        elif key not in COMMON_KEYS:
            errors.append(f"[common]: unknown parameter '{key}' (valid: {', '.join(sorted(COMMON_KEYS))})")
    _check_ints(errors, "[common]", common, ("PAD_X", "MIN_W", "SCROLL_W", "FIT_W", "FIT_H"))
    if "OUT" in common and not (isinstance(common["OUT"], str) and common["OUT"]):
        errors.append("[common]: OUT must be a non-empty string")
    for key in ("RECALIBRATE", "DEBUG"):
        if key in common and not isinstance(common[key], bool):
            errors.append(f"[common]: {key} must be true or false")


def _check_name(errors: list[str], where: str, name: object, names: set[str]) -> None:
    if not (isinstance(name, str) and name):
        errors.append(f"{where}: name is required (it is used in the image file name)")
    elif any(char in name for char in FORBIDDEN_NAME_CHARS):
        errors.append(f"{where}: name must not contain any of \\ / : * ? \" < > |")
    elif name in names:
        errors.append(f"{where}: duplicate name '{name}' in this file")
    else:
        names.add(name)


def _parse_shot(errors: list[str], where: str, raw: Mapping[str, Any], names: set[str],
                file_fit: tuple[int, int]) -> ShotSettings | None:
    for key in raw:
        if key not in SHOT_KEYS:
            errors.append(f"{where}: unknown parameter '{key}' (valid: {', '.join(sorted(SHOT_KEYS))})")
    _check_name(errors, where, raw.get("name"), names)
    if not (isinstance(raw.get("key"), str) and raw["key"]):
        errors.append(f"{where}: key is required (a non-empty string)")
    _check_ints(errors, where, raw, ("FIT_W", "FIT_H"))
    return ShotSettings(
        name=raw.get("name"), key=raw.get("key"),
        fit_w=raw.get("FIT_W", file_fit[0]), fit_h=raw.get("FIT_H", file_fit[1]),
    )


def _parse_file(errors: list[str], index: int, raw: Mapping[str, Any], common: CommonSettings,
                file_exists: Callable[[str], bool]) -> FileSettings | None:
    fpath = raw.get("FILE")
    where = f"[[file]] #{index}" + (f" ({fpath})" if isinstance(fpath, str) else "")
    for key in raw:
        if key not in FILE_KEYS:
            errors.append(f"{where}: unknown parameter '{key}' (valid: {', '.join(sorted(FILE_KEYS))})")
    if not (isinstance(fpath, str) and fpath):
        errors.append(f"{where}: FILE is required (path of the file to capture)")
    elif not file_exists(fpath):
        errors.append(f"{where}: file not found: {fpath}")
    if raw.get("APP") not in ("notepad", "npp"):
        errors.append(f"{where}: APP must be \"notepad\" or \"npp\" (got {raw.get('APP')!r})")
    if raw.get("MODE") not in FINDERS:
        errors.append(f"{where}: MODE must be one of {sorted(FINDERS)} (got {raw.get('MODE')!r})")
    for key in ("INCLUDE_HEADER", "INCLUDE_MARGIN", "FORCE_NO_WRAP"):
        if key in raw and not isinstance(raw[key], bool):
            errors.append(f"{where}: {key} must be true or false (without quotes)")
    _check_ints(errors, where, raw, ("FIT_W", "FIT_H"))

    shots_raw = raw.get("shot", [])
    if not (isinstance(shots_raw, list) and shots_raw):
        errors.append(f"{where}: needs at least one [[file.shot]] block")
        return None
    file_fit = (raw.get("FIT_W", common.fit_w), raw.get("FIT_H", common.fit_h))
    shots: list[ShotSettings] = []
    names: set[str] = set()
    for shot_index, shot_raw in enumerate(shots_raw, 1):
        if shot_raw.get("enabled", True) is False:
            continue
        shot_name = shot_raw.get("name")
        shot_where = f"{where} shot #{shot_index}" + (f" ({shot_name})" if isinstance(shot_name, str) else "")
        shot = _parse_shot(errors, shot_where, shot_raw, names, file_fit)
        if shot is not None:
            shots.append(shot)
    if not shots:
        return None
    return FileSettings(
        path=fpath, app=raw.get("APP"), mode=raw.get("MODE"),
        force_no_wrap=raw.get("FORCE_NO_WRAP", False),
        include_header=raw.get("INCLUDE_HEADER", True),
        include_margin=raw.get("INCLUDE_MARGIN", True),
        fit_w=file_fit[0], fit_h=file_fit[1], shots=tuple(shots),
    )


def parse_settings(data: Mapping[str, Any], *, file_exists: Callable[[str], bool],
                   npp_exe: str, npp_exists: Callable[[str], bool] | None = None) -> HexdumpSettings:
    """Validate parsed TOML data and return settings. Raises HexdumpSettingsError listing every problem."""
    errors: list[str] = []
    common_raw = data.get("common", {})
    files_raw = data.get("file", [])
    for key in data:
        if key not in ("common", "file"):
            errors.append(f"Section [{key}] is not valid (only [common] and [[file]] with [[file.shot]] are allowed)")

    _check_common(errors, common_raw)
    common = CommonSettings(
        out_dir=common_raw.get("OUT", "out"), pad_x=common_raw.get("PAD_X", 20),
        min_w=common_raw.get("MIN_W", 400), scroll_w=common_raw.get("SCROLL_W", 30),
        fit_w=common_raw.get("FIT_W", 0), fit_h=common_raw.get("FIT_H", 0),
        recalibrate=common_raw.get("RECALIBRATE", False), debug=common_raw.get("DEBUG", False),
    )

    if not isinstance(files_raw, list) or not files_raw:
        errors.append("Nothing to capture: add at least one [[file]] block with [[file.shot]] blocks")
        files_raw = []
    files: list[FileSettings] = []
    for index, raw in enumerate(files_raw, 1):
        if raw.get("enabled", True) is False:
            continue
        parsed = _parse_file(errors, index, raw, common, file_exists)
        if parsed is not None:
            files.append(parsed)

    if npp_exists is None:
        npp_exists = file_exists
    if any(f.app == "npp" for f in files) and not npp_exists(npp_exe):
        errors.append(f"Notepad++ not found: {npp_exe} (NPP_EXE is fixed in get_input.py; edit it there)")
    if not files and not errors:
        errors.append("All files are disabled (enabled = false)")
    if errors:
        raise HexdumpSettingsError(errors)
    return HexdumpSettings(common=common, files=tuple(files))


def load_settings(path: str, *, npp_exe: str, file_exists: Callable[[str], bool] = os.path.isfile,
                  npp_exists: Callable[[str], bool] | None = None) -> HexdumpSettings:
    """Read a TOML settings file from disk and validate it."""
    if not file_exists(path):
        raise HexdumpSettingsError([f"Settings file not found: {path}"])
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise HexdumpSettingsError([
            f"Settings file {path} has invalid TOML syntax: {exc}",
            "Hint: paths containing \\ must be written in SINGLE quotes '...' (not double quotes).",
        ]) from exc
    return parse_settings(data, file_exists=file_exists, npp_exe=npp_exe, npp_exists=npp_exists)
