"""Master Sheet value building, normalisers and WebFlow variants: pure functions, no Excel."""
from datetime import datetime

import pytest

from autohub.core import normalizers as n
from autohub.services.MasterSheet.variant_builder import (
    build_request_values,
    compute_new_variant_rows,
    ecu_for_variant,
    index_system_variants,
    security_type_1_value,
    variant_key,
)
from autohub.services.MasterSheet.webflow_variants import webflow_variant_from_row

GENERAL = {"Project": "62XS", "MY": "27.0MY"}
ECU = {"Event": "DAN", "MP": "MP1", "Immobi": "ACTIVE", "SecurityKey": "Mass Production", "PVERName": "SW ver：V034"}
MAIN = {"NumCompID": "37820-62X -MD10-M6", "NumProgID": "37805-62X-MD10", "NumReWrecuid": "02-27", "CALIBID": "cal", "Row": 21}
SYSTEM = {"Hardware": "MG1CS022", "Destination": "M", "Market": "Brazil", "SSID": "41X", "ECUMARK": "7C8"}


@pytest.mark.parametrize(
    "function, value, expected",
    [
        (n.clean_text, None, ""),
        (n.clean_text, "  a ", "a"),
        (n.normalize_part_number, "37820-62X -MD10-M6", "37820-62X-MD10-M6"),
        (n.normalize_displacement, "1.5L", "1.5"),
        (n.normalize_model_year, "27.0MY", "2027"),
        (n.normalize_model_year, "MY28", "2028"),
        (n.normalize_model_year, "28.5MY", "28.5MY"),
        (n.normalize_model_year, 19.0, "2019"),
        (n.normalize_model_year, "2019", "2019"),
        (n.normalize_model_year, "odd", "odd"),
        (n.normalize_emission, "PROCONVE-L8(40)", "PROCONVE L8"),
        (n.normalize_list, "A,\nB", "A|B"),
        (n.normalize_program_version, "SW ver：V034", "V034"),
        (n.title_status, "ACTIVE", "Active"),
        (n.customer_hardware_part_number, "37820-62X-MD10-M6", "37820-62X-MD1"),
        (n.development_number, "0261B00DA8-00", "0261B00DA8"),
        (n.development_number, "0261B00DA8", "0261B00DA8"),
        (n.development_number, "0261B00-001", "0261B00-001"),
        (n.ascii_hex, "37805", "3337383035"),
        (n.parse_event, "62XS for DAN/MP1 event", "62XS - DAN"),
        (n.parse_event, "62XS - HIN Lot / MP1", "62XS - HIN"),
        (n.parse_event, "6WZX for MP0 event", "6WZX - MP0"),
        (n.parse_event, " 62XS  -  HIN  lot / MP1 ", "62XS - HIN"),
        (n.parse_event, None, ""),
        (n.normalize_project_purpose, "62XS for HIN/MP1 event", "62xs - hin lot / mp1"),
        (n.normalize_project_purpose, "62XS - HIN Lot / MP1", "62xs - hin lot / mp1"),
        (n.parse_event, "free text", "free text"),
    ],
)
def test_normalizers(function, value, expected):
    assert function(value) == expected


def test_request_values_for_a_variant():
    values = build_request_values(GENERAL, ECU, MAIN, {"SK1": ""}, SYSTEM, now=datetime(2026, 1, 2))
    assert values["J"] == values["CS"] == "37820-62X-MD10-M6"  # DWG NO. is the part number
    assert values["CX"] == "37820-62X-MD1"  # CUST PART NO. is DWG NO. without the last 4 characters
    assert values["H"] == "62XS - DAN Lot / MP1"
    assert values["AJ"] == "Brazil"  # Market comes from the DESTINATION row
    assert values["S"] == values["BD"] == "MG1CS022"
    assert values["CY"] == "7C8" and values["CZ"] == "41X"
    assert values["CL"] == n.ascii_hex("37805-62X-MD10")
    assert values["C"] == datetime(2026, 1, 2)
    assert "CN" not in values


def test_project_purpose_uses_project_event_and_milestone():
    values = build_request_values(GENERAL, {**ECU, "Event": "HIN"}, MAIN, {}, SYSTEM)
    assert values["H"] == "62XS - HIN Lot / MP1"
    assert webflow_variant_from_row(values["J"], values)["event"] == "62XS - HIN"


def test_security_type_1_joins_sk1_sk2_sk3():
    boot = {"SK1": "3670", "SK2": " 1A2B ", "SK3": None}
    assert security_type_1_value(boot) == "36701A2B"
    assert build_request_values(GENERAL, ECU, MAIN, {**boot, "SK3": "FF"}, SYSTEM)["CN"] == "36701A2BFF"
    assert security_type_1_value({}) == ""


def test_hw_info_fills_hw_columns_but_not_over_the_system_matrix():
    hw = {"hw_ident": "0261S10A2Y", "b_number": "0261B00CE7-00", "eu_mark": "ZZZ", "ss_id": "YYY"}
    values = build_request_values(GENERAL, ECU, MAIN, {}, SYSTEM, hw)
    assert (values["AN"], values["AO"]) == ("0261S10A2Y", "0261B00CE7")  # "-00" is dropped
    assert (values["CY"], values["CZ"]) == ("7C8", "41X")

    blank = {**SYSTEM, "SSID": None, "ECUMARK": None}
    filled = build_request_values(GENERAL, ECU, MAIN, {}, blank, hw)
    assert (filled["CY"], filled["CZ"]) == ("ZZZ", "YYY")


def test_index_system_variants_keeps_the_live_column_for_an_abolished_duplicate():
    info = {
        "GeneralInfo": [
            {"Column": "F", "PartNumber": "37820-A", "Abolished": False},
            {"Column": "G", "PartNumber": "37820 -A", "Abolished": True},
        ],
        "FormB": [{"Column": "F", "Hardware": "live"}, {"Column": "G", "Hardware": "old"}],
        "Setting": [],
    }
    assert index_system_variants(info)["37820-A"]["Hardware"] == "live"


def test_ecu_for_variant_picks_the_group_holding_the_row():
    groups = [{"Event": "A", "Rows": [21, 22]}, {"Event": "B", "Rows": [23]}]
    assert ecu_for_variant({"Ecu": groups}, {"Row": 23})["Event"] == "B"
    assert ecu_for_variant({"Ecu": groups}, {"Row": 99})["Event"] == "A"
    assert ecu_for_variant({"Ecu": []}, {"Row": 1}) == {}


def _ecu_info(count=1):
    main = [{**MAIN, "Row": 21 + i, "NumCompID": f"37820-62X-M{i}10-M6"} for i in range(count)]
    return {
        "GeneralInfo": [GENERAL],
        "Ecu": [{**ECU, "Rows": [m["Row"] for m in main]}],
        "Main": main,
        "Container": [{}] * count,
        "Boot": [{}] * count,
    }


def _matrix(count=1):
    return {
        "GeneralInfo": [{"Column": chr(70 + i), "PartNumber": f"37820-62X-M{i}10-M6"} for i in range(count)],
        "FormB": [{"Column": chr(70 + i), **SYSTEM} for i in range(count)],
        "Setting": [],
    }


def test_compute_new_rows_skips_existing_keys_and_drops_created_date():
    info, matrix = _ecu_info(2), _matrix(2)
    first = build_request_values(GENERAL, ECU, info["Main"][0], {}, SYSTEM)
    existing = {variant_key(first["H"], first["J"], first["BI"])}

    rows = compute_new_variant_rows(info, matrix, existing)

    assert [r["J"] for r in rows] == ["37820-62X-M110-M6"]
    assert "C" not in rows[0]


def test_new_purpose_format_does_not_duplicate_a_legacy_variant():
    info = _ecu_info()
    existing = {variant_key("62XS for DAN/MP1 event", info["Main"][0]["NumCompID"], MAIN["NumProgID"])}

    assert compute_new_variant_rows(info, _matrix(), existing) == []


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda info: info.update(Main=[]), "Main variant data"),
        (lambda info: info.update(Container=[]), "Container variant counts"),
        (lambda info: info.update(Boot=[]), "enough Boot"),
    ],
)
def test_compute_new_rows_validates_the_ecu_info(mutate, message):
    info = _ecu_info()
    mutate(info)
    with pytest.raises(ValueError, match=message):
        compute_new_variant_rows(info, _matrix(), set())


def test_compute_new_rows_names_a_part_number_missing_from_the_matrix():
    with pytest.raises(ValueError, match="System Matrix variant not found"):
        compute_new_variant_rows(_ecu_info(), {"GeneralInfo": [], "FormB": [], "Setting": []}, set())


def test_webflow_variant_uses_sheet_values_instead_of_defaults():
    row = {"H": "62XS for DAN/MP1 event", "Q": "MED17", "R": "Honda", "S": "MED17.9", "BD": "Custom family",
           "BC": "Custom spec", "BG": "TP9", "CR": "Custom component", "T": "Custom delivery", "U": "Pilot",
           "V": "Program", "W": "YES", "X": "No", "Y": "Yes", "Z": False, "AA": True,
           "BE": "62XS", "BF": "V030", "BH": "FFFF", "CL": "33", "CM": "00", "CN": "FF", "CQ": "01"}
    variant = webflow_variant_from_row("37820-62X-MD10-M6", row)
    assert variant["event"] == "62XS - DAN" and variant["ecu_type"] == "MED17.9"
    assert variant["ecu_generation"] == "MED17" and variant["brand"] == "Honda"
    assert variant["general"] == {
        "delivery_type": "Custom delivery", "release_class": "Pilot", "release_scope": "Program", "limitations": "YES",
        "safety_monitoring": False, "safety_calibration": True, "calibration": False, "data_integration": True,
    }
    assert variant["ecu"]["family_name"] == "Custom family"
    assert variant["ecu"]["indi_spec"] == "Custom spec"
    assert variant["ecu"]["tp_level"] == "TP9"
    assert variant["customer"]["component_id"] == "Custom component"
    assert webflow_variant_from_row("P", {})["ecu"]["indi_spec"] == ""


@pytest.mark.parametrize("release_class", ["Pre-Production", "Production", "Pilot", "  Pre-Production  "])
def test_webflow_release_class_comes_from_the_row(release_class):
    variant = webflow_variant_from_row("P", {"U": release_class})
    assert variant["general"]["release_class"] == release_class.strip()


@pytest.mark.parametrize("release_class", [None, "", "   "])
def test_webflow_release_class_leaves_blank_cells_blank(release_class):
    variant = webflow_variant_from_row("P", {"U": release_class})
    assert variant["general"]["release_class"] == ""


def test_reader_preserves_release_class_for_both_reported_variants():
    from autohub.services.MasterSheet.row_reader import VariantRowReader

    class Reader(VariantRowReader):
        def request_rows_with_part_number(self):
            return iter(((4, "37820-6WZ-M610-M6"), (5, "37820-6WZ-M710-M6")))

        def _value(self, column, row):
            return "Pre-Production" if column == "U" else None

        def _webflow_link(self, row):
            return ""

    variants = Reader(None).load_webflow_variants()
    assert [variant["part_number"] for variant in variants] == [
        "37820-6WZ-M610-M6", "37820-6WZ-M710-M6",
    ]
    assert [variant["general"]["release_class"] for variant in variants] == [
        "Pre-Production", "Pre-Production",
    ]


def test_security_type_1_drops_the_excel_float_suffix():
    assert security_type_1_value({"SK1": "2025.0", "SK2": "020B9", "SK3": "010.0"}) == "2025020B9010"
    assert security_type_1_value({"SK1": 20250901.0, "SK2": "1A2B"}) == "202509011A2B"
    assert n.hex_text("ABC.0") == "ABC" and n.hex_text("x.0") == "x.0"


@pytest.mark.parametrize(
    "value, expected",
    [("4E5", True), ("1.5e-3", True), ("-2E10", True), ("0261B", True), ("E5", False), ("4E", False), ("4EA5", False), ("400000", False), (400000, False), (None, False)],
)
def test_needs_text_format(value, expected):
    assert n.needs_text_format(value) is expected


class _Cell:
    HasFormula = False
    Column = 1
    NumberFormat = "General"
    Value = None


class _Sheet:
    def __init__(self):
        self.cells = {}

    def Range(self, address):
        return self.cells.setdefault(address, _Cell()) if address != "CZ1" else type("C", (), {"Column": 104})()


def test_writer_formats_scientific_looking_text_as_text():
    from autohub.services.MasterSheet.row_writer import VariantRowWriter

    sheet = _Sheet()
    VariantRowWriter(sheet, None).write_values(5, {"A": "4E5", "B": "400000"})
    assert (sheet.cells["A5"].NumberFormat, sheet.cells["A5"].Value) == ("@", "4E5")
    assert sheet.cells["B5"].NumberFormat == "General"


def test_sw_version_is_01_for_mg1cs022_only_and_indi_spec_is_filled():
    for hardware, expected in (("MG1CS022", "01"), ("mg1cs022", "01"), ("MG1CS020", "-"), ("", "-")):
        values = build_request_values(GENERAL, ECU, MAIN, {}, {**SYSTEM, "Hardware": hardware})
        assert values["CQ"] == expected
    values = build_request_values(GENERAL, ECU, MAIN, {}, SYSTEM)
    assert values["BC"] == "Honda_MG1CS022_CS_IndiSpec_01"
    assert webflow_variant_from_row("P", {"BC": "Custom", "BD": "MG1CS022"})["ecu"]["indi_spec"] == "Custom"
