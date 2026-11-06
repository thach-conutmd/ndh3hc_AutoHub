from types import SimpleNamespace

from autohub.modules.creation import hex_paths
from autohub.modules.creation.hex_paths import resolve_calibration_hex
from autohub.services.MasterSheet.row_reader import VariantRowReader


class _Links:
    def __init__(self, address):
        self._address = address
        self.Count = 1 if address else 0

    def __call__(self, index):
        return SimpleNamespace(Address=self._address)


class _Cell:
    def __init__(self, value="", link=""):
        self.Value = value
        self.Hyperlinks = _Links(link)


class _Sheet:
    def __init__(self, cells, last_row):
        self._cells = cells
        self.UsedRange = SimpleNamespace(Row=1, Rows=SimpleNamespace(Count=last_row))

    def Range(self, address):
        return self._cells.get(address, _Cell())


def test_resolver_keeps_variants_with_a_valid_linked_hex_without_prompting(tmp_path):
    hex_file = tmp_path / "ABC.hex"
    hex_file.write_text(":00000001FF\n", encoding="ascii")
    variants = [{"part_number": "P1", "_calibration_hex_path": str(hex_file)}]

    def choose_folder():
        raise AssertionError("must not prompt when the Master Sheet link is valid")

    ready, errors = resolve_calibration_hex(variants, "SYM", choose_folder)

    assert ready == variants
    assert errors == []


def test_resolver_prompts_once_and_matches_missing_variants_by_dwg(monkeypatch, tmp_path):
    calls = []

    def fake_find(folder, symbol, expected):
        calls.append((folder, symbol, expected))
        if expected == "P9":
            raise ValueError("no calibration HEX file matches the DWG number P9.")
        return tmp_path / f"{expected}.hex"

    monkeypatch.setattr(hex_paths, "find_calibration_hex", fake_find)
    prompts = []
    variants = [
        {"part_number": "P1", "_calibration_hex_path": str(tmp_path / "missing.hex")},
        {"part_number": "P2"},
        {"part_number": "P9"},
    ]

    def choose_folder():
        prompts.append(True)
        return str(tmp_path)

    ready, errors = resolve_calibration_hex(variants, "SYM", choose_folder)

    assert prompts == [True]
    assert [v["part_number"] for v in ready] == ["P1", "P2"]
    assert ready[0]["_calibration_hex_path"] == str(tmp_path / "P1.hex")
    assert variants[0]["_calibration_hex_path"] == str(tmp_path / "missing.hex")
    assert errors == ["P9: no calibration HEX file matches the DWG number P9."]
    assert calls == [(str(tmp_path), "SYM", "P1"), (str(tmp_path), "SYM", "P2"), (str(tmp_path), "SYM", "P9")]


def test_resolver_reports_missing_hex_when_folder_selection_is_cancelled():
    ready, errors = resolve_calibration_hex([{"part_number": "P1"}], "SYM", lambda: "")

    assert ready == []
    assert errors == ["P1: no HEX file linked in the Master Sheet and no HEX folder selected."]


def test_reader_takes_the_hex_path_from_the_az_hyperlink_not_the_filename():
    from autohub.services.MasterSheet.row_writer import HEX_LINK_COLUMN

    windows_path = r"D:\Project\HEX\ABC.hex"
    cells = {
        "D11": _Cell("REQ"),
        "J11": _Cell("P1"),
        f"{HEX_LINK_COLUMN}11": _Cell("ABC.hex", link=windows_path),
    }
    reader = VariantRowReader(_Sheet(cells, last_row=11))

    variants = reader.load_webflow_variants()

    assert variants[0]["_calibration_hex_path"] == windows_path


def test_reader_leaves_hex_path_unset_when_the_az_cell_has_no_hyperlink():
    from autohub.services.MasterSheet.row_writer import HEX_LINK_COLUMN

    cells = {"D11": _Cell("REQ"), "J11": _Cell("P1"), f"{HEX_LINK_COLUMN}11": _Cell("ABC.hex")}
    reader = VariantRowReader(_Sheet(cells, last_row=11))

    variants = reader.load_webflow_variants()

    assert "_calibration_hex_path" not in variants[0]
