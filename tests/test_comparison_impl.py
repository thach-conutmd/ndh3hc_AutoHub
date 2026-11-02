from autohub.core.impl_update import ImplUpdate
from autohub.modules.comparison.comparison import ComparisonRow, Status
from autohub.modules.comparison.impl_update import build_impl_update, impl_column
from autohub.services.MasterSheet.row_writer import VariantRowWriter


def test_impl_update_uses_only_known_master_parameters_with_target_values():
    rows = [
        ComparisonRow("General/Limitations", "a", "b", Status.VALUE_MISMATCH, base="base"),
        ComparisonRow("General/Market", ("EU",), ("EU", "US"), Status.VALUE_MISMATCH),
        ComparisonRow("General/Car", "x", None, Status.MISSING_IN_WEBFLOW),
        ComparisonRow("Check/CalibrationResponsibility", "false", "true", Status.VALUE_MISMATCH),
        ComparisonRow("Unknown/Path", "x", "y", Status.VALUE_MISMATCH),
    ]
    update = build_impl_update("SW1", rows)
    assert update.software == "SW1"
    assert update.values == {"W": "b", "AJ": "EU|US", "Z": True}
    assert impl_column("Master/Nope") is None


class Cell:
    def __init__(self, value=None, formula=False):
        self.Value, self.HasFormula, self.NumberFormat = value, formula, "General"


class Sheet:
    def __init__(self, cells):
        self.cells = cells

    def Range(self, address):
        return self.cells.setdefault(address, Cell())

    def Cells(self, row, column):
        return self.cells.setdefault(f"#{row},{column}", Cell())


def sheet():
    return Sheet({
        "AX20": Cell("0011"), "#21,4": Cell("IMPL"), "W21": Cell("old"), "X21": Cell(None, formula=True),
        "AX30": Cell("0099"), "#31,4": Cell("IMPL"),
        "AX40": Cell("0012"), "#41,4": Cell("COMP"),
    })


def test_writer_updates_only_the_matching_impl_row_and_skips_formulas():
    worksheet = sheet()
    outcomes = VariantRowWriter(worksheet, None).write_impl_values(
        {"P1": [20], "P2": [30], "P3": [40], "P4": [20, 50]},
        {
            "P1": ImplUpdate("0011", {"W": "new", "X": True}),
            "P2": ImplUpdate("0011", {"W": "bad"}),
            "P3": ImplUpdate("0012", {"W": "bad"}),
            "P4": ImplUpdate("0011", {"W": "bad"}),
            "P5": ImplUpdate("0011", {"W": "bad"}),
        },
    )
    assert (outcomes["P1"].written, outcomes["P1"].skipped, outcomes["P1"].error) == (1, 1, "")
    assert worksheet.cells["W21"].Value == "new" and worksheet.cells["X21"].Value is None
    for part in ("P2", "P3", "P4", "P5"):
        assert outcomes[part].error and not outcomes[part].written
    assert "W31" not in worksheet.cells and "W41" not in worksheet.cells
