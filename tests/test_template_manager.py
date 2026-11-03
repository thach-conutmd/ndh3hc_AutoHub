from pathlib import Path

import openpyxl
import pytest

from autohub.core.templates import FORM_B_TEMPLATE, MASTER_SHEET_TEMPLATE, TemplateManager


class MemorySettings:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def load(self):
        return dict(self.data)

    def update(self, **kwargs):
        self.data.update(kwargs)


def _xlsx(path: Path) -> str:
    workbook = openpyxl.Workbook()
    workbook.save(path)
    return str(path)


def test_problem_reports_missing_path_with_spec_message(tmp_path):
    manager = TemplateManager(MemorySettings({MASTER_SHEET_TEMPLATE.settings_key: str(tmp_path / "gone.xlsx")}))
    assert manager.problem(MASTER_SHEET_TEMPLATE) == MASTER_SHEET_TEMPLATE.missing_message


def test_problem_rejects_non_xlsx(tmp_path):
    text = tmp_path / "template.txt"
    text.write_text("x")
    manager = TemplateManager(MemorySettings())
    assert manager.problem(FORM_B_TEMPLATE, str(text)) == FORM_B_TEMPLATE.missing_message


def test_problem_uses_load_check_and_catches_exceptions(tmp_path):
    path = _xlsx(tmp_path / "template.xlsx")

    def broken(_path):
        raise OSError("corrupt")

    assert TemplateManager(MemorySettings(), load_checks={"form_b": broken}).problem(FORM_B_TEMPLATE, path) == (
        FORM_B_TEMPLATE.missing_message
    )
    assert TemplateManager(MemorySettings(), load_checks={"form_b": lambda _p: ""}).problem(
        FORM_B_TEMPLATE, path
    ) == ""


def test_path_prefers_configured_over_default(tmp_path):
    configured = _xlsx(tmp_path / "mine.xlsx")
    manager = TemplateManager(
        MemorySettings({FORM_B_TEMPLATE.settings_key: configured}),
        defaults={"form_b": "bundled.xlsx"},
    )
    assert manager.path(FORM_B_TEMPLATE) == configured
    assert TemplateManager(MemorySettings(), defaults={"form_b": "bundled.xlsx"}).path(FORM_B_TEMPLATE) == "bundled.xlsx"


def test_require_raises_spec_message_when_invalid(tmp_path):
    manager = TemplateManager(MemorySettings())
    with pytest.raises(ValueError, match="Form B template is not available"):
        manager.require(FORM_B_TEMPLATE)


def test_save_persists_path_to_settings_store(tmp_path):
    store = MemorySettings()
    path = _xlsx(tmp_path / "form_b.xlsx")
    TemplateManager(store).save(FORM_B_TEMPLATE, path)
    assert store.load()[FORM_B_TEMPLATE.settings_key] == path
