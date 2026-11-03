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


BUILT_IN = Path("datas/templates/Form_B_Default_Template.xlsx")


def test_resolve_falls_back_to_built_in_when_custom_is_invalid(tmp_path):
    manager = TemplateManager(
        MemorySettings({FORM_B_TEMPLATE.settings_key: str(tmp_path / "gone.xlsx")}),
        defaults={FORM_B_TEMPLATE.name: str(BUILT_IN)},
    )
    assert manager.resolve(FORM_B_TEMPLATE) == str(BUILT_IN)
    assert manager.require(FORM_B_TEMPLATE) == str(BUILT_IN)
    assert manager.problem(FORM_B_TEMPLATE) == ""


def test_require_raises_when_custom_and_built_in_are_invalid(tmp_path):
    manager = TemplateManager(
        MemorySettings({FORM_B_TEMPLATE.settings_key: str(tmp_path / "gone.xlsx")}),
        defaults={FORM_B_TEMPLATE.name: str(tmp_path / "also_gone.xlsx")},
    )
    assert manager.problem(FORM_B_TEMPLATE) == FORM_B_TEMPLATE.missing_message
    with pytest.raises(ValueError, match="^Form B template is not available. Please select a valid template in Settings.$"):
        manager.require(FORM_B_TEMPLATE)


def test_seed_default_configures_built_in_on_first_run_only(tmp_path):
    settings = MemorySettings()
    manager = TemplateManager(settings, defaults={FORM_B_TEMPLATE.name: str(BUILT_IN.resolve())})
    manager.seed_default(FORM_B_TEMPLATE)
    assert settings.load()[FORM_B_TEMPLATE.settings_key] == str(BUILT_IN.resolve())

    custom = _xlsx(tmp_path / "custom.xlsx")
    manager.save(FORM_B_TEMPLATE, custom)
    manager.seed_default(FORM_B_TEMPLATE)
    assert settings.load()[FORM_B_TEMPLATE.settings_key] == custom


def test_seed_default_keeps_cleared_setting_and_skips_missing_built_in(tmp_path):
    settings = MemorySettings({FORM_B_TEMPLATE.settings_key: ""})
    TemplateManager(settings, defaults={FORM_B_TEMPLATE.name: str(BUILT_IN)}).seed_default(FORM_B_TEMPLATE)
    assert settings.load()[FORM_B_TEMPLATE.settings_key] == ""

    fresh = MemorySettings()
    TemplateManager(fresh, defaults={FORM_B_TEMPLATE.name: str(tmp_path / "missing.xlsx")}).seed_default(FORM_B_TEMPLATE)
    assert FORM_B_TEMPLATE.settings_key not in fresh.load()


def test_form_b_service_stops_before_webflow_when_no_template_is_usable(tmp_path):
    from autohub.services.FormB.form_b import FormBService

    def fail_factory():
        raise AssertionError("WebFlow must not start without a valid template")

    templates = TemplateManager(MemorySettings(), defaults={FORM_B_TEMPLATE.name: str(tmp_path / "none.xlsx")})
    service = FormBService(fail_factory, templates=templates)
    with pytest.raises(ValueError, match="Form B template is not available"):
        service.generate([{"part_number": "P1"}], tmp_path / "out.xlsx")
    assert not (tmp_path / "out.xlsx").exists()


def test_export_from_built_in_template_keeps_template_and_layout(tmp_path):
    import hashlib

    from autohub.services.common.encrypted_workbook import decrypt_workbook
    from autohub.services.FormB.form_b import export_form_b

    template = BUILT_IN.resolve()
    before = hashlib.sha256(template.read_bytes()).hexdigest()
    variant = {
        "part_number": "PART-1", "project": "62XS", "event_name": "CERT_MP1", "ecu_type": "MG1CS022",
        "form_b": {"AP": "MG1CS022", "AN": "0261S10BC1", "AR": "37820-62X-MD1-M6", "CS": "37820-62X-MD1-M6",
                   "AX": "1033400001", "AZ": "base.hex", "BA": "", "AW": "3E10181671", "AD": "Active|IMMO6",
                   "BG": "TP3", "CX": "37820-62X-MD1", "CY": "7C8", "CZ": "SS1"},
    }
    output = export_form_b([variant], {"PART-1": "12345678"}, tmp_path / "form.xlsx", template)
    assert hashlib.sha256(template.read_bytes()).hexdigest() == before

    source = openpyxl.load_workbook(decrypt_workbook(str(template)))["FormB"]
    result = openpyxl.load_workbook(output)["FormB"]
    try:
        assert {str(r) for r in source.merged_cells.ranges} <= {str(r) for r in result.merged_cells.ranges}
        for letter, dimension in source.column_dimensions.items():
            assert result.column_dimensions[letter].width == dimension.width
        for index, dimension in source.row_dimensions.items():
            if dimension.height is not None:
                assert result.row_dimensions[index].height == dimension.height
    finally:
        source.parent.close()
        result.parent.close()
