"""Kick Off Meeting reader: pure parser rules, password handling and how the facts reach the table rows."""
import io
from pathlib import Path

import msoffcrypto
import pytest
from pptx import Presentation
from pptx.util import Inches

from autohub.services.KickOff.KickOff import KickOffMeeting
from autohub.services.KickOff.parser import RULES, Rule, parse_kick_off
from autohub.services.MasterSheet.variant_builder import build_request_values
from tests.fakes import FakeDialogs, FakeDocument, FakeMasterSheet, build_service
from tests.test_home_workflow import _presenter
from tests.test_variant_builder import ECU, GENERAL, MAIN, SYSTEM

ROWS = [
    ["Engine type", "1.5L L4 GDI", "←"],
    ["Maximum Power（kW/rpm）", "93 kW／6200 rpm　(E100)", "←"],
    ["1", "ECU", "Bosch", "MG1 CS022"],
    ["Displacement    ", "1199 cc"],
    ["EM Category", "BS6 +RDE"],
    ["Security", "Immobilizer (Generation 6th)", "", "X"],
    ["NP1-kai engine, same as 6SAA/6G0X/5DZX/5V6P"],
    ["Power", "99 kW"],  # later duplicates never override the first match
]


def test_parser_reads_power_cylinders_and_ecu_name():
    assert parse_kick_off(ROWS) == {
        "cylinders": "4",
        "power_kw": "93",
        "displacement_l": "1.2",
        "emission": "BS6 + RDE",
        "immobilizer": "IMMO6",
        "engine_family": "NP1",
    }


def test_parser_handles_other_wordings_and_ignores_the_rest():
    assert parse_kick_off([["Power", "66 kW/6000rpm"], ["Engine type", "1.2L L3"], ["Cylinder Head", "A"]]) == {
        "power_kw": "66",
        "cylinders": "3",
    }
    assert parse_kick_off([]) == {}


def test_a_new_fact_is_a_data_change():
    import re

    extra = Rule("fuel", re.compile(r"^fuel$", re.I), re.compile(r"(E\d+)"))
    assert parse_kick_off([["Fuel", "E100"]], (*RULES, extra))["fuel"] == "E100"


def _deck(path: Path, rows=ROWS) -> Path:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    table = slide.shapes.add_table(len(rows), 4, Inches(0), Inches(0), Inches(8), Inches(3)).table
    for r, cells in enumerate(rows):
        for c, text in enumerate(cells):
            table.cell(r, c).text = text
    presentation.save(str(path))
    return path


def _encrypt(source: Path, target: Path, password: str) -> Path:
    with open(source, "rb") as src, open(target, "wb") as out:
        msoffcrypto.OfficeFile(src).encrypt(password, out)
    return target


def test_reads_an_unencrypted_deck(tmp_path):
    reader = KickOffMeeting(str(_deck(tmp_path / "plain.pptx")))
    assert reader.load_data() is True and reader.info["power_kw"] == "93"


@pytest.mark.parametrize("password", ["honda", "hb"])
def test_reads_a_deck_protected_with_either_known_password(tmp_path, password):
    deck = _encrypt(_deck(tmp_path / "plain.pptx"), tmp_path / "locked.pptx", password)
    reader = KickOffMeeting(str(deck))
    assert reader.load_data() is True and reader.info["cylinders"] == "4"


def test_unknown_password_gives_a_clear_error(tmp_path):
    deck = _encrypt(_deck(tmp_path / "plain.pptx"), tmp_path / "locked.pptx", "other")
    reader = KickOffMeeting(str(deck))
    assert reader.load_data() is False and "password" in reader.last_error


def test_deck_without_matching_tables_is_reported(tmp_path):
    reader = KickOffMeeting(str(_deck(tmp_path / "empty.pptx", [["Item", "Value"]])))
    assert reader.load_data() is False and "No engine or ECU information" in reader.last_error


def test_builder_fills_the_blank_columns_from_kick_off_info():
    info = {"power_kw": "93", "cylinders": "4"}
    values = build_request_values(GENERAL, ECU, MAIN, {}, SYSTEM, kick_off=info)
    assert (values["AC"], values["AK"]) == ("93", "4")
    assert "AC" not in build_request_values(GENERAL, ECU, MAIN, {}, SYSTEM)


def test_kick_off_corrects_emission_and_immobilizer():
    info = {"emission": "BS6 + RDE", "immobilizer": "IMMO6", "engine_family": "NP1"}
    values = build_request_values(GENERAL, ECU, MAIN, {}, {**SYSTEM, "Emission": "BS6"}, kick_off=info)
    assert (values["AH"], values["AD"], values["AG"]) == ("BS6 + RDE", "active|IMMO6", "NP1")


def test_displacement_from_the_system_matrix_is_not_touched():
    info = {"displacement_l": "1.2"}
    assert build_request_values(GENERAL, ECU, MAIN, {}, {**SYSTEM, "Displacement": "1.5L"}, kick_off=info)["AE"] == "1.5"
    assert build_request_values(GENERAL, ECU, MAIN, {}, {**SYSTEM, "Displacement": None}, kick_off=info)["AE"] == "1.2"


def test_a_different_emission_norm_in_the_system_matrix_is_kept():
    system = {**SYSTEM, "Emission": "EURO 5"}
    values = build_request_values(GENERAL, ECU, MAIN, {}, system, kick_off={"emission": "BS6 + RDE"})
    assert values["AH"] == "EURO 5"


@pytest.mark.parametrize(
    "first, second, same",
    [("BS6", "BS6 + RDE", True), ("BHARAT STAGE6", "BS-6 +RDE", True), ("BS6", "EURO 5", False), ("", "BS6", False)],
)
def test_same_emission_ignores_wording_and_rde(first, second, same):
    from autohub.core.normalizers import same_emission

    assert same_emission(first, second) is same


def test_displacement_litres():
    from autohub.core.normalizers import displacement_litres

    assert (displacement_litres("1199"), displacement_litres("1,498"), displacement_litres(998)) == ("1.2", "1.5", "1.0")


def test_new_variant_passes_kick_off_info_to_the_master_sheet(tmp_path):
    master = FakeMasterSheet(new_rows=[{"J": "P"}])
    kick_off = FakeDocument(info={"power_kw": "93"})
    dialogs = FakeDialogs(files=["e.xlsx", "m.xlsx", "kom.pptx"], kick_off_answer=True)
    presenter, _, _, settings = _presenter(tmp_path, build_service(master=master, kick_off=kick_off), dialogs)

    presenter.new_variant()

    assert master.compute_args[3] == {"power_kw": "93"}
    assert "kick_off_path" not in settings.data


def test_new_variant_reports_an_unreadable_kick_off(tmp_path):
    kick_off = FakeDocument(ok=False, error="none of the known passwords works")
    dialogs = FakeDialogs(files=["e.xlsx", "m.xlsx", "kom.pptx"], kick_off_answer=True)
    presenter, _, dialogs, _ = _presenter(tmp_path, build_service(kick_off=kick_off), dialogs)
    presenter.new_variant()
    assert dialogs.errors == [("New variants", "none of the known passwords works")]


SAMPLES = Path(__file__).resolve().parent.parent / "datas" / "KoM"


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="sample data folder not available")
def test_real_decks_in_datas():
    for name, expected in (("62XS", "93"), ("6WZX", "93"), ("6SAAMMC", "66")):
        deck = next(SAMPLES.glob(f"{name}*.pptx"))
        reader = KickOffMeeting(str(deck))
        assert reader.load_data() is True, reader.last_error
        assert reader.info["power_kw"] == expected
        assert reader.info["immobilizer"] == "IMMO6"
    assert KickOffMeeting(str(next(SAMPLES.glob("6SAAMMC*.pptx")))).load_data()


def test_cylinders_are_read_from_the_equipped_with_sentence():
    rows = [["for below models which will be equipped with 1.2L DOHC 4-cylinder engine: 28MY 6SAA-MMC,"]]
    assert parse_kick_off(rows) == {"cylinders": "4"}


def test_ecu_hw_name_is_the_ecu_type_and_tp_level_follows_the_protections():
    values = build_request_values(GENERAL, ECU, MAIN, {}, SYSTEM)
    assert values["AP"] == values["S"] == "MG1CS022"
    for rom, tuning, expected in (("ACTIVE", "ACTIVE", "TP9"), ("ACTIVE", "INACTIVE", "TP3"), ("INACTIVE", "INACTIVE", "TP3"), (None, "ACTIVE", "TP3")):
        ecu = {**ECU, "ROMCheck": rom, "TuningProtection": tuning}
        assert build_request_values(GENERAL, ecu, MAIN, {}, SYSTEM)["BG"] == expected


def test_engine_family_comes_from_the_ecu_info_sheet_before_the_deck():
    general = {**GENERAL, "EngineFamily": "NP1"}
    values = build_request_values(general, ECU, MAIN, {}, SYSTEM, kick_off={"engine_family": "AP2"})
    assert values["AG"] == "NP1"
    assert build_request_values(GENERAL, ECU, MAIN, {}, SYSTEM, kick_off={"engine_family": "AP2"})["AG"] == "AP2"
