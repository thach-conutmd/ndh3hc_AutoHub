from unittest.mock import Mock
from types import SimpleNamespace

import pytest

from autohub.modules.creation.service import WebFlowConfig, WebFlowJobService
from autohub.services.MasterSheet.row_writer import VariantRowWriter
from autohub.services.MasterSheet.webflow_variants import webflow_variant_from_row
from autohub.services.MasterSheet.mx17_layout import home_from_main
from autohub.modules.creation.variant_checklist import VariantChecklist


@pytest.mark.parametrize("columns,addresses", [
    (None, ["AX11", "AW11"]),
    ({"AX": "X", "AW": "Y"}, ["X11", "Y11"]),
])
def test_number_writer_uses_existing_layout_columns_and_preserves_text(columns, addresses):
    worksheet = Mock()
    cells = {address: Mock(HasFormula=False) for address in addresses}
    worksheet.Range.side_effect = cells.__getitem__
    writer = VariantRowWriter(worksheet, Mock())
    assert writer.write_webflow_numbers({"P1": 11}, {"p1": {"AX": "00123", "AW": "ECR42"}}, columns) == 1
    assert cells[addresses[0]].Value == "00123"
    assert cells[addresses[1]].Value == "ECR42"
    assert all(cell.NumberFormat == "@" for cell in cells.values())


def test_number_writer_fails_for_missing_variant_or_formula():
    sheet = Mock()
    writer = VariantRowWriter(sheet, Mock())
    with pytest.raises(ValueError, match="No Master Sheet row"):
        writer.write_webflow_numbers({}, {"P": {"AX": "123"}})
    sheet.Range.return_value.HasFormula = True
    with pytest.raises(ValueError, match="formula"):
        writer.write_webflow_numbers({"P": 11}, {"P": {"AX": "123"}})


@pytest.mark.parametrize("column", ["BA", "Z"])
def test_checksum_writer_updates_only_matching_cell_and_restores_format(column):
    cell = Mock(HasFormula=False, Value="*****", NumberFormat="General")
    worksheet = Mock()
    worksheet.Range.side_effect = {f"{column}14": cell}.__getitem__
    writer = VariantRowWriter(worksheet, None)
    assert writer.write_container_checksums(
        {"OTHER": 11, "PART-2": 14}, {"part-2": "000abc12"}, column
    ) == 1
    assert cell.Value == "000ABC12"
    assert cell.NumberFormat == "General"
    worksheet.Range.assert_called_once_with(f"{column}14")


def test_checksum_writer_validates_all_targets_before_modifying_cells():
    first = Mock(HasFormula=False, Value="*****", NumberFormat="General")
    second = Mock(HasFormula=True, Formula="=OTHER", Value="old")
    worksheet = Mock()
    worksheet.Range.side_effect = {"BA11": first, "BA14": second}.__getitem__
    writer = VariantRowWriter(worksheet, None)
    with pytest.raises(ValueError, match="formula in BA14"):
        writer.write_container_checksums(
            {"P1": 11, "P2": 14}, {"P1": "12345678", "P2": "ABCDEF12"}
        )
    assert first.Value == "*****"
    assert second.Formula == "=OTHER"
    with pytest.raises(ValueError, match="No Master Sheet row"):
        writer.write_container_checksums({"P1": 11}, {"P10": "12345678"})
    assert first.Value == "*****"


@pytest.mark.parametrize("formula", ["=K59", "=$K$59", "=k59"])
def test_mg1_sw_writeback_preserves_ax_formula_and_writes_source_cell(formula):
    ax = Mock(HasFormula=True, Formula=formula)
    source = Mock(HasFormula=False)
    ecr = Mock(HasFormula=False)
    worksheet = Mock()
    worksheet.Range.side_effect = {"AX59": ax, "K59": source, "AW59": ecr}.__getitem__
    writer = VariantRowWriter(worksheet, None)
    assert writer.write_webflow_numbers({"P": 59}, {"P": {"AX": "00123", "AW": "ECR42"}}) == 1
    assert source.Value == "00123"
    assert source.NumberFormat == "@"
    assert ax.Formula == formula
    assert "Value" not in ax.__dict__
    assert ecr.Value == "ECR42"


def test_mg1_sw_writeback_rejects_formula_in_source_cell():
    worksheet = Mock()
    worksheet.Range.side_effect = {
        "AX59": Mock(HasFormula=True, Formula="=K59"),
        "K59": Mock(HasFormula=True, Formula="=OTHER59"),
    }.__getitem__
    with pytest.raises(ValueError, match="formula"):
        VariantRowWriter(worksheet, None).write_webflow_numbers({"P": 59}, {"P": {"AX": "123"}})


@pytest.mark.parametrize("failure", [False, True])
def test_service_writes_numbers_and_returns_explicit_writeback_failure(failure):
    browser = Mock()
    browser.create_and_fill_jobs.return_value = [
        {"PartNumber": "P", "JobId": "42", "SoftwarePartNumber": "00123", "ECRNumber": "ECR42"}
    ]
    sheet = SimpleNamespace(
        open=Mock(), close=Mock(), write_webflow_links=Mock(),
        write_webflow_numbers=Mock(return_value=1),
    )
    if failure:
        sheet.write_webflow_numbers.side_effect = PermissionError("Workbook locked")
    service = WebFlowJobService(Mock(return_value=browser), Mock(return_value=sheet))
    results = service.create_jobs([{"part_number": "P"}], WebFlowConfig("", "", "", ""), master_sheet_path="sheet.xlsx")
    sheet.write_webflow_numbers.assert_called_once_with({"P": {"AX": "00123", "AW": "ECR42"}})
    assert sheet.close.call_count == 2
    assert results[0]["SoftwarePartNumber"] == "00123"
    assert results[0].get("NumberError") == ("Workbook locked" if failure else None)


@pytest.mark.parametrize("mx17", [False, True])
def test_saved_numbers_reload_into_creation_columns(qapp, mx17):
    cells = {"W11": "P", "J11": "P"}

    class Cell:
        HasFormula = False

        def __init__(self, address):
            self.address = address

        @property
        def Value(self):
            return cells.get(self.address)

        @Value.setter
        def Value(self, value):
            cells[self.address] = value

    worksheet = SimpleNamespace(Range=Cell)
    writer = VariantRowWriter(worksheet, None)
    mapping = {"AX": "X", "AW": "Y"} if mx17 else None
    writer.write_webflow_numbers({"P": 11}, {"P": {"AX": "00123", "AW": "ECR42"}}, mapping)
    row = {address[:-2]: value for address, value in cells.items()}
    home = home_from_main(row) if mx17 else row
    variant = webflow_variant_from_row("P", home)
    checklist = VariantChecklist()
    checklist.set_variants([variant])
    assert checklist._table.item(0, 6).text() == "00123"
    assert checklist._table.item(0, 7).text() == "ECR42"
