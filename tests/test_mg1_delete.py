"""MG1 delete by part number against a small fake worksheet (REQ / IMPL / compare triples from row 11)."""
import re
from types import SimpleNamespace

from autohub.services.MasterSheet.MasterSheet import MasterSheet


class Sheet:
    def __init__(self, variants):
        self.rows = {}
        row = 11
        for part in variants:
            self.rows[row] = {"D": "REQ", "J": part}
            self.rows[row + 1] = {"D": "IMPL"}
            self.rows[row + 2] = {"D": "compare"}
            row += 3

    def Range(self, address):
        column, row = re.fullmatch(r"([A-Z]+)(\d+)", address).groups()
        return SimpleNamespace(Value=self.rows.get(int(row), {}).get(column))

    def Cells(self, row, column):
        return SimpleNamespace(Value=self.rows.get(row, {}).get("D" if column == 4 else None))

    def Rows(self, span):
        first, last = (int(n) for n in span.split(":"))

        def delete():
            kept = [self.rows[r] for r in sorted(self.rows) if not first <= r <= last]
            self.rows = {11 + i: values for i, values in enumerate(kept)}

        return SimpleNamespace(Delete=delete)

    @property
    def UsedRange(self):
        return SimpleNamespace(Row=1, Rows=SimpleNamespace(Count=max(self.rows) if self.rows else 1))


def _master(variants):
    sheet = Sheet(variants)
    master = MasterSheet("x.xlsx")
    master.workbook = SimpleNamespace(Worksheets=lambda _name: sheet)
    return master, sheet


def test_deletes_by_part_number_even_when_row_numbers_moved():
    master, sheet = _master(["A-1", "B-2", "C-3"])
    sheet.Rows("11:13").Delete()  # rows moved up since the table was loaded
    assert master.delete_variants_by_part_number(["c-3"], save=False) == 1
    assert [v["J"] for v in sheet.rows.values() if v["D"] == "REQ"] == ["B-2"]


def test_unknown_part_number_deletes_nothing():
    master, sheet = _master(["A-1", "B-2"])
    assert master.delete_variants_by_part_number(["Z-9", ""], save=False) == 0
    assert len(sheet.rows) == 6


def test_checksum_writeback_resolves_latest_matching_request_row_and_saves():
    from unittest.mock import Mock

    worksheet = Mock()
    worksheet.UsedRange.Row = 1
    worksheet.UsedRange.Rows.Count = 19
    values = {
        "D11": "REQ", "J11": "PART-1", "BA11": "older",
        "D14": "REQ", "J14": "PART-10", "BA14": "=OTHER",
        "D17": "REQ", "J17": "PART-1", "BA17": "*****",
    }
    cells = {
        address: Mock(Value=value, HasFormula=False, NumberFormat="General")
        for address, value in values.items()
    }
    worksheet.Range.side_effect = lambda address: cells.setdefault(address, Mock(Value=None))
    master = MasterSheet("master.xlsx")
    master.workbook = SimpleNamespace(Worksheets=lambda _: worksheet)
    master.save = Mock()
    assert master.write_container_checksums({"PART-1": "000abc12"}) == 1
    assert cells["BA17"].Value == "000ABC12"
    assert cells["BA17"].NumberFormat == "General"
    assert cells["BA11"].Value == "older"
    assert cells["BA14"].Value == "=OTHER"
    master.save.assert_called_once()
