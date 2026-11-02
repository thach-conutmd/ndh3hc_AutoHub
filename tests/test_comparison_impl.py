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
    assert update.values == {"W": "b", "AJ": "EU|US", "Z": "true"}
    assert update.kinds["Z"] == "checkbox" and update.kinds["AJ"] == "option:market" and update.kinds["W"] == ""
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


import pytest

from autohub.core.impl_values import CHECKBOX, TP_LEVEL, normalize_impl_value, option_kind
from autohub.modules.comparison.comparison import compare_parameters
from autohub.modules.comparison.matching import master_parameters


@pytest.mark.parametrize("raw, current, expected", [
    ("true", "Yes", "Yes"), ("false", "No", "No"), ("TRUE", "No", "Yes"), ("false", "yes", "no"),
    ("true", "YES", "YES"), ("true", "TRUE", "TRUE"), ("false", True, False), ("true", None, True),
])
def test_checkbox_follows_master_style(raw, current, expected):
    assert normalize_impl_value(CHECKBOX, raw, [current]) == expected


@pytest.mark.parametrize("raw, current, expected", [
    ("3", "TP3", "TP3"), ("TP3", "TP3", "TP3"), ("3", None, "TP3"), ("TP3", None, "TP3"),
    ("4", "TP3", "TP4"), ("tp5", "", "TP5"), ("3", "3", "3"), ("n/a", "TP3", "n/a"),
])
def test_tp_level_is_prefixed_once(raw, current, expected):
    assert normalize_impl_value(TP_LEVEL, raw, [current]) == expected


def test_unordered_values_keep_master_order_only_when_tokens_match():
    kind = option_kind("immobilizer")
    assert normalize_impl_value(kind, "active|IMMO6", [None, "IMMO6|active"]) == "IMMO6|active"
    assert normalize_impl_value(kind, "active|IMMO6", ["IMMO6|active", None]) == "IMMO6|active"
    assert normalize_impl_value(kind, "active|IMMO7", ["IMMO6|active"]) == "active|IMMO7"
    assert normalize_impl_value(kind, "active|IMMO6", []) == "active|IMMO6"


def test_other_parameters_and_pipes_are_written_unchanged():
    assert normalize_impl_value("", "b|a", ["a|b"]) == "b|a"
    assert normalize_impl_value("", "3", ["TP3"]) == "3"


def _status(master_section, key, master, target, path):
    result = compare_parameters(master_parameters({master_section: {key: master}}), {path: target})
    return next(row for row in result if row.parameter == path).status


@pytest.mark.parametrize("master, target, status", [
    ("Yes", "true", Status.MATCH), ("No", "false", Status.MATCH), ("Yes", "false", Status.VALUE_MISMATCH),
])
def test_checkbox_comparison_is_semantic(master, target, status):
    assert _status("general", "calibration", master == "Yes", target, "Check/CalibrationResponsibility") == status


@pytest.mark.parametrize("target, status", [
    ("3", Status.MATCH), ("TP3", Status.MATCH), ("4", Status.VALUE_MISMATCH),
])
def test_tp_level_comparison_is_semantic(target, status):
    assert _status("ecu", "tp_level", "TP3", target, "ECU/TP_Level") == status


@pytest.mark.parametrize("target, status", [
    (("active", "IMMO6"), Status.MATCH), (("IMMO6", "active"), Status.MATCH), (("IMMO6", "idle"), Status.VALUE_MISMATCH),
])
def test_unordered_comparison_is_semantic(target, status):
    assert _status("hardware", "immobilizer", "IMMO6|active", target, "General/Immobilizer") == status


def test_writer_normalizes_to_master_format_before_writing():
    worksheet = Sheet({
        "AX20": Cell("0011"), "#21,4": Cell("IMPL"), "#20,4": Cell("REQ"),
        "X20": Cell("Yes"), "X21": Cell(None), "BG20": Cell("TP2"), "BG21": Cell(None),
        "AD20": Cell("IMMO6|active"), "AD21": Cell(None),
    })
    update = ImplUpdate(
        "0011", {"X": "true", "BG": "3", "AD": "active|IMMO6", "W": "raw|value"},
        {"X": "checkbox", "BG": "tp_level", "AD": "option:immobilizer", "W": ""},
    )
    outcomes = VariantRowWriter(worksheet, None).write_impl_values({"P1": [20]}, {"P1": update})
    assert outcomes["P1"].error == "" and outcomes["P1"].written == 4
    assert worksheet.cells["X21"].Value == "Yes"
    assert worksheet.cells["BG21"].Value == "TP3"
    assert worksheet.cells["AD21"].Value == "IMMO6|active"
    assert worksheet.cells["W21"].Value == "raw|value"
    assert worksheet.cells["X20"].Value == "Yes" and worksheet.cells["AD20"].Value == "IMMO6|active"
