"""Tests for HexdumpAnalyzer settings parsing, plus parity with the legacy Hexdump/Capture_Auto/get_input.py loader."""
import importlib.util
import sys
from pathlib import Path

import pytest

from autohub.services.HexdumpAnalyzer.exceptions import HexdumpSettingsError
from autohub.services.HexdumpAnalyzer.settings import load_settings, parse_settings

LEGACY_CAPTURE = Path(__file__).resolve().parent.parent / "Hexdump" / "Capture_Auto"
NPP = "C:/Program Files/Notepad++/notepad++.exe"


def _write(tmp_path: Path, name: str = "job.toml", body: str = "") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _source(tmp_path: Path) -> str:
    src = tmp_path / "source.txt"
    src.write_text("x", encoding="utf-8")
    return str(src)


def _valid_toml(src: str) -> str:
    return f"""
[common]
OUT = "out_dir"
FIT_W = 800

[[file]]
FILE = '{src}'
APP = "notepad"
MODE = "block"
FIT_H = 500

[[file.shot]]
name = "first"
key = "KEY_A"

[[file.shot]]
name = "second"
key = "KEY_B"
FIT_W = 300
"""


def test_valid_settings_resolve_defaults_and_inheritance(tmp_path):
    src = _source(tmp_path)
    path = _write(tmp_path, body=_valid_toml(src))

    settings = load_settings(str(path), npp_exe=NPP)

    assert settings.common.out_dir == "out_dir"
    assert settings.common.fit_w == 800
    assert settings.common.pad_x == 20 and settings.common.min_w == 400
    assert len(settings.files) == 1
    file = settings.files[0]
    assert (file.path, file.app, file.mode) == (src, "notepad", "block")
    assert (file.fit_w, file.fit_h) == (800, 500)
    assert file.include_header is True and file.include_margin is True and file.force_no_wrap is False
    first, second = file.shots
    assert (first.name, first.key, first.fit_w, first.fit_h) == ("first", "KEY_A", 800, 500)
    assert (second.name, second.key, second.fit_w, second.fit_h) == ("second", "KEY_B", 300, 500)


def test_disabled_entries_are_skipped_and_errors_collected(tmp_path):
    src = _source(tmp_path)
    body = f"""
[[file]]
FILE = '{src}'
APP = "notepad"
MODE = "nope"
enabled = false

[[file]]
FILE = '{src}'
APP = "vim"
MODE = "block"

[[file.shot]]
name = "a/b"
key = ""

[[file.shot]]
name = "a/b"
key = "K"
enabled = false
"""
    with pytest.raises(HexdumpSettingsError) as info:
        parse_settings(_as_dict(body), file_exists=lambda p: True, npp_exe=NPP)
    errors = info.value.errors
    assert len(errors) == 3
    assert "APP must be" in errors[0]
    assert "name must not contain" in errors[1]
    assert "key is required" in errors[2]


def test_all_files_disabled_is_an_error(tmp_path):
    src = _source(tmp_path)
    body = f"""
[[file]]
FILE = '{src}'
enabled = false
"""
    with pytest.raises(HexdumpSettingsError) as info:
        parse_settings(_as_dict(body), file_exists=lambda p: True, npp_exe=NPP)
    assert info.value.errors == ("All files are disabled (enabled = false)",)


def test_npp_requires_executable_when_used(tmp_path):
    src = _source(tmp_path)
    body = f"""
[[file]]
FILE = '{src}'
APP = "npp"
MODE = "cnt"
[[file.shot]]
name = "s"
key = "K"
"""
    with pytest.raises(HexdumpSettingsError) as info:
        parse_settings(_as_dict(body), file_exists=lambda p: p == src, npp_exe=NPP)
    assert info.value.errors == (f"Notepad++ not found: {NPP} (NPP_EXE is fixed in get_input.py; edit it there)",)


def test_missing_settings_file_and_invalid_toml(tmp_path):
    with pytest.raises(HexdumpSettingsError) as info:
        load_settings(str(tmp_path / "absent.toml"), npp_exe=NPP)
    assert info.value.errors == (f"Settings file not found: {tmp_path / 'absent.toml'}",)

    bad = _write(tmp_path, "bad.toml", "[common\nOUT = 1")
    with pytest.raises(HexdumpSettingsError) as info:
        load_settings(str(bad), npp_exe=NPP)
    assert info.value.errors[0].startswith(f"Settings file {bad} has invalid TOML syntax")
    assert "SINGLE quotes" in info.value.errors[1]


def _as_dict(body: str) -> dict:
    import tomllib
    return tomllib.loads(body)


def _load_legacy_get_input(monkeypatch):
    """Import legacy get_input. Its Split_Auto.hsm_dflash runs a Windows-only sample at import time,
    so that one module is replaced by a stub; the settings loader never calls it."""
    from autohub.services.HexdumpAnalyzer.mem_overview_parser import find_mem_overview_block
    stub = type(sys)("Split_Auto.hsm_dflash")
    stub.find_mem_overview_block = find_mem_overview_block
    monkeypatch.setitem(sys.modules, "Split_Auto.hsm_dflash", stub)
    monkeypatch.syspath_prepend(str(LEGACY_CAPTURE))
    spec = importlib.util.spec_from_file_location("legacy_get_input", LEGACY_CAPTURE / "get_input.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_snapshot(legacy, path: str):
    """Run the legacy loader and return its effective per-file/per-shot cfg values."""
    common, files = legacy.load_settings(path)
    legacy.apply_common(common)
    snapshots = []
    for f in files:
        legacy.apply_file(f)
        for shot in f["shots"]:
            legacy.apply_shot(shot)
            snapshots.append({
                "file": f["FILE"], "app": legacy.cfg.APP, "mode": legacy.cfg.MODE,
                "force_no_wrap": legacy.cfg.FORCE_NO_WRAP, "include_header": legacy.cfg.INCLUDE_HEADER,
                "include_margin": legacy.cfg.INCLUDE_MARGIN, "name": legacy.cfg.JOB_NAME,
                "key": legacy.cfg.KEY, "fit_w": legacy.cfg.FIT_W, "fit_h": legacy.cfg.FIT_H,
            })
    return {"out_dir": legacy.cfg.OUT_DIR, "pad_x": legacy.cfg.PAD_X, "min_w": legacy.cfg.MIN_W,
            "scroll_w": legacy.cfg.SCROLL_W, "recalibrate": legacy.cfg.RECALIBRATE,
            "debug": legacy.cfg.DEBUG}, snapshots


@pytest.mark.skipif(not LEGACY_CAPTURE.is_dir(), reason="legacy Hexdump source not present")
def test_parity_with_legacy_loader(tmp_path, monkeypatch):
    src = _source(tmp_path)
    path = _write(tmp_path, body=_valid_toml(src))
    legacy = _load_legacy_get_input(monkeypatch)

    legacy_common, legacy_shots = _legacy_snapshot(legacy, str(path))
    settings = load_settings(str(path), npp_exe=NPP)

    assert settings.common.out_dir == legacy_common["out_dir"]
    assert settings.common.pad_x == legacy_common["pad_x"]
    assert settings.common.min_w == legacy_common["min_w"]
    assert settings.common.scroll_w == legacy_common["scroll_w"]
    assert settings.common.recalibrate == legacy_common["recalibrate"]
    assert settings.common.debug == legacy_common["debug"]
    new_shots = [
        {"file": f.path, "app": f.app, "mode": f.mode, "force_no_wrap": f.force_no_wrap,
         "include_header": f.include_header, "include_margin": f.include_margin,
         "name": s.name, "key": s.key, "fit_w": s.fit_w, "fit_h": s.fit_h}
        for f in settings.files for s in f.shots
    ]
    assert new_shots == legacy_shots


@pytest.mark.skipif(not LEGACY_CAPTURE.is_dir(), reason="legacy Hexdump source not present")
@pytest.mark.parametrize("snippet", [
    '[common]\nFOO = 1\n',
    '[common]\nNPP_EXE = "x"\n',
    '[common]\nPAD_X = -1\nDEBUG = "yes"\n',
    '[nope]\nx = 1\n',
    'file = "not a list"\n',
    '[[file]]\nFILE = "{src}"\nAPP = "notepad"\nMODE = "block"\nINCLUDE_HEADER = "no"\n'
    '[[file.shot]]\nname = "a"\nkey = "k"\nFIT_W = true\n',
    '[[file]]\nFILE = "{src}"\nAPP = "notepad"\nMODE = "block"\n'
    '[[file.shot]]\nname = "a"\nkey = "k"\n[[file.shot]]\nname = "a"\nkey = "k"\n',
    '[[file]]\nFILE = "{src}"\nAPP = "notepad"\nMODE = "block"\nshot = []\n',
])
def test_parity_of_validation_messages_with_legacy(tmp_path, snippet, capsys, monkeypatch):
    src = _source(tmp_path)
    path = _write(tmp_path, body=snippet.replace("{src}", src))
    legacy = _load_legacy_get_input(monkeypatch)

    with pytest.raises(SystemExit):
        legacy.load_settings(str(path))
    legacy_lines = [line.strip()[2:] for line in capsys.readouterr().out.splitlines() if line.strip().startswith("- ")]

    with pytest.raises(HexdumpSettingsError) as info:
        load_settings(str(path), npp_exe=legacy.cfg.NPP_EXE)
    assert list(info.value.errors) == legacy_lines
