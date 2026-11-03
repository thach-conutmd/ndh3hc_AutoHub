import hashlib
from pathlib import Path

import pytest

from autohub.modules.home.service import copy_master_sheet_template, master_sheet_copy_name


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_copy_name_follows_required_pattern():
    assert master_sheet_copy_name("ABC123") == "Honda_ABC123_Container_MasterSheet_r00.xlsx"


def test_copy_name_sanitizes_path_characters():
    assert master_sheet_copy_name('A/B:C*"') == "Honda_A_B_C__Container_MasterSheet_r00.xlsx"


def test_copy_name_requires_project():
    with pytest.raises(ValueError):
        master_sheet_copy_name("   ")


def test_copy_creates_new_file_and_leaves_template_unchanged(tmp_path):
    template = tmp_path / "template.xlsx"
    template.write_bytes(b"original master content")
    before = _digest(template)

    created = copy_master_sheet_template(str(template), "PRJ1")

    assert Path(created) == tmp_path / "Honda_PRJ1_Container_MasterSheet_r00.xlsx"
    assert Path(created).read_bytes() == b"original master content"
    assert _digest(template) == before


def test_copy_never_overwrites_existing_file(tmp_path):
    template = tmp_path / "template.xlsx"
    template.write_bytes(b"template")
    existing = tmp_path / "Honda_PRJ1_Container_MasterSheet_r00.xlsx"
    existing.write_bytes(b"user work")

    with pytest.raises(ValueError, match="already exists"):
        copy_master_sheet_template(str(template), "PRJ1")

    assert existing.read_bytes() == b"user work"


def test_copy_failure_removes_partial_copy(tmp_path, monkeypatch):
    template = tmp_path / "template.xlsx"
    template.write_bytes(b"template")

    import autohub.modules.home.service as service

    def broken_copy(reader, writer):
        writer.write(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(service.shutil, "copyfileobj", broken_copy)

    with pytest.raises(OSError):
        copy_master_sheet_template(str(template), "PRJ1")

    assert not (tmp_path / "Honda_PRJ1_Container_MasterSheet_r00.xlsx").exists()
    assert template.read_bytes() == b"template"
