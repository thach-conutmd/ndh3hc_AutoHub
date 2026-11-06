from types import SimpleNamespace
from unittest.mock import Mock

from autohub.core.settings_keys import CALIBRATION_FOLDER_PATH_KEY
from autohub.modules.home.presenter import HomePresenter
from autohub.services.MasterSheet.row_writer import VariantRowWriter
from tests.fakes import MemorySettings

HEX_PATH = r"D:\Project\HEX\ABC.hex"


class FakeCell:
    def __init__(self, column):
        self.Column = column
        self.HasFormula = False
        self.NumberFormat = "General"
        self.Value = None


class FakeSheet:
    def __init__(self):
        self.cells = {}
        self.Hyperlinks = Mock()

    def Range(self, address):
        letters = "".join(ch for ch in address if ch.isalpha())
        column = 0
        for ch in letters:
            column = column * 26 + ord(ch) - ord("A") + 1
        return self.cells.setdefault(address, FakeCell(column))


def test_az_cell_shows_filename_and_links_to_full_hex_path():
    sheet = FakeSheet()
    VariantRowWriter(sheet, None).write_values(12, {"AZ": "ABC.hex"}, {"AZ": HEX_PATH})

    sheet.Hyperlinks.Add.assert_called_once_with(sheet.Range("AZ12"), HEX_PATH, "", "", "ABC.hex")


def test_plain_value_is_written_without_link_when_no_path_is_given():
    sheet = FakeSheet()
    VariantRowWriter(sheet, None).write_values(12, {"AZ": "ABC.hex"})

    sheet.Hyperlinks.Add.assert_not_called()
    assert sheet.Range("AZ12").Value == "ABC.hex"


def test_link_is_skipped_when_path_does_not_end_with_the_written_value():
    sheet = FakeSheet()
    VariantRowWriter(sheet, None).write_values(12, {"AZ": "OTHER.hex"}, {"AZ": HEX_PATH})

    sheet.Hyperlinks.Add.assert_not_called()
    assert sheet.Range("AZ12").Value == "OTHER.hex"


def test_failed_hyperlink_falls_back_to_plain_filename():
    sheet = FakeSheet()
    sheet.Hyperlinks.Add.side_effect = RuntimeError("COM error")
    VariantRowWriter(sheet, None).write_values(12, {"AZ": "ABC.hex"}, {"AZ": HEX_PATH})

    assert sheet.Range("AZ12").Value == "ABC.hex"


def test_save_rows_uses_calibration_path_from_variant():
    sheet = FakeSheet()
    VariantRowWriter(sheet, None).save_rows(
        [{"_row": 12, "AZ": "ABC.hex", "_calibration_hex_path": HEX_PATH}]
    )

    sheet.Hyperlinks.Add.assert_called_once_with(sheet.Range("AZ12"), HEX_PATH, "", "", "ABC.hex")


def test_presenter_attaches_absolute_hex_path_for_hex_values_only(tmp_path):
    settings = MemorySettings({CALIBRATION_FOLDER_PATH_KEY: str(tmp_path)})
    variants = [{"AZ": "ABC.hex"}, {"AZ": "not-a-hex.txt"}, {"AZ": ""}]

    HomePresenter._with_calibration_paths(SimpleNamespace(_settings=settings), variants)

    assert variants[0]["_calibration_hex_path"] == str(tmp_path / "ABC.hex")
    assert "_calibration_hex_path" not in variants[1]
    assert "_calibration_hex_path" not in variants[2]


def test_presenter_adds_no_path_without_calibration_folder():
    variants = [{"AZ": "ABC.hex"}]

    HomePresenter._with_calibration_paths(SimpleNamespace(_settings=MemorySettings()), variants)

    assert "_calibration_hex_path" not in variants[0]
