"""Master Sheet workbook session: opens the workbook and delegates row reading, writing and value building."""
import os

from autohub.core.impl_update import ImplOutcome, ImplUpdate
from autohub.core.normalizers import normalize_part_number
from autohub.core.records import EcuInfoData, HWLookup, KickOffInfo, SystemMatrixData
from autohub.core.webflow_defaults import WebFlowDefaults
from autohub.services.common.workbook import ExcelDocument
from autohub.services.MasterSheet.row_reader import VariantRowReader
from autohub.services.MasterSheet.row_writer import LAST_DATA_COLUMN, VariantRowWriter
from autohub.services.MasterSheet.variant_builder import compute_new_variant_rows


class MasterSheet(ExcelDocument):
    document_name = "Master Sheet"
    raise_on_open_error = True  # nothing may be written into a workbook that failed to open
    LAST_DATA_COLUMN = LAST_DATA_COLUMN
    sheet_name = "Master sheet"

    def _open_workbook(self, path: str):
        self.excel_app.DisplayAlerts = False
        self.workbook = self.excel_app.Workbooks.Open(path, UpdateLinks=0, ReadOnly=False)
        if self.workbook.ReadOnly:
            raise PermissionError(f"Workbook is locked or read-only: {self.file_path}")
        return self.workbook

    def _worksheet(self):
        if not self.workbook:
            raise RuntimeError("Workbook is not opened.")
        return self.workbook.Worksheets(self.sheet_name)

    def save(self, output_path: str = None):
        if not self.workbook:
            raise RuntimeError("Workbook is not opened.")

        if output_path:
            output_path = os.path.abspath(output_path)
            self.workbook.SaveAs(output_path)
            saved_path = output_path
        else:
            self.workbook.Save()
            saved_path = self.workbook.FullName

        if not self.workbook.Saved:
            raise IOError(f"Excel did not save the workbook: {saved_path}")
        return saved_path

    def compute_new_variants(
        self,
        system_info: SystemMatrixData,
        ecu_info: EcuInfoData,
        hw_info: HWLookup | None = None,
        kick_off: KickOffInfo | None = None,
        variant_defaults: WebFlowDefaults | None = None,
    ) -> list[dict]:
        """REQ-row values (keyed by column letter) for variants not yet in the sheet; nothing is written.

        `hw_info` fills the Bosch HW columns and any blank SS-ID / EU-mark; `kick_off` fills power, cylinders
        and ECU HW name.
        """
        existing_keys = VariantRowReader(self._worksheet()).existing_variant_keys()
        return compute_new_variant_rows(
            ecu_info, system_info, existing_keys, hw_info, kick_off=kick_off, variant_defaults=variant_defaults
        )

    def save_variant_rows(self, variants: list[dict], save: bool = True) -> list[dict]:
        """Write each (possibly user-edited) row: a "_row" entry updates that row, otherwise one is inserted."""
        writer = VariantRowWriter(self._worksheet(), self.excel_app)
        saved = writer.save_rows(variants)
        if save:
            self.save()
        return saved

    def delete_variant_rows(self, request_rows: list[int], save: bool = True) -> int:
        deleted = VariantRowWriter(self._worksheet(), self.excel_app).delete_variants(request_rows)
        if save and deleted:
            self.save()
        return deleted

    def delete_variants_by_part_number(self, part_numbers: list[str], save: bool = True) -> int:
        """Deletes the variants whose REQ row has one of these part numbers, wherever the rows are now.

        The part number is compared on the sheet itself right before deleting, so a row number that moved since
        the table was loaded can never take another variant with it."""
        wanted = {normalize_part_number(part).upper() for part in part_numbers if normalize_part_number(part)}
        rows = [
            row for row, part in VariantRowReader(self._worksheet()).request_rows_with_part_number()
            if part.upper() in wanted
        ]
        deleted = VariantRowWriter(self._worksheet(), self.excel_app).delete_variants(rows)
        if save and deleted:
            self.save()
        return deleted

    def write_webflow_links(self, links: dict[str, str], save: bool = True) -> int:
        written = VariantRowWriter(self._worksheet(), self.excel_app).write_webflow_links(
            VariantRowReader(self._worksheet()).latest_request_rows(), links
        )
        if save and written:
            self.save()
        return written

    def write_webflow_numbers(self, numbers: dict[str, dict[str, str]], save: bool = True) -> int:
        written = VariantRowWriter(self._worksheet(), self.excel_app).write_webflow_numbers(
            VariantRowReader(self._worksheet()).latest_request_rows(), numbers
        )
        if save and written:
            self.save()
        return written

    def write_impl_values(self, updates: dict[str, ImplUpdate], save: bool = True) -> dict[str, ImplOutcome]:
        request_rows: dict[str, list[int]] = {}
        for row, part in VariantRowReader(self._worksheet()).request_rows_with_part_number():
            request_rows.setdefault(part.upper(), []).append(row)
        outcomes = VariantRowWriter(self._worksheet(), self.excel_app).write_impl_values(request_rows, updates)
        if save and any(outcome.written for outcome in outcomes.values()):
            self.save()
        return outcomes

    def write_container_checksums(self, checksums: dict[str, str], save: bool = True) -> int:
        written = VariantRowWriter(self._worksheet(), self.excel_app).write_container_checksums(
            VariantRowReader(self._worksheet()).latest_request_rows(), checksums
        )
        if save and written:
            self.save()
        return written

    def load_variant_rows(self) -> list[dict]:
        return VariantRowReader(self._worksheet()).load_variant_rows()

    def load_webflow_variants(self) -> list[dict]:
        return VariantRowReader(self._worksheet()).load_webflow_variants()
