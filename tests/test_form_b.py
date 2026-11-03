import zlib
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import openpyxl
import pytest

from autohub.core.checksums import crc32_file, normalize_crc32
from autohub.services.FormB.form_b import FormBService, export_form_b
from autohub.services.MasterSheet.webflow_variants import webflow_variant_from_row
from autohub.services.common.encrypted_workbook import decrypt_workbook
from autohub.services.WebFlow import WebFlow as webflow_module
from autohub.services.WebFlow.FilesTab import FilesTab
from autohub.services.WebFlow.WebFlow import WebFlow
from autohub.modules.form_b.ui import FormBWidget
from autohub.modules.form_b import ui as form_b_ui
from autohub.core.settings import JsonSettingsStore
from tests.fakes import MemorySettings

TEMPLATE = Path("datas/FormB/62XS_MP2_FORMB_MG1CS022_20260511.xlsx")


@pytest.fixture(autouse=True)
def isolate_form_b_settings(monkeypatch):
    monkeypatch.setattr(form_b_ui, "JsonSettingsStore", MemorySettings)


def variant(index: int, checksum=""):
    return {
        "part_number": f"PART-{index}",
        "webflow_link": f"https://webflow/app/ShowJob/{index}",
        "project": "62XS",
        "event_name": "CERT_MP1",
        "ecu_type": "MG1CS022",
        "form_b": {
            "AP": "MG1CS022",
            "AN": f"0261S10BC{index}",
            "AR": f"37820-62X-MD{index}-M6",
            "AX": f"10SW1334{index:02}",
            "AZ": f"base-{index}.hex",
            "BA": checksum,
            "AW": f"3E1018167{index}",
            "AD": "Active|IMMO6",
            "BG": "TP3",
            "CX": f"37820-62X-MD{index}",
            "CY": "7C8",
            "CZ": f"SS{index}",
        },
    }


def test_master_sheet_variant_keeps_form_b_source_values():
    converted = webflow_variant_from_row("PART-1", {"AP": "MG1CS022", "BA": 232761, "AN": "HW-1"})
    assert converted["form_b"] == {
        "AP": "MG1CS022", "AN": "HW-1", "AR": "", "AX": "", "AZ": "",
        "BA": 232761, "AW": "", "AD": "", "BG": "", "CX": "", "CY": "", "CZ": "",
    }


@pytest.mark.parametrize(("value", "expected"), [
    ("689d1972", "689D1972"),
    (232761, "00038D39"),
    (None, ""),
    ("---", ""),
])
def test_normalize_crc32(value, expected):
    assert normalize_crc32(value) == expected


def test_checksum_is_calculated_from_file_in_uppercase(tmp_path):
    path = tmp_path / "container.cnt"
    path.write_bytes(b"123456789")
    assert crc32_file(path) == f"{zlib.crc32(b'123456789'):08X}" == "CBF43926"


def test_form_b_uses_master_checksum_without_opening_webflow(tmp_path):
    webflow = Mock()
    service = FormBService(lambda: webflow)
    output = service.generate([variant(1, "abcd1234")], tmp_path / "form.xlsx")
    assert output.name.startswith("62XS_MP1_FORMB_MG1CS022_")
    workbook = openpyxl.load_workbook(output, data_only=True)
    try:
        sheet = workbook["FormB"]
        assert sheet["B26"].value == "62X -MD1"
        assert sheet["B35"].value == "ABCD1234"
        assert sheet["B37"].value == "IMMO6"
        assert sheet["B38"].value == "TPROT=3"
        assert sheet["B34"].value == "10SW133401.cnt"
        assert sheet["B24"].value == "MG1CS022"
        webflow.get_container_crc32.assert_not_called()
    finally:
        workbook.close()


def test_missing_master_checksum_uses_webflow_crc(tmp_path):
    webflow = Mock()
    webflow.get_container_crc32.return_value = "689d1972"
    output = FormBService(lambda: webflow).generate([variant(1)], tmp_path / "form.xlsx")
    workbook = openpyxl.load_workbook(output, data_only=True)
    try:
        assert workbook["FormB"]["B35"].value == "689D1972"
    finally:
        workbook.close()
    webflow.get_container_crc32.assert_called_once_with(
        "https://webflow/app/ShowJob/1", "10SW133401.cnt"
    )
    webflow.quit.assert_called_once()


def test_missing_checksum_without_webflow_link_fails_before_opening_browser(tmp_path):
    webflow_factory = Mock()
    item = variant(1)
    item["webflow_link"] = ""
    with pytest.raises(ValueError, match="no WebFlow job is linked"):
        FormBService(webflow_factory).generate([item], tmp_path / "form.xlsx")
    webflow_factory.assert_not_called()


@pytest.mark.parametrize(("count", "last_block_row", "footer_row"), [
    (1, 26, 42),
    (6, 26, 42),
    (7, 42, 56),
    (12, 42, 56),
])
def test_form_b_variants_fill_six_column_blocks_and_keep_template_formatting(
    tmp_path, count, last_block_row, footer_row
):
    variants = [variant(index) for index in range(1, count + 1)]
    output = export_form_b(variants, {item["part_number"]: "00000001" for item in variants}, tmp_path / "form.xlsx")
    workbook = openpyxl.load_workbook(output, data_only=True)
    template = openpyxl.load_workbook(decrypt_workbook(str(TEMPLATE)))
    try:
        sheet = workbook["FormB"]
        template_sheet = template["FormB"]
        assert sheet["B26"].value == "62X -MD1"
        assert sheet["G26"].value == ("62X -MD6" if count >= 6 else None)
        if count > 6:
            assert sheet["B42"].value == "62X -MD7"
            assert sheet["G42"].value == ("62X -MD12" if count >= 12 else None)
        assert sheet[f"A{footer_row}"].value.startswith("Please review")
        assert sheet["B26"]._style == template_sheet["B26"]._style
        if count > 6:
            assert sheet["B42"]._style == template_sheet["B26"]._style
        assert sheet.max_row >= last_block_row
    finally:
        workbook.close()
        template.close()


def test_form_b_filename_uses_master_fields_and_generation_date(tmp_path):
    output = export_form_b(
        [variant(1)],
        {"PART-1": "00000001"},
        tmp_path / "selected-name.xlsx",
        today=date(2026, 3, 26),
    )
    assert output.name == "62XS_MP1_FORMB_MG1CS022_20260326.xlsx"


@pytest.mark.parametrize("count,receipt_row", [(1, 43), (7, 57), (13, 71)])
def test_form_b_information_overwrites_template_header_without_changing_formatting(tmp_path, count, receipt_row):
    form_information = {
        "department_organization": "Engineering",
        "name": "Alex Example",
        "phone_number": "+1 555 0100",
        "date": date(2026, 11, 3),
        "return_to": "Release Team",
        "project_release": "Project Alpha",
        "production_project": "Production Beta",
        "bosch_project_number": "BOSCH-123",
        "ecu_type": "ECU-ABC",
        "expected_receipt_date": date(2027, 2, 8),
    }
    variants = [variant(index) for index in range(1, count + 1)]
    output = export_form_b(
        variants,
        {item["part_number"]: "00000001" for item in variants},
        tmp_path / "selected-name.xlsx",
        today=date(2026, 3, 26),
        form_information=form_information,
    )
    baseline_output = export_form_b(
        variants,
        {item["part_number"]: "00000001" for item in variants},
        tmp_path / "baseline" / "selected-name.xlsx",
        today=date(2026, 3, 26),
    )
    workbook = openpyxl.load_workbook(output, data_only=True)
    template = openpyxl.load_workbook(decrypt_workbook(str(TEMPLATE)), data_only=True)
    baseline = openpyxl.load_workbook(baseline_output, data_only=True)
    try:
        sheet = workbook["FormB"]
        template_sheet = template["FormB"]
        assert sheet["C3"].value == "Engineering"
        assert sheet["C4"].value == "Alex Example"
        assert sheet["C5"].value == "Phone No.: +1 555 0100"
        assert sheet["C13"].value.date() == date(2026, 11, 3)
        assert sheet["A18"].value.endswith("to Release Team")
        assert sheet["A21"].value == "(Production release for project) : Project Alpha"
        assert sheet["A22"].value == "For Production Beta production"
        assert sheet["B23"].value == "BOSCH-123"
        assert sheet["B24"].value == "ECU-ABC"
        assert sheet[f"A{receipt_row}"].value == "We appreciate the receipt by 8 February 2027"
        assert sheet[f"A{receipt_row}"]._style == template_sheet["A43"]._style
        for cell in ("C3", "C4", "C5", "C13", "A18", "A21", "A22", "B23", "B24"):
            assert sheet[cell]._style == template_sheet[cell]._style
        assert sheet.merged_cells.ranges == template_sheet.merged_cells.ranges
        assert [sheet.row_dimensions[row].height for row in range(1, sheet.max_row + 1)] == [
            baseline["FormB"].row_dimensions[row].height for row in range(1, sheet.max_row + 1)
        ]
        assert {
            column: sheet.column_dimensions[column].width
            for column in sheet.column_dimensions
        } == {
            column: template_sheet.column_dimensions[column].width
            for column in template_sheet.column_dimensions
        }
    finally:
        workbook.close()
        template.close()
        baseline.close()


def test_form_b_information_defaults_to_today_with_placeholder_only_examples(qapp):
    widget = FormBWidget(Mock(), Mock())
    date_field = widget._form_fields["date"]
    assert date_field.text() == date.today().isoformat()
    assert date_field.placeholderText() == "YYYY-MM-DD"
    assert not date_field.isReadOnly()
    for key, field in widget._form_fields.items():
        if key != "date":
            assert field.text() == ""
            assert field.placeholderText().startswith("e.g. ")

    values, invalid_fields = widget._collect_form_information()
    assert values == {"date": date.today()}
    assert len(invalid_fields) == 9
    date_field.setText("2027-01-15")
    values, _ = widget._collect_form_information()
    assert values["date"] == date(2027, 1, 15)


def test_form_b_information_requires_every_field_and_valid_date(qapp):
    dialogs = Mock()
    widget = FormBWidget(Mock(), dialogs)
    item = variant(1)
    widget.set_variants([item])
    widget._checklist._checkboxes[item["part_number"]].setChecked(True)
    for field in widget._form_fields.values():
        field.clear()
    values, invalid_fields = widget._collect_form_information()
    assert values == {}
    assert invalid_fields == [
        "Department / Organization",
        "Name",
        "Phone Number",
        "Date",
        "Return To",
        "Project / Production Release Project",
        "Production Project",
        "Bosch Project Number",
        "ECU-Type",
        "Expected Receipt Date",
    ]
    widget._export()
    assert all(field in dialogs.error.call_args.args[1] for field in invalid_fields)
    dialogs.save_file.assert_not_called()

    for key, field in widget._form_fields.items():
        field.setText(
            "2026-02-30" if key == "date" else
            "8 February 2027" if key == "expected_receipt_date" else f"value-{key}"
        )
    values, invalid_fields = widget._collect_form_information()
    assert "Date (use YYYY-MM-DD)" in invalid_fields
    assert len(invalid_fields) == 1
    widget._export()
    assert "Date (use YYYY-MM-DD)" in dialogs.error.call_args.args[1]
    dialogs.save_file.assert_not_called()

    widget._form_fields["date"].setText("2026-11-03")
    values, invalid_fields = widget._collect_form_information()
    assert not invalid_fields
    assert values["date"] == date(2026, 11, 3)
    assert values["expected_receipt_date"] == date(2027, 2, 8)
    widget._form_fields["expected_receipt_date"].setText("31 February 2027")
    _, invalid_fields = widget._collect_form_information()
    assert len(invalid_fields) == 1
    assert invalid_fields[0].startswith("Expected Receipt Date (use DD Month YYYY")


def test_form_b_export_passes_form_information_to_generator(qapp):
    service = Mock()
    dialogs = Mock()
    dialogs.save_file.return_value = "selected.xlsx"
    widget = FormBWidget(service, dialogs)
    item = variant(1)
    widget.set_variants([item])
    widget._checklist._checkboxes[item["part_number"]].setChecked(True)
    for key, field in widget._form_fields.items():
        field.setText(
            "2026-11-03" if key == "date" else
            "8 February 2027" if key == "expected_receipt_date" else f"value-{key}"
        )

    widget._tasks.start = Mock()
    widget._export()
    work = widget._tasks.start.call_args.args[0]
    work()

    service.generate.assert_called_once_with(
        [item],
        "selected.xlsx",
        dialogs.open_progress.return_value.step,
        {
            "department_organization": "value-department_organization",
            "name": "value-name",
            "phone_number": "value-phone_number",
            "date": date(2026, 11, 3),
            "return_to": "value-return_to",
            "project_release": "value-project_release",
            "production_project": "value-production_project",
            "bosch_project_number": "value-bosch_project_number",
            "ecu_type": "value-ecu_type",
            "expected_receipt_date": date(2027, 2, 8),
        },
    )


def test_form_b_master_information_uses_loaded_and_selected_values_without_overwriting_edits(qapp):
    widget = FormBWidget(Mock(), Mock())
    first, second = variant(1), variant(2)
    widget.set_variants([first, second])
    assert widget._form_fields["project_release"].text() == "62XS"
    assert widget._form_fields["production_project"].text() == "62XS MP1"
    assert widget._form_fields["ecu_type"].text() == "MG1CS022"
    for key in ("department_organization", "name", "phone_number", "return_to", "bosch_project_number"):
        assert widget._form_fields[key].text() == ""
        assert widget._form_fields[key].placeholderText()
    for field in widget._form_fields.values():
        assert not field.isReadOnly()

    widget._form_fields["project_release"].setText("User release project")
    widget._form_fields["date"].setText("2027-01-15")
    second.update(project="OTHER", event_name="CERT_MP2")
    second["form_b"]["AP"] = "OTHER-ECU"
    widget.set_variants([first, second])
    assert widget._form_fields["project_release"].text() == "User release project"
    assert widget._form_fields["production_project"].text() == ""
    assert widget._form_fields["ecu_type"].text() == ""
    widget._checklist._checkboxes[second["part_number"]].setChecked(True)
    assert widget._form_fields["production_project"].text() == "OTHER MP2"
    assert widget._form_fields["ecu_type"].text() == "OTHER-ECU"
    assert widget._form_fields["project_release"].text() == "OTHER"
    assert widget._form_fields["date"].text() == "2027-01-15"
    widget.set_variants([])
    assert widget._form_fields["production_project"].text() == ""
    assert widget._form_fields["ecu_type"].text() == ""
    assert widget._form_fields["project_release"].text() == ""


def test_form_b_restores_non_date_inputs_and_saves_changes(qapp, tmp_path):
    settings = JsonSettingsStore(tmp_path / "settings.json")
    widget = FormBWidget(Mock(), Mock(), settings)
    for key, field in widget._form_fields.items():
        field.setText(
            "2027-01-15" if key == "date" else
            "8 February 2027" if key == "expected_receipt_date" else f"saved-{key}"
        )
    saved = settings.load()[form_b_ui.FORM_B_INPUTS_KEY]
    assert set(saved) == set(widget._form_fields) - {"date", "expected_receipt_date"}
    reopened = FormBWidget(Mock(), Mock(), JsonSettingsStore(tmp_path / "settings.json"))
    assert reopened._form_fields["date"].text() == date.today().isoformat()
    assert reopened._form_fields["expected_receipt_date"].text() == ""
    for key, value in saved.items():
        assert reopened._form_fields[key].text() == value
    reopened.set_variants([variant(1)])
    assert reopened._form_fields["project_release"].text() == "62XS"
    assert reopened._form_fields["production_project"].text() == "62XS MP1"
    assert reopened._form_fields["ecu_type"].text() == "MG1CS022"
    assert reopened._form_fields["name"].text() == "saved-name"
    reopened._form_fields["project_release"].setText("edited project")
    reopened.set_variants([variant(1)])
    assert reopened._form_fields["project_release"].text() == "62XS"
    reopened._form_fields["name"].clear()
    assert settings.load()[form_b_ui.FORM_B_INPUTS_KEY]["name"] == ""


def test_form_b_ignores_previously_saved_date_fields(qapp):
    settings = MemorySettings({form_b_ui.FORM_B_INPUTS_KEY: {
        "date": "2000-01-01",
        "expected_receipt_date": "1 January 2000",
        "name": "Saved name",
    }})
    widget = FormBWidget(Mock(), Mock(), settings)
    assert widget._form_fields["date"].text() == date.today().isoformat()
    assert widget._form_fields["expected_receipt_date"].text() == ""
    widget._export()
    assert settings.load()[form_b_ui.FORM_B_INPUTS_KEY]["name"] == "Saved name"
    assert "date" not in settings.load()[form_b_ui.FORM_B_INPUTS_KEY]
    assert "expected_receipt_date" not in settings.load()[form_b_ui.FORM_B_INPUTS_KEY]


def test_form_b_missing_master_information_keeps_placeholders(qapp):
    widget = FormBWidget(Mock(), Mock())
    widget.set_variants([{"part_number": "PART-1", "ecu_type": "", "form_b": {}}])
    for key in ("project_release", "production_project", "ecu_type"):
        assert widget._form_fields[key].text() == ""
        assert widget._form_fields[key].placeholderText()


def test_form_b_filename_sanitizes_invalid_path_characters(tmp_path):
    item = variant(1)
    item.update(project="62XS:Test", ecu_type="MG1/CS022")
    output = export_form_b(
        [item],
        {"PART-1": "00000001"},
        tmp_path / "selected-name.xlsx",
        today=date(2026, 3, 26),
    )
    assert output.name == "62XS_Test_MP1_FORMB_MG1_CS022_20260326.xlsx"


def test_form_b_rejects_variants_with_different_filename_fields(tmp_path):
    with pytest.raises(ValueError, match="same Master Sheet Project, Phase and ECU Type"):
        export_form_b(
            [variant(1), {**variant(2), "project": "OTHER"}],
            {"PART-1": "00000001", "PART-2": "00000002"},
            tmp_path / "selected-name.xlsx",
            today=date(2026, 3, 26),
        )


class FastWait:
    def __init__(self, _driver, *_args, **_kwargs):
        pass

    def until(self, condition):
        for _ in range(5):
            result = condition(None)
            if result:
                return result
        raise RuntimeError("wait timed out")


def test_files_tab_download_fallback_calculates_crc32(monkeypatch):
    driver = Mock()
    directory = []

    def configure(_command, parameters):
        directory.append(Path(parameters["downloadPath"]))

    driver.execute_cdp_cmd.side_effect = configure
    row, file_cell, crc_cell, link = Mock(), Mock(), Mock(), Mock()
    row.find_elements.return_value = [Mock(), file_cell, crc_cell]
    file_cell.find_elements.return_value = [link]
    crc_cell.text = ""
    link.click.side_effect = lambda: (directory[0] / "container.cnt").write_bytes(b"123456789")
    files = FilesTab(driver)
    monkeypatch.setattr(files, "_execution_file", lambda _filename: (row, 1, 2, [Mock(), file_cell, crc_cell]))
    monkeypatch.setattr("autohub.services.WebFlow.FilesTab.WebDriverWait", FastWait)
    assert files.container_crc32("container.cnt") == "CBF43926"
    assert not directory[0].exists()


def test_webflow_opens_linked_job_and_reads_file_checksum(monkeypatch):
    session = Mock()
    session.open_job.return_value = True
    tab = Mock()
    tab.select_files_tab.return_value = True
    tab.container_crc32.return_value = "689D1972"
    monkeypatch.setattr(webflow_module, "FilesTab", lambda _driver: tab)
    assert WebFlow.get_container_crc32(
        session, "https://webflow/app/ShowJob/42", "10SW137784.cnt"
    ) == "689D1972"
    session.open_job.assert_called_once_with("42", url="https://webflow/app/ShowJob/42")
    tab.container_crc32.assert_called_once_with("10SW137784.cnt")
