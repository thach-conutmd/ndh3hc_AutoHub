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

TEMPLATE = Path("datas/FormB/62XS_MP2_FORMB_MG1CS022_20260511.xlsx")


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
