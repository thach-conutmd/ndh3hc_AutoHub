"""Mx17MasterSheet.save_variant_rows against a dict-backed fake of the Excel COM objects."""
import re
from types import SimpleNamespace

from autohub.services.MasterSheet import mx17_layout as layout
from autohub.services.MasterSheet.mx17_sheet import Mx17MasterSheet


class Cell:
    def __init__(self, sheet, address):
        self.sheet, self.address = sheet, address
        self.HasFormula = False
        self.MergeCells = False
        self.NumberFormat = "General"

    @property
    def Value(self):
        return self.sheet.cells.get(self.address)

    @Value.setter
    def Value(self, value):
        self.sheet.cells[self.address] = value


class Sheet:
    def __init__(self, name, cells):
        self.Name, self.cells = name, dict(cells)

    def Range(self, address):
        if ":" not in address:
            return Cell(self, address)
        first, last = address.split(":")
        match = re.fullmatch(r"([A-Z]+)(\d+)", last)
        from openpyxl.utils import column_index_from_string, get_column_letter
        last_col, last_row = column_index_from_string(match.group(1)), int(match.group(2))
        first_row = int(re.sub(r"\D", "", first))
        def clear():
            for address in list(self.cells):
                column, row = re.fullmatch(r"([A-Z]+)(\d+)", address).groups()
                if first_row <= int(row) <= last_row and column_index_from_string(column) <= last_col:
                    del self.cells[address]

        return SimpleNamespace(ClearContents=clear, Value=tuple(
            tuple(self.cells.get(f"{get_column_letter(c)}{r}") for c in range(1, last_col + 1))
            for r in range(first_row, last_row + 1)
        ))

    def Rows(self, number):
        def delete():
            moved = {}
            for address, value in self.cells.items():
                column, row = re.fullmatch(r"([A-Z]+)(\d+)", address).groups()
                row = int(row)
                if row != number:
                    moved[f"{column}{row - 1 if row > number else row}"] = value
            self.cells = moved
        return SimpleNamespace(Delete=delete)

    @property
    def UsedRange(self):
        rows = [int(re.sub(r"\D", "", a)) for a in self.cells] or [1]
        return SimpleNamespace(Row=1, Rows=SimpleNamespace(Count=max(rows)))


def _sheet(main, info=None):
    sheets = [Sheet(layout.MAIN_SHEET_NAME, main)]
    if info is not None:
        sheets.append(Sheet("X_Info", info))
    book = SimpleNamespace(
        ReadOnly=False,
        Worksheets=lambda key: next(s for s in sheets if s.Name == key) if isinstance(key, str) else sheets[key - 1],
        Saved=True,
        FullName="x",
        Save=lambda: None,
    )
    book.Worksheets.Count = len(sheets)
    master = Mx17MasterSheet("x.xlsx")
    master.workbook = book
    return master, sheets


def _main_row(part="37820-5BF-G26", ecu="MED17.9.3"):
    return {"W7": part, "E7": ecu, "F7": "CIVIC"}


def test_editing_one_of_two_keys_sharing_a_column_is_written():
    master, sheets = _sheet(_main_row())
    row = master.load_variant_rows()[0]
    row["S"] = "NEWHW"  # S and AP both live in main column E
    master.save_variant_rows([row], save=False)
    assert sheets[0].cells["E7"] == "NEWHW"


def test_checksum_writeback_uses_matching_latest_main_row_and_saves():
    from unittest.mock import Mock

    master, sheets = _sheet({
        **_main_row(), "Z7": "*****",
        "W8": "OTHER", "Z8": "=SOMETHING",
        "W9": "37820-5BF-G26", "E9": "MED17.9.3", "Z9": "*****",
    })
    master.save = Mock()
    before = dict(sheets[0].cells)
    assert master.write_container_checksums({"37820-5BF-G26": "000abc12"}) == 1
    assert sheets[0].cells == {**before, "Z9": "000ABC12"}
    master.save.assert_called_once()
    loaded = master.load_webflow_variants()
    assert next(item for item in loaded if item["part_number"] == "37820-5BF-G26")["form_b"]["BA"] == "000ABC12"


def test_editing_the_part_number_is_written():
    master, sheets = _sheet(_main_row())
    row = master.load_variant_rows()[0]
    row["J"] = "37820-5BF-G27"
    master.save_variant_rows([row], save=False)
    assert sheets[0].cells["W7"] == "37820-5BF-G27"


def test_unchanged_rows_write_nothing_and_clearing_a_value_clears_the_cell():
    master, sheets = _sheet(_main_row())
    row = master.load_variant_rows()[0]
    before = dict(sheets[0].cells)
    master.save_variant_rows([row], save=False)
    assert sheets[0].cells == before
    row["AT"] = ""
    master.save_variant_rows([row], save=False)
    assert sheets[0].cells["F7"] is None


def test_unmapped_columns_are_reported():
    master, _ = _sheet(_main_row())
    row = master.load_variant_rows()[0]
    row["R"] = "Acura"
    assert master.save_variant_rows([row], save=False)[0]["Unmapped"] == ["R"]


def test_writing_into_merged_cells_goes_through_the_anchor_and_names_failures():
    import pytest

    class Merged:
        MergeCells = True
        HasFormula = False
        NumberFormat = "General"

        def __init__(self, address, anchor):
            self.Address, self._anchor, self.Value = address, anchor, None
            self.MergeArea = SimpleNamespace(Cells=lambda *_: SimpleNamespace(Address=anchor))

    master = Mx17MasterSheet("x.xlsx")
    skipped = Merged("AL7", "AK7")
    Mx17MasterSheet._write_cell(skipped, "v")
    assert skipped.Value is None  # not the anchor

    class Broken:
        Name = "S"

        def Range(self, address):
            raise OSError("We can't do that to a merged cell.")

    with pytest.raises(RuntimeError, match="S!AK7"):
        master._write(Broken(), 7, {"AK": "x"}, "DA")


def test_delete_finds_variants_by_part_number_not_by_row():
    main = {"W7": "A-1", "W8": "B-2", "W9": "C-3"}
    master, sheets = _sheet(main)
    assert master.delete_variants_by_part_number(["a-1", "C-3"], save=False) == 2
    assert sheets[0].cells == {"W7": "B-2"}
    assert master.delete_variants_by_part_number(["missing"], save=False) == 0
    assert [s.Name for s in sheets] == [layout.MAIN_SHEET_NAME]


def test_unchanged_variants_are_not_written():
    master, sheets = _sheet({**_main_row(), "W8": "OTHER", "E8": "MED17.9.3"})
    rows = master.load_variant_rows()
    rows[1]["AT"] = "NEW"
    before = dict(sheets[0].cells)
    master.save_variant_rows(rows, save=False)
    assert {a: v for a, v in sheets[0].cells.items() if a.endswith("7")} == {a: v for a, v in before.items() if a.endswith("7")}
    assert sheets[0].cells["F8"] == "NEW"


def test_writes_never_go_past_the_last_existing_column():
    master, sheets = _sheet(_main_row())
    master._write(sheets[0], 7, {"DA": "in", "DB": "out", "XFD": "out"}, "DA")
    assert sheets[0].cells["DA7"] == "in"
    assert "DB7" not in sheets[0].cells and "XFD7" not in sheets[0].cells


def test_new_info_sheet_never_renames_or_clears_the_main_sheet():
    """Excel's active sheet can still be the main sheet after a copy; the new sheet must be found by name."""
    main = {**_main_row(), "W8": "OTHER"}
    info = {"B4": "[General]\nDelivery Type", "A5": "title", "A6": "37820-X"}
    master, sheets = _sheet(main, info)
    sheets[1].Name = layout.INFO_TEMPLATE_SHEET
    book = master.workbook
    book.ActiveSheet = sheets[0]  # the main sheet stays active

    def copy(before=None, after=None):
        sheets.append(Sheet(f"{layout.INFO_TEMPLATE_SHEET} (2)", sheets[1].cells))
        book.Worksheets.Count = len(sheets)

    sheets[1].Copy = copy
    before = dict(sheets[0].cells)
    created = master._new_info_sheet("5BFT_Info", "title")
    assert sheets[0].Name == layout.MAIN_SHEET_NAME and sheets[0].cells == before
    assert created.Name == "5BFT_Info" and sheets[1].Name == layout.INFO_TEMPLATE_SHEET
