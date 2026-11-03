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
from autohub.modules.form_b.variant_checklist import FormBVariantChecklist
from autohub.core.settings import JsonSettingsStore
from autohub.core.settings_keys import FORM_B_FIELD_VISIBILITY, FORM_B_PROJECT_SUFFIX_KEY
from autohub.core.form_b import form_b_phase, master_phase
from autohub.core.progress_dialog import ProgressDialog
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
            "CS": f"37820-62X-MD{index}-M6",
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
        "AP": "MG1CS022", "AN": "HW-1", "AR": "", "CS": "", "AX": "", "AZ": "",
        "BA": 232761, "AW": "", "AD": "", "BG": "", "CX": "", "CY": "", "CZ": "",
    }


def test_form_b_table_columns_and_crc_refresh_preserve_variant_data(qapp):
    checklist = FormBVariantChecklist()
    first, second = variant(1, "000abc12"), variant(2, "*****")
    first["ecu"] = {"family_name": "Family", "project_version": "Project", "program_version": "V123"}
    first["hardware"] = {"software_part_number": "SW1", "ecr_number": "ECR1"}
    checklist.set_variants([first, second])
    table = checklist._table
    assert [table.horizontalHeaderItem(i).text() for i in range(8)] == [
        "Select", "Part Number", "Family Name", "FSWID Project Version",
        "WebFlow Link", "SW Part Number", "CRC", "ECR Number",
    ]
    assert [table.item(0, i).text() for i in (1, 2, 3, 5, 6, 7)] == [
        "PART-1", "Family", "Project", "SW1", "000ABC12", "ECR1",
    ]
    assert table.cellWidget(0, 4).text() == "WF1"
    assert table.cellWidget(0, 5) is None
    assert table.item(1, 6).text() == "-"
    checklist._checkboxes["PART-2"].setChecked(True)
    second["form_b"]["BA"] = "12345678"
    checklist.refresh_checksums()
    assert table.item(1, 6).text() == "12345678"
    assert checklist._checkboxes["PART-2"].isChecked()
    checklist._apply_filter()
    qapp.processEvents()
    assert table.cellWidget(0, 4).text() == "WF1"
    assert table.item(1, 6).text() == "12345678"
    assert first["ecu"]["program_version"] == "V123"


@pytest.mark.parametrize("callback", ["_finish", "_fail"])
def test_form_b_completion_refreshes_successful_checksum_writebacks(qapp, callback):
    widget = FormBWidget(Mock(), Mock())
    item = variant(1, "*****")
    widget.set_variants([item])
    widget._checklist._checkboxes["PART-1"].setChecked(True)
    item["form_b"]["BA"] = "ABCDEF12"
    getattr(widget, callback)("result", Mock())
    assert widget._checklist._table.item(0, 6).text() == "ABCDEF12"
    assert widget._checklist._checkboxes["PART-1"].isChecked()


def test_form_b_customer_hardware_mapping_keeps_selected_rows_together(tmp_path):
    variants = []
    for index, (hardware, label) in enumerate((
        ("37820-62X-MD20-M6", "62X-MD20"),
        ("37820-62X-ME20-M6", "62X-ME20"),
        ("37820-65A-T31", "65A-T31"),
        ("37820-62X-MG20-M6", "62X-MG20"),
        ("37820-62X-MH20-M6", "62X-MH20"),
        ("37820-62X-MJ20-M6", "62X-MJ20"),
        (" 37820-62X-MK20-M6 ", "62X-MK20"),
    )):
        variants.append(webflow_variant_from_row(f"UNRELATED-SW-{index}", {
            "H": "62XS - CERT_MP1",
            "S": "MG1CS022",
            "AR": f"UNRELATED-CUSTOMER-HW-{index}",
            "CS": hardware,
            "AN": f"RB-HW-{index}",
            "AX": f"RB-SW-{index}",
            "AS": f"CUSTOMER-SW-{index}",
        }))
        assert variants[-1]["form_b"]["CS"] == hardware
        assert variants[-1]["unmapped_fields"]["CS (DWG NO.)"] == hardware.strip()
        variants[-1]["expected_label"] = label
    selected = [variants[index] for index in (1, 0, 4, 3, 5, 2, 6)]
    output = export_form_b(selected, {}, tmp_path / "form.xlsx")
    workbook = openpyxl.load_workbook(output)
    try:
        sheet = workbook["FormB"]
        for index, item in enumerate(selected):
            column, row = index % 6 + 2, 26 if index < 6 else 42
            hardware = item["form_b"]["CS"]
            assert sheet.cell(row, column).value == item["expected_label"]
            assert sheet.cell(row + 1, column).value == hardware
            assert sheet.cell(row + 2, column).value == item["form_b"]["AN"]
            assert sheet.cell(row + 3, column).value == item["form_b"]["AX"]
    finally:
        workbook.close()


def test_form_b_missing_customer_hardware_does_not_use_sw_part_number(tmp_path):
    item = variant(1)
    item["form_b"]["CS"] = ""
    output = export_form_b([item], {}, tmp_path / "form.xlsx")
    workbook = openpyxl.load_workbook(output)
    try:
        assert workbook["FormB"]["B26"].value is None
        assert workbook["FormB"]["B27"].value is None
    finally:
        workbook.close()


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
        assert sheet["B26"].value == "62X-MD1"
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


def test_retrieved_crc_is_saved_only_for_the_matching_variant(tmp_path):
    browser, sheet = Mock(), Mock()
    browser.get_container_crc32.return_value = "000abc12"
    sheet.write_container_checksums.return_value = 1
    factory = Mock(return_value=sheet)
    session = Mock()
    session.__enter__ = Mock()
    session.__exit__ = Mock(return_value=False)
    existing, missing = variant(1, "12345678"), variant(2, "*****")
    output = FormBService(
        lambda: browser, master_sheet_factory=factory, session_factory=lambda: session,
    ).generate([existing, missing], tmp_path / "form.xlsx", master_sheet_path="master.xlsx")
    factory.assert_called_once_with("master.xlsx")
    sheet.write_container_checksums.assert_called_once_with({"PART-2": "000ABC12"})
    sheet.open.assert_called_once()
    sheet.close.assert_called_once()
    session.__enter__.assert_called_once()
    session.__exit__.assert_called_once()
    assert existing["form_b"]["BA"] == "12345678"
    assert missing["form_b"]["BA"] == "000ABC12"
    workbook = openpyxl.load_workbook(output)
    try:
        assert workbook["FormB"]["B35"].value == "12345678"
        assert workbook["FormB"]["C35"].value == "000ABC12"
    finally:
        workbook.close()


@pytest.mark.parametrize("failure", ["", RuntimeError("CRC retrieval failed")])
def test_crc_failure_keeps_failed_variant_untouched_and_previous_success_saved(tmp_path, failure):
    browser, sheet = Mock(), Mock()
    browser.get_container_crc32.side_effect = ["ABCDEF12", failure]
    sheet.write_container_checksums.return_value = 1
    first, second = variant(1, "*****"), variant(2, "*****")
    service = FormBService(lambda: browser, master_sheet_factory=lambda _: sheet)
    with pytest.raises(RuntimeError):
        service.generate([first, second], tmp_path / "form.xlsx", master_sheet_path="master.xlsx")
    sheet.write_container_checksums.assert_called_once_with({"PART-1": "ABCDEF12"})
    assert first["form_b"]["BA"] == "ABCDEF12"
    assert second["form_b"]["BA"] == "*****"
    browser.quit.assert_called_once()


@pytest.mark.parametrize("error", [
    PermissionError("Workbook locked"),
    ValueError("No Master Sheet row found"),
    OSError("Save failed"),
])
def test_crc_writeback_failure_is_reported_without_marking_variant_as_saved(tmp_path, error):
    browser, sheet = Mock(), Mock()
    browser.get_container_crc32.return_value = "ABCDEF12"
    sheet.write_container_checksums.side_effect = error
    item = variant(1, "*****")
    service = FormBService(lambda: browser, master_sheet_factory=lambda _: sheet)
    with pytest.raises(type(error), match=str(error)):
        service.generate([item], tmp_path / "form.xlsx", master_sheet_path="master.xlsx")
    sheet.close.assert_called_once()
    browser.quit.assert_called_once()
    assert item["form_b"]["BA"] == "*****"


def test_master_checksum_does_not_trigger_writeback(tmp_path):
    factory = Mock()
    service = FormBService(Mock(), master_sheet_factory=factory)
    service.generate([variant(1, "ABCDEF12")], tmp_path / "form.xlsx")
    factory.assert_not_called()


def test_checksum_writeback_requires_loaded_master_path(tmp_path):
    browser_factory = Mock()
    service = FormBService(browser_factory, master_sheet_factory=Mock())
    with pytest.raises(ValueError, match="Load a Master Sheet"):
        service.generate([variant(1)], tmp_path / "form.xlsx")
    browser_factory.assert_not_called()


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
        assert sheet["B26"].value == "62X-MD1"
        assert sheet["G26"].value == ("62X-MD6" if count >= 6 else None)
        if count > 6:
            assert sheet["B42"].value == "62X-MD7"
            assert sheet["G42"].value == ("62X-MD12" if count >= 12 else None)
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
        assert sheet["A21"].value == "(Production release for project) : 62XS Project Alpha"
        assert sheet["A22"].value == "For Production Beta production"
        assert sheet["B23"].value == "BOSCH-123"
        assert sheet["B24"].value == "ECU-ABC"
        assert sheet[f"A{receipt_row}"].value == "We appreciate the receipt by 8 February 2027"
        assert sheet[f"A{receipt_row}"]._style == template_sheet["A43"]._style
        confirmation = sheet[f"A{receipt_row + 6}"]
        responsibility = sheet[f"A{receipt_row + 7}"]
        assert confirmation.value + responsibility.value == (
            "The release of the file for Production Beta is hereby confirmed under our responsibility."
        )
        assert confirmation._style == template_sheet["A49"]._style
        assert responsibility._style == template_sheet["A50"]._style
        footer_cell = sheet[f"A{receipt_row + 16}"]
        assert footer_cell.value == "Date: 2026-11-03 Alex Example"
        assert footer_cell._style == template_sheet["A59"]._style
        assert sheet.max_row == baseline["FormB"].max_row
        assert sum(
            isinstance(cell.value, str) and cell.value.startswith("Date: ")
            for row in sheet for cell in row
        ) == 1
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
            if key == "expected_receipt_date":
                assert field.placeholderText() == "YYYY-MM-DD"
            elif key == "department_organization":
                assert field.placeholderText() == "MS/EJV1-PS"
            else:
                assert field.placeholderText().startswith("e.g. ")

    values, invalid_fields = widget._collect_form_information()
    assert values == {"date": date.today()}
    assert len(invalid_fields) == 9
    date_field.setText("2027-01-15")
    values, _ = widget._collect_form_information()
    assert values["date"] == date(2027, 1, 15)


def test_advanced_fields_default_hidden_and_keep_values_when_toggled(qapp):
    settings = MemorySettings()
    widget = FormBWidget(Mock(), Mock(), settings)
    advanced = ("return_to", "project_release", "production_project", "ecu_type")
    for key in advanced:
        assert widget._field_containers[key].isHidden()
    assert not widget._field_containers["name"].isHidden()
    widget._form_fields["department_organization"].setText("Engineering")
    widget._form_fields["name"].setText("Alex")
    widget.set_variants([variant(1)])
    widget._checklist._checkboxes["PART-1"].setChecked(True)
    assert widget._form_fields["return_to"].text() == "Engineering Alex"
    assert widget._form_fields["production_project"].text() == "62XS MP1"
    values = {key: field.text() for key, field in widget._form_fields.items()}
    for selected_key in (*advanced, None):
        widget.apply_settings({
            setting: key == selected_key for key, (setting, _) in FORM_B_FIELD_VISIBILITY.items()
        })
        visible_containers = []
        for key, container in widget._field_containers.items():
            visible = key not in advanced or key == selected_key
            assert container.isHidden() is not visible
            if visible:
                visible_containers.append(container)
        for index, container in enumerate(visible_containers):
            position = widget._information_grid.getItemPosition(widget._information_grid.indexOf(container))
            assert position[:2] == (index // 3, index % 3)
        assert {key: field.text() for key, field in widget._form_fields.items()} == values
    _, invalid = widget._collect_form_information()
    assert "Return To" not in invalid
    assert "Production Project" not in invalid


@pytest.mark.parametrize("field_key", FORM_B_FIELD_VISIBILITY)
def test_settings_advanced_form_b_fields_apply_live_persist_and_discard(qapp, tmp_path, field_key):
    from autohub.modules.settings.ui import SettingsWidget
    from autohub.ui.main_window import MainWindow

    settings, dialogs = JsonSettingsStore(tmp_path / "settings.json"), Mock()
    setting_key = FORM_B_FIELD_VISIBILITY[field_key][0]
    widget = FormBWidget(Mock(), Mock(), settings)
    page = SettingsWidget(settings, dialogs)
    MainWindow._wire_cross_module_signals([page, widget])
    assert all(not checkbox.isChecked() for checkbox in page._form_b_visibility.values())
    assert not page._apply.isEnabled()
    page._form_b_visibility[setting_key].setChecked(True)
    assert widget._field_containers[field_key].isHidden()
    page._apply.click()
    assert settings.load()[setting_key] is True
    assert not widget._field_containers[field_key].isHidden()
    restored_settings = JsonSettingsStore(tmp_path / "settings.json")
    reopened = FormBWidget(Mock(), Mock(), restored_settings)
    restored_page = SettingsWidget(restored_settings, dialogs)
    for key, (setting, _) in FORM_B_FIELD_VISIBILITY.items():
        assert reopened._field_containers[key].isHidden() is (key != field_key)
        assert restored_page._form_b_visibility[setting].isChecked() is (key == field_key)
    page._form_b_visibility[setting_key].setChecked(False)
    dialogs.ask_yes_no_cancel.return_value = False
    assert page.confirm_leave()
    assert page._form_b_visibility[setting_key].isChecked()
    assert not page._apply.isEnabled()
    page._form_b_visibility[setting_key].setChecked(False)
    page._apply.click()
    assert settings.load()[setting_key] is False
    assert widget._field_containers[field_key].isHidden()


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
            "2027-02-08" if key == "expected_receipt_date" else f"value-{key}"
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
    widget._form_fields["expected_receipt_date"].setText("2027-02-31")
    _, invalid_fields = widget._collect_form_information()
    assert len(invalid_fields) == 1
    assert invalid_fields == ["Expected Receipt Date (use YYYY-MM-DD)"]


@pytest.mark.parametrize("release_project", [
    "Honda Project", "6SAY Honda Project", "Honda Project for 6SAY",
])
def test_iso_receipt_date_exports_as_long_date(qapp, tmp_path, release_project):
    widget = FormBWidget(Mock(), Mock())
    for key, field in widget._form_fields.items():
        field.setText("2026-05-19" if key in ("date", "expected_receipt_date") else f"value-{key}")
    information, invalid_fields = widget._collect_form_information()
    assert invalid_fields == []
    item = variant(1, "12345678")
    item["project"] = "6SAY"
    information["project_release"] = release_project
    output = FormBService(Mock()).generate(
        [item], tmp_path / "form.xlsx",
        form_information=information,
    )
    workbook = openpyxl.load_workbook(output)
    try:
        assert workbook["FormB"]["A43"].value == "We appreciate the receipt by 19 May 2026"
        expected = "6SAY Honda Project" if release_project == "Honda Project" else release_project
        assert workbook["FormB"]["A21"].value == f"(Production release for project) : {expected}"
    finally:
        workbook.close()


@pytest.mark.parametrize("suffix,expected", [
    ("Honda Project", "6SAY Honda Project"),
    ("  Customer   Release  ", "6SAY Customer Release"),
    ("", "6SAY"),
    ("   ", "6SAY"),
])
def test_configured_project_suffix_persists_autofills_and_exports(qapp, tmp_path, suffix, expected):
    from autohub.modules.settings.ui import SettingsWidget
    from autohub.ui.main_window import MainWindow

    settings = JsonSettingsStore(tmp_path / "settings.json")
    page = SettingsWidget(settings, Mock())
    assert page._form_b_project_suffix.text() == "Honda Project"
    widget = FormBWidget(Mock(), Mock(), settings)
    item = variant(1, "12345678")
    item["project"] = "6SAY"
    widget.set_variants([item])
    widget._checklist._checkboxes["PART-1"].setChecked(True)
    MainWindow._wire_cross_module_signals([page, widget])
    page._form_b_project_suffix.setText(suffix)
    page._on_apply()
    normalized = " ".join(suffix.split())
    assert settings.load()[FORM_B_PROJECT_SUFFIX_KEY] == normalized
    assert not page._apply.isEnabled()
    assert widget._form_fields["project_release"].text() == expected
    restored_settings = JsonSettingsStore(tmp_path / "settings.json")
    restored_page = SettingsWidget(restored_settings, Mock())
    assert restored_page._form_b_project_suffix.text() == normalized
    restored = FormBWidget(Mock(), Mock(), restored_settings)
    restored.set_variants([item])
    assert restored._form_fields["project_release"].text() == expected
    for key, field in widget._form_fields.items():
        if key in ("date", "expected_receipt_date"):
            field.setText("2026-05-19")
        elif not field.text():
            field.setText(f"value-{key}")
    information, invalid = widget._collect_form_information()
    assert invalid == []
    output = export_form_b([item], {"PART-1": "12345678"}, tmp_path / "form.xlsx",
                           form_information=information)
    workbook = openpyxl.load_workbook(output)
    try:
        assert workbook["FormB"]["A21"].value == f"(Production release for project) : {expected}"
    finally:
        workbook.close()


def test_project_suffix_discard_restores_applied_setting(qapp):
    from autohub.modules.settings.ui import SettingsWidget

    dialogs = Mock()
    dialogs.ask_yes_no_cancel.return_value = False
    settings = MemorySettings()
    page = SettingsWidget(settings, dialogs)
    page._form_b_project_suffix.setText("Unapplied suffix")
    assert page.confirm_leave()
    assert page._form_b_project_suffix.text() == "Honda Project"
    assert not page._apply.isEnabled()
    assert FORM_B_PROJECT_SUFFIX_KEY not in settings.load()


@pytest.mark.parametrize("missing_phase", [False, True])
def test_form_b_export_passes_form_information_to_generator(qapp, monkeypatch, missing_phase):
    service = Mock()
    service.template_problem.return_value = ""
    dialogs = Mock()
    dialogs.save_file.return_value = "selected.xlsx"
    widget = FormBWidget(service, dialogs, MemorySettings({"master_sheet_path": "master.xlsx"}))
    item = variant(1)
    if missing_phase:
        item["event_name"] = "CERT"
    prompt = Mock(return_value=("MP1", True))
    monkeypatch.setattr(form_b_ui.QInputDialog, "getText", prompt)
    widget.set_variants([item])
    widget._checklist._checkboxes[item["part_number"]].setChecked(True)
    for key, field in widget._form_fields.items():
        field.setText(
            "2026-11-03" if key == "date" else
            "2027-02-08" if key == "expected_receipt_date" else f"value-{key}"
        )

    widget._tasks.start = Mock()
    widget._export()
    work = widget._tasks.start.call_args.args[0]
    work()

    service.generate.assert_called_once_with(
        [{**item, "form_b_phase": "MP1"}] if missing_phase else [item],
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
        master_sheet_path="master.xlsx",
    )
    assert prompt.called is missing_phase
    assert "form_b_phase" not in item


def test_form_b_master_information_uses_loaded_and_selected_values_without_overwriting_edits(qapp):
    widget = FormBWidget(Mock(), Mock())
    first, second = variant(1), variant(2)
    widget.set_variants([first, second])
    assert widget._form_fields["project_release"].text() == "62XS Honda Project"
    assert widget._form_fields["production_project"].text() == ""
    widget._checklist._checkboxes[first["part_number"]].setChecked(True)
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
    assert widget._form_fields["project_release"].text() == "OTHER Honda Project"
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
            "2027-02-08" if key == "expected_receipt_date" else f"saved-{key}"
        )
    saved = settings.load()[form_b_ui.FORM_B_INPUTS_KEY]
    assert set(saved) == set(widget._form_fields) - {"date", "expected_receipt_date"}
    reopened = FormBWidget(Mock(), Mock(), JsonSettingsStore(tmp_path / "settings.json"))
    assert reopened._form_fields["date"].text() == date.today().isoformat()
    assert reopened._form_fields["expected_receipt_date"].text() == ""
    for key, value in saved.items():
        assert reopened._form_fields[key].text() == (
            "saved-department_organization saved-name" if key == "return_to" else value
        )
    reopened.set_variants([variant(1)])
    reopened._checklist._checkboxes["PART-1"].setChecked(True)
    assert reopened._form_fields["project_release"].text() == "62XS Honda Project"
    assert reopened._form_fields["production_project"].text() == "62XS MP1"
    assert reopened._form_fields["ecu_type"].text() == "MG1CS022"
    assert reopened._form_fields["name"].text() == "saved-name"
    reopened._form_fields["project_release"].setText("edited project")
    reopened.set_variants([variant(1)])
    assert reopened._form_fields["project_release"].text() == "62XS Honda Project"
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


def test_return_to_tracks_department_and_name_and_remains_editable(qapp):
    settings = MemorySettings()
    widget = FormBWidget(Mock(), Mock(), settings)
    fields = widget._form_fields
    fields["department_organization"].setText("  Engineering  ")
    fields["name"].setText("Alex Nguyen")
    assert fields["return_to"].text() == "Engineering Alex Nguyen"
    assert settings.load()[form_b_ui.FORM_B_INPUTS_KEY]["return_to"] == "Engineering Alex Nguyen"
    fields["return_to"].setText("Release desk")
    assert fields["return_to"].text() == "Release desk"
    fields["name"].setText("Sam Nguyen")
    assert fields["return_to"].text() == "Engineering Sam Nguyen"
    fields["department_organization"].clear()
    assert fields["return_to"].text() == "Sam Nguyen"
    fields["name"].clear()
    assert fields["return_to"].text() == ""


def test_production_project_refreshes_selection_and_warns_on_conflicts(qapp):
    widget = FormBWidget(Mock(), Mock())
    first, second = variant(1), variant(2)
    second["event_name"] = "CERT_MP2"
    widget.set_variants([first, second])
    field = widget._form_fields["production_project"]
    assert field.text() == ""
    widget._checklist._checkboxes["PART-1"].setChecked(True)
    assert field.text() == "62XS MP1"
    field.setText("Manual override")
    widget._update_selection(1, 2)
    assert field.text() == "Manual override"
    widget._checklist._checkboxes["PART-2"].setChecked(True)
    assert field.text() == ""
    assert not widget._production_warning.isHidden()
    assert "Production Project" in widget._collect_form_information()[1]
    field.setText("Manually confirmed production")
    assert "Production Project" not in widget._collect_form_information()[1]
    widget._checklist._checkboxes["PART-1"].setChecked(False)
    assert field.text() == "62XS MP2"
    assert widget._production_warning.isHidden()
    widget._checklist.clear_selection()
    assert field.text() == ""


def test_production_project_autofills_for_matching_selected_variants(qapp):
    widget = FormBWidget(Mock(), Mock())
    widget.set_variants([variant(1), variant(2)])
    for checkbox in widget._checklist._checkboxes.values():
        checkbox.setChecked(True)
    assert widget._form_fields["production_project"].text() == "62XS MP1"
    assert widget._production_warning.isHidden()


@pytest.mark.parametrize(("purpose", "project", "phase"), [
    ("6SAY - MP1", "6SAY", "MP1"),
    ("6WZX - CERT_MP0", "6WZX", "MP0"),
    ("6SAY - CERT-MP12", "6SAY", "MP12"),
    ("6SAY - CERT MP2", "6SAY", "MP2"),
    ("6SAY - CERT/MP3", "6SAY", "MP3"),
    ("6SAY - MP4 production release", "6SAY", "MP4"),
    ("6SAY - cert_mp10_release", "6SAY", "MP10"),
])
def test_project_purpose_mp_parsing_drives_selected_production_project_and_export(
    qapp, tmp_path, monkeypatch, purpose, project, phase
):
    item = webflow_variant_from_row("PART-1", {
        "H": purpose, "S": "MG1CS022", "AP": "MG1CS022",
        "AX": "container", "BA": "12345678",
    })
    assert master_phase(item) == phase
    widget = FormBWidget(Mock(), Mock())
    widget.set_variants([item])
    widget._checklist._checkboxes["PART-1"].setChecked(True)
    assert widget._form_fields["production_project"].text() == f"{project} {phase}"
    prompt = Mock()
    monkeypatch.setattr(form_b_ui.QInputDialog, "getText", prompt)
    assert widget._resolve_phases([item]) == [item]
    prompt.assert_not_called()
    output = export_form_b(
        [item], {"PART-1": "12345678"}, tmp_path / "form.xlsx",
        today=date(2026, 11, 3),
    )
    assert output.name == f"{project}_{phase}_FORMB_MG1CS022_20261103.xlsx"


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


def test_missing_phase_uses_manual_value_only_for_affected_variants(tmp_path):
    first, second = variant(1, "12345678"), variant(2, "12345678")
    first["form_b_phase"] = "MP9"
    second.update(event_name="CERT", form_b_phase=" mp1 ")
    progress = Mock()
    output = FormBService(Mock()).generate(
        [first, second], tmp_path / "form.xlsx", progress
    )
    assert "_MP1_FORMB_" in output.name
    assert form_b_phase(first) == "MP1"
    assert second["event_name"] == "CERT"
    warnings = [call.args[0] for call in progress.call_args_list if call.args[0].startswith("Warning:")]
    assert len(warnings) == 1
    assert "PART-2" in warnings[0] and "MP1" in warnings[0]
    assert "PART-1" not in warnings[0]


@pytest.mark.parametrize("event_name", ["", "CERT", "CERT_MPX", "CERT_MP"])
def test_phase_prompt_accepts_manual_phase_without_changing_master_data(qapp, monkeypatch, event_name):
    widget = FormBWidget(Mock(), Mock())
    valid, affected = variant(1), variant(2)
    affected["event_name"] = event_name
    prompt = Mock(side_effect=[("invalid", True), (" mp1 ", True)])
    monkeypatch.setattr(form_b_ui.QInputDialog, "getText", prompt)
    resolved = widget._resolve_phases([valid, affected])
    assert prompt.call_count == 2
    assert "PART-2" in prompt.call_args_list[0].args[2]
    assert resolved[0] is valid
    assert resolved[1]["form_b_phase"] == "MP1"
    assert "form_b_phase" not in affected


def test_cancel_manual_phase_returns_without_export(qapp, monkeypatch):
    service, dialogs = Mock(), Mock()
    widget = FormBWidget(service, dialogs)
    item = variant(1)
    item["event_name"] = "CERT"
    widget.set_variants([item])
    widget._checklist._checkboxes["PART-1"].setChecked(True)
    monkeypatch.setattr(form_b_ui.QInputDialog, "getText", Mock(return_value=("", False)))
    widget._export()
    service.generate.assert_not_called()
    dialogs.save_file.assert_not_called()
    dialogs.open_progress.assert_not_called()
    dialogs.error.assert_not_called()


def test_missing_phase_without_valid_manual_input_reports_actionable_validation(tmp_path):
    item = variant(1)
    item.update(event_name="CERT", form_b_phase="invalid")
    with pytest.raises(ValueError, match="Enter a manual phase"):
        export_form_b([item], {}, tmp_path / "form.xlsx")


def test_progress_missing_phase_warning_is_not_an_error(qapp):
    window = ProgressDialog("Export Form B")
    try:
        window.step("Warning: PART-2 uses manually entered MP1.")
        qapp.processEvents()
        assert window._status.text().startswith("Warning:")
        assert "Warning:" in window._log.toPlainText()
        assert "Error:" not in window._log.toPlainText()
        window.step("Creating the Form B workbook...")
        qapp.processEvents()
        assert window._status.styleSheet() == ""
        window.succeed("Form B workbook saved.")
    finally:
        qapp.processEvents()
        window.close()


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
