"""Adapter the Hexdump UI calls: wraps settings loading and range lookup, converting errors to HexdumpInputError."""
from __future__ import annotations

from autohub.core.ports import HexdumpInputError
from autohub.services.HexdumpAnalyzer.exceptions import HexdumpSettingsError
from autohub.services.HexdumpAnalyzer.range_finder import FINDERS, find_range
from autohub.services.HexdumpAnalyzer.settings import HexdumpSettings, load_settings

# Legacy get_input.py fixed this path in code (not settable in .toml); it is only checked for APP = "npp" files.
NPP_EXE = r"C:\Program Files\Notepad++\notepad++.exe"


class HexdumpService:
    def modes(self) -> tuple[str, ...]:
        return tuple(sorted(FINDERS))

    def check_settings(self, path: str) -> str:
        try:
            settings = load_settings(path, npp_exe=NPP_EXE)
        except HexdumpSettingsError as exc:
            raise HexdumpInputError("\n".join(exc.errors)) from exc
        return _summarize(settings)

    def find_range(self, mode: str, path: str, key: str) -> tuple[int, int]:
        try:
            return find_range(mode, path, key)
        except (ValueError, OSError) as exc:
            raise HexdumpInputError(str(exc)) from exc


def _summarize(settings: HexdumpSettings) -> str:
    lines = [f"OK: {len(settings.files)} file(s), "
             f"{sum(len(f.shots) for f in settings.files)} shot(s), output folder '{settings.common.out_dir}'."]
    for file in settings.files:
        lines.append(f"\n{file.path}  [APP={file.app}, MODE={file.mode}]")
        for shot in file.shots:
            lines.append(f"  - {shot.name}: key={shot.key}")
    return "\n".join(lines)
