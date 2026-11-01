"""Resolve equivalent inputs to exact labels, using the actual captured WebFlow lists."""
import json
from pathlib import Path

import pytest

from autohub.core.webflow_options import normalize_option_value, resolve_option_values
from autohub.services.MasterSheet.webflow_variants import webflow_variant_from_row


@pytest.fixture(scope="module")
def recorded_options():
    root = Path(__file__).resolve().parents[1] / "logs/webflow_trace/20261031_113302"
    fields = {
        "model_year": "Model_year", "emission_norm": "Emission_norm",
        "transmission": "Transmission", "immobilizer": "Immobilizer", "market": "Market",
    }
    result = {}
    for key, name in fields.items():
        capture = next(root.glob(f"*General_{name}*.changes.json"))
        result[key] = {
            event["new"] for event in json.loads(capture.read_text(encoding="utf-8"))["events"]
            if event.get("attr") == "aria-label" and event.get("target", "").startswith("li#")
        }
    return result


@pytest.mark.parametrize("field,value,expected", [
    ("model_year", "27.0MY", {"2027"}),
    ("model_year", "MY27/MY28", {"2027", "2028"}),
    ("model_year", "MY24.5", {"MY24.5"}),
    ("model_year", "2025;2026", {"2025;2026"}),
    ("emission_norm", "Bharat Stage 6", {"BS6"}),
    ("emission_norm", "BS-6.2", {"BS6.2"}),
    ("transmission", "manual", {"MT"}),
    ("transmission", "automatic transmission", {"AT"}),
    ("transmission", "cvt", {"CVT"}),
    ("transmission", "CVT with paddle shift", {"CVT with Paddle shift"}),
    ("transmission", "AT / MT", {"AT / MT"}),
    ("immobilizer", "Active|IMMO 6", {"active", "IMMO6"}),
    ("immobilizer", "Inactive", {"Without"}),
    ("market", "UK", {"GB"}),
    ("market", "Argentina", {"Argentine"}),
    ("market", "India/Sri Lanka/Nepal/Bhutan", None),
    ("market", "India/Nepal/Bhutan", {"India", "Nepal", "Bhutan"}),
    ("market", "Brazil", {"Brazil"}),
])
def test_values_resolve_to_real_recorded_options(recorded_options, field, value, expected):
    if expected is None:
        with pytest.raises(ValueError, match="does not offer"):
            resolve_option_values(field, value, recorded_options[field])
    else:
        assert resolve_option_values(field, value, recorded_options[field]) == expected
        assert expected.issubset(recorded_options[field])


def test_emission_does_not_discard_stage_or_rde_qualifiers(recorded_options):
    for value in ("BS6 + RDE", "BS6.3", "EURO 6"):
        with pytest.raises(ValueError, match="does not offer"):
            resolve_option_values("emission_norm", value, recorded_options["emission_norm"])


def test_exact_option_wins_over_alias():
    assert resolve_option_values("market", "UK", ["UK", "GB"]) == {"UK"}
    assert resolve_option_values("emission_norm", "EURO 6", ["EU6"]) == {"EU6"}


def test_ambiguous_alias_does_not_guess():
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_option_values("emission_norm", "Bharat Stage 6", ["BS6", "BS-6"])


def test_unknown_values_remain_visible_and_fail_selection():
    assert normalize_option_value("market", "Unknown market") == "Unknown market"
    with pytest.raises(ValueError, match="Unknown market"):
        resolve_option_values("market", "Unknown market", ["Brazil"])


def test_unrelated_multiselects_are_not_split_or_aliased():
    with pytest.raises(ValueError, match="does not offer"):
        resolve_option_values("change_reason", "manual/automatic", ["MT", "AT"])


def test_loaded_sheet_values_are_normalized_without_modifying_the_sheet_row():
    row = {"AF": "27.0MY|MY28", "AD": "ACTIVE|IMMO 6", "AI": "manual", "AJ": "UK"}
    original = dict(row)
    hardware = webflow_variant_from_row("PN", row)["hardware"]
    assert hardware["model_year"] == "2027|2028"
    assert hardware["immobilizer"] == "active|IMMO6"
    assert hardware["transmission"] == "MT"
    assert hardware["market"] == "GB"
    assert row == original
