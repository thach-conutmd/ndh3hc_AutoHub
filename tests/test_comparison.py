"""Pure WebFlow export parsing, Master matching and parameter-map comparison."""
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from autohub.core.webflow_fields import HARDWARE_FIELDS
from autohub.modules.comparison.comparison import Status, compare_parameters, compare_xml_datasets, compare_xml_parameters
from autohub.modules.comparison.matching import (
    JOB_PATH, SOFTWARE_PATH, VARIANT_PATH, export_identity, master_parameters,
    match_variant, validate_export_link, validate_link,
)
from autohub.modules.comparison.xml_parser import MAX_XML_BYTES, comparison_parameters, parse_xml
from autohub.services.MasterSheet.webflow_variants import webflow_variant_from_row


def export_xml(parameters, job_id="12"):
    root = ET.Element("Job")
    fields = ET.SubElement(root, "Fields")
    values = {**parameters}
    if job_id is not None:
        values[JOB_PATH] = str(job_id)
    for path, value in values.items():
        group, name = path.split("/", 1)
        kind = "StringList" if isinstance(value, tuple) else "Bool" if isinstance(value, bool) else "String"
        field = ET.SubElement(fields, "Field", Name=name, Group=group, Type=kind)
        if isinstance(value, tuple):
            items = ET.SubElement(field, "Items")
            for item in value:
                ET.SubElement(items, "Item").text = item
        elif value is not None:
            field.text = str(value).lower() if isinstance(value, bool) else str(value)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def variant(part="P1", software="0010", link="https://webflow/app/ShowJob/12"):
    return {
        "part_number": part, "webflow_link": link,
        "hardware": {"software_part_number": software, "customer_order_number": part, "power": "93"},
        "general": {}, "ecu": {}, "customer": {},
    }


def target_parameters(part="P1", software="0010"):
    return {VARIANT_PATH: part, SOFTWARE_PATH: software, "General/Power": "93"}


def test_parser_preserves_missing_false_zero_leading_zeros_and_list_values():
    parameters = parse_xml(export_xml({
        "General/Power": "0", "General/Missing": None, "General/False": False,
        SOFTWARE_PATH: "0010", "General/Market": ("Japan", "Brazil", "Japan"),
    }))
    assert parameters["General/Power"] == "0"
    assert parameters["General/Missing"] is None
    assert parameters["General/False"] == "false"
    assert parameters[SOFTWARE_PATH] == "0010"
    assert parameters["General/Market"] == ("Brazil", "Japan")


@pytest.mark.parametrize("filename", ["WF225949_export (1).xml", "WF225950_export (1).xml"])
def test_parser_accepts_real_webflow_exports_and_all_hardware_mappings(filename):
    source = Path(__file__).resolve().parents[1] / "datas/WebFlowXmlSample" / filename
    parameters = parse_xml(source.read_bytes())
    assert len(parameters) > 100
    assert export_identity(parameters)[0].startswith("37820-")
    assert export_identity(parameters)[1].startswith("10SW")
    mapped = master_parameters({"hardware": {key: "sheet value" for _, key, _, _ in HARDWARE_FIELDS}})
    assert len(mapped) == len(HARDWARE_FIELDS)
    assert mapped.keys() <= parameters.keys()


def test_parser_uses_named_nested_rows_without_flattening_to_ambiguous_labels():
    xml = """<Job><Fields>
      <Field Name="ExternalResult" Group="Files"><Items>
        <Row><Name>TP</Name><Value>3</Value></Row>
        <Row><Name>SW</Name><Value>0010</Value></Row>
      </Items></Field>
      <Field Name="Comment" Group="One">first</Field>
      <Field Name="Comment" Group="Two">second</Field>
    </Fields></Job>"""
    parameters = parse_xml(xml)
    assert parameters["Files/ExternalResult/Items/Row[TP]/Value"] == "3"
    assert parameters["Files/ExternalResult/Items/Row[SW]/Value"] == "0010"
    assert parameters["One/Comment"] != parameters["Two/Comment"]


def test_comparison_exclusions_cover_normalized_hierarchies_only():
    parameters = parse_xml("""<Job><Fields>
      <Field Name="Attachment" Group=" Files "><Items><Row><Value>ignored</Value></Row></Items></Field>
      <Field Name="Review" Group=" Notes "><Nested><Text>ignored</Text></Nested></Field>
      <Field Name="Files" Group="General">retained</Field>
      <Field Name="Value" Group="FilesExtra">retained</Field>
    </Fields></Job>""")
    assert "Files/Attachment/Items/Row/Value" in parameters
    assert comparison_parameters(parameters) == {
        "General/Files": "retained", "FilesExtra/Value": "retained",
    }


def test_all_comparison_engines_exclude_files_and_notes_from_scope():
    base = {"General/Power": "93", "Files/A/Deep/Value": "base", "Notes/BaseOnly": "base"}
    target = {"General/Power": "93", "Files/A/Deep/Value": "target", "Notes/TargetOnly": "target"}
    results = (
        compare_parameters(base, target),
        compare_parameters(base, target, base),
        compare_xml_parameters(base, target),
        compare_xml_datasets(base, [target]),
        compare_xml_datasets(base, [target, base]),
    )
    for rows in results:
        assert [row.parameter for row in rows] == ["General/Power"]
        assert not any(row.deviation for row in rows)


@pytest.mark.parametrize("exclusions,expected", [
    ((), ["Files/Attachment", "General/Power", "Notes/Review"]),
    (("General/",), ["Files/Attachment", "Notes/Review"]),
    (("Files/", "Notes/"), ["General/Power"]),
])
def test_configured_exclusions_replace_defaults_in_every_engine(exclusions, expected):
    values = {"Files/Attachment": "file", "Notes/Review": "note", "General/Power": "93"}
    for rows in (
        compare_parameters(values, values, exclusions=exclusions),
        compare_parameters(values, values, values, exclusions=exclusions),
        compare_xml_parameters(values, values, exclusions=exclusions),
        compare_xml_datasets(values, [values, values], exclusions=exclusions),
    ):
        assert [row.parameter for row in rows] == expected


def test_exclusion_prefixes_normalize_like_xml_parameter_paths():
    from autohub.modules.comparison.xml_parser import comparison_exclusions

    prefixes = comparison_exclusions({"xml_comparison_exclusions": [" Custom / caf\u00e9 /", "Custom/caf%C3%A9/"]})
    assert prefixes == ("Custom/caf%C3%A9/",)
    assert comparison_parameters({"Custom/caf%C3%A9/Nested": "x", "Custom/Other": "y"}, prefixes) == {"Custom/Other": "y"}
    assert comparison_exclusions({}) == ("Files/", "Notes/")
    assert comparison_exclusions({"xml_comparison_exclusions": []}) == ()


def test_parser_accepts_namespaces_and_utf16():
    data = '<Job xmlns="urn:webflow"><Fields><Field Name="Power" Group="General">93</Field></Fields></Job>'
    assert parse_xml(data.encode("utf-16")) == {"General/Power": "93"}


def test_disabled_exclusions_are_saved_but_not_applied():
    from autohub.modules.comparison.xml_parser import comparison_exclusions

    settings = {
        "xml_comparison_exclusions": [" Files / ", "Notes/"],
        "xml_comparison_disabled_exclusions": ["Files/"],
    }
    assert comparison_exclusions(settings) == ("Notes/",)
    assert comparison_exclusions(settings, manual=True) == ("Notes/",)
    assert comparison_exclusions(settings, enabled_only=False) == ("Files/", "Notes/")
    settings["xml_comparison_exclusions_master_only"] = True
    assert comparison_exclusions(settings) == ("Notes/",)
    assert comparison_exclusions(settings, manual=True) == ()


@pytest.mark.parametrize("data", [
    b"", b"<html>not an export</html>", b"<Job><Fields/></Job>", b"<Job><Fields>",
    b'<Job><Fields><Field Group="General">no name</Field></Fields></Job>',
    b'<Job><Fields><Field Name="A"/><Field Name="A"/></Fields></Job>',
    b'<Job><Fields><Field Name="A" Type="Bool">maybe</Field></Fields></Job>',
    b'<Job><Fields><Field Name="A" Type="StringList"><Items><Bad/></Items></Field></Fields></Job>',
    b'<?xml version="1.0" encoding="unknown-encoding"?><Job><Fields><Field Name="A"/></Fields></Job>',
    b'<!DOCTYPE Job [<!ENTITY x "value">]><Job><Fields><Field Name="A">&x;</Field></Fields></Job>',
])
def test_parser_rejects_invalid_or_ambiguous_exports(data):
    with pytest.raises(ValueError):
        parse_xml(data)


def test_parser_limits_input_size_and_nesting():
    with pytest.raises(ValueError, match="10 MiB"):
        parse_xml(b" " * (MAX_XML_BYTES + 1))
    with pytest.raises(ValueError, match="nesting"):
        parse_xml('<Job><Fields><Field Name="A">' + "<Nested>" * 34 + "x" + "</Nested>" * 34 + "</Field></Fields></Job>")


def test_master_mapping_reuses_existing_sheet_payload():
    payload = webflow_variant_from_row("P1", {
        "AX": "0010", "AQ": "P1", "BG": "TP3", "X": "No", "Y": "Yes",
        "AF": "MY27|MY28", "CL": "0001", "CQ": "01",
    })
    parameters = master_parameters(payload)
    assert parameters[SOFTWARE_PATH] == "0010"
    assert parameters["Check/Safety_Monitoring_SW_by_RB"] == "false"
    assert parameters["Check/SafetyCalibrationResponsibility"] == "true"
    assert parameters["General/ModelYear"] == ("2027", "2028")
    assert parameters["Customer/ECU_progam_ID"] == "0001"
    assert parameters["Customer/SW_Version"] == "01"
    assert parameters["ECU/TP_Level"] == "TP3"


def test_unmapped_master_values_are_reported_as_missing_in_webflow():
    parameters = master_parameters({"unmapped_fields": {"CS (DWG NO.)": "P1"}})
    row = compare_parameters(parameters, {})[0]
    assert row.parameter == "Master/CS (DWG NO.)"
    assert row.status == Status.MISSING_IN_WEBFLOW


def test_match_uses_both_variant_and_software_without_losing_leading_zeros():
    expected = variant(software="0010")
    assert match_variant([variant(software="0011"), expected], target_parameters()) is expected
    assert match_variant([variant(" p 1 ", " 0010 ")], target_parameters())
    with pytest.raises(ValueError, match="No Master"):
        match_variant([variant(software="10")], target_parameters())


@pytest.mark.parametrize("parameters", [{}, {VARIANT_PATH: "P1"}, {VARIANT_PATH: "P1", SOFTWARE_PATH: None},
                                        {VARIANT_PATH: "P1", SOFTWARE_PATH: ("0010",)}])
def test_match_rejects_missing_or_nonscalar_identity(parameters):
    with pytest.raises(ValueError, match="nonblank"):
        match_variant([variant()], parameters)


def test_match_rejects_ambiguous_master_rows():
    with pytest.raises(ValueError, match="Multiple"):
        match_variant([variant(), variant()], target_parameters())


@pytest.mark.parametrize("link", [
    "", "not a link", "file:///app/ShowJob/12", "https://host/app/ShowJob/0",
    "https://host/app/ShowJob/no", "https://host/12", "https:///app/ShowJob/12",
    "https://name:password@host/app/ShowJob/12", "https://host:bad/app/ShowJob/12",
    "https://bad host/app/ShowJob/12",
])
def test_invalid_links_fail_explicitly(link):
    with pytest.raises(ValueError, match="valid WebFlow"):
        validate_link(link)


def test_valid_link_and_export_job_must_correspond():
    link = "https://webflow/app/ShowJob/12"
    assert validate_link(link) == link
    validate_export_link({JOB_PATH: "12"}, link)
    with pytest.raises(ValueError, match="JobId"):
        validate_export_link({JOB_PATH: "13"}, link)


def test_comparison_preserves_two_way_statuses_within_master_scope():
    rows = {row.parameter: row for row in compare_parameters(
        {"match": "1", "mismatch": "1", "master_only": "x", "blank": "", "zero": "0",
         "false": "false", "missing_master_value": None},
        {"match": "1", "mismatch": "2", "target_only": "y", "blank": None, "zero": "0",
         "false": "false", "missing_master_value": "value"},
    )}
    assert rows["match"].status == Status.MATCH
    assert rows["mismatch"].status == Status.VALUE_MISMATCH
    assert rows["master_only"].status == Status.MISSING_IN_WEBFLOW
    assert "target_only" not in rows
    assert rows["missing_master_value"].status == Status.MISSING_IN_MASTER
    assert rows["blank"].status == Status.MISSING_IN_WEBFLOW
    assert rows["zero"].status == rows["false"].status == Status.MATCH
    assert not rows["match"].deviation
    assert all(rows[name].deviation for name in ("mismatch", "master_only", "missing_master_value", "blank"))


def test_option_aliases_and_tp_level_use_webflow_semantics_without_hiding_other_mismatches():
    rows = {row.parameter: row for row in compare_parameters(
        {"General/Market": ("UK", "Brazil"), "General/EmissionNorm": ("PROCONVE-L8",),
         "ECU/TP_Level": "TP3", "Customer/SW_Version": "01"},
        {"General/Market": ("GB", "Brazil"), "General/EmissionNorm": ("PROCONVE L8",),
         "ECU/TP_Level": "3", "Customer/SW_Version": "1"},
    )}
    assert all(rows[path].status == Status.MATCH for path in ("General/Market", "General/EmissionNorm", "ECU/TP_Level"))
    assert rows["Customer/SW_Version"].status == Status.VALUE_MISMATCH


def test_three_way_statuses_and_missing_values_are_never_false_matches():
    rows = {row.parameter: row for row in compare_parameters(
        {"both": "1", "master": "1", "base": "2", "neither": "2", "missing": None},
        {"both": "1", "master": "1", "base": "1", "neither": "1", "missing": None},
        {"both": "1", "master": "2", "base": "1", "neither": "3", "missing": None, "base_only": "4"},
    )}
    assert rows["both"].status == Status.MATCHES_BOTH
    assert rows["master"].status == Status.MATCHES_MASTER
    assert rows["base"].status == Status.MATCHES_BASE
    assert rows["neither"].status == rows["missing"].status == Status.MATCHES_NEITHER
    assert "base_only" not in rows
    assert not rows["both"].deviation and not rows["master"].deviation
    assert rows["base"].deviation


def test_empty_base_map_still_enables_three_way_comparison():
    assert compare_parameters({"p": "x"}, {"p": "x"}, {})[0].status == Status.MATCHES_MASTER


def test_xml_only_paths_are_ignored_even_with_an_empty_master():
    assert compare_parameters({}, {"target_only": "x"}, {"base_only": "y"}) == []
    rows = compare_parameters({"scope": "x"}, {"scope": "x", "extra": "y"}, {"extra": "z"})
    assert [row.parameter for row in rows] == ["scope"]


def test_manual_xml_comparison_uses_union_and_shared_value_semantics():
    base = parse_xml(export_xml({
        "General/Power": " 0 ", "General/Enabled": False, "General/BaseOnly": "base",
        "General/Blank": None, "General/BlankBase": None, "General/Market": ("UK", "Brazil"),
        "ECU/TP_Level": "TP3", "Customer/SW_Version": "0010",
    }, job_id=None))
    target = parse_xml(export_xml({
        "General/Power": "0", "General/Enabled": False, "General/TargetOnly": "target",
        "General/Blank": None, "General/BlankBase": "value", "General/Market": ("Brazil", "GB"),
        "ECU/TP_Level": "3", "Customer/SW_Version": "10",
    }, job_id=None))
    rows = {row.parameter: row for row in compare_xml_parameters(base, target)}
    assert list(rows) == sorted(base.keys() | target.keys())
    for path in ("General/Power", "General/Enabled", "General/Market", "ECU/TP_Level"):
        assert rows[path].status == Status.MATCH and not rows[path].deviation
    assert rows["General/BaseOnly"].status == Status.MISSING_IN_TARGET
    assert rows["General/TargetOnly"].status == Status.MISSING_IN_BASE
    assert rows["General/Blank"].status == Status.MISSING_IN_TARGET
    assert rows["General/BlankBase"].status == Status.MISSING_IN_BASE
    assert rows["Customer/SW_Version"].status == Status.VALUE_MISMATCH
    assert rows["Customer/SW_Version"].base == "0010"
    assert rows["Customer/SW_Version"].target == "10"
    assert rows["Customer/SW_Version"].master is None


def test_manual_xml_missing_paths_take_precedence_over_blank_values():
    assert compare_xml_parameters({}, {"blank": None})[0].status == Status.MISSING_IN_BASE
    assert compare_xml_parameters({"blank": None}, {})[0].status == Status.MISSING_IN_TARGET
