"""Variant workflows over the Master Sheet / ECU Info Sheet / System Matrix (no Qt, no concrete I/O types)."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Callable, Sequence

from autohub.core.a2l_hex import component_id_matches, load_calibration_folder
from autohub.core.progress import ProgressCallback, no_progress
from autohub.core.ports import (
    EcuInfoDocument,
    HWInfoDocument,
    KickOffDocument,
    PartNumberDeleter,
    SystemMatrixDocument,
    VariantSheet,
)

#: Opens whatever per-thread resource the documents need (COM) around one operation.
SessionFactory = Callable[[], AbstractContextManager]


@dataclass(frozen=True)
class NewVariantResult:
    variants: list[dict]
    warnings: list[str]


class VariantService:
    """Each method runs inside its own session, so it is safe to call from a worker thread."""

    def __init__(
        self,
        master_sheet_factory: Callable[[str], VariantSheet],
        ecu_info_factory: Callable[[str], EcuInfoDocument],
        system_matrix_factory: Callable[[str], SystemMatrixDocument],
        hw_info_factory: Callable[[str], HWInfoDocument],
        session_factory: SessionFactory,
        kick_off_factory: Callable[[str], KickOffDocument],
        master_sheet_checker: Callable[[str], str],
    ):
        self._master_sheet_factory = master_sheet_factory
        self._ecu_info_factory = ecu_info_factory
        self._system_matrix_factory = system_matrix_factory
        self._hw_info_factory = hw_info_factory
        self._session = session_factory
        self._kick_off_factory = kick_off_factory
        self._master_sheet_checker = master_sheet_checker

    def master_sheet_problem(self, master_sheet_path: str) -> str:
        """Why the file is not a readable Master Sheet (missing, wrong format or layout); empty when it is."""
        return self._master_sheet_checker(master_sheet_path)

    def _require_master_sheet(self, path: str) -> None:
        problem = self.master_sheet_problem(path)
        if problem:
            raise ValueError(problem)

    @staticmethod
    def _load(document, description: str) -> None:
        if not document.load_data():
            raise ValueError(getattr(document, "last_error", "") or f"Could not load {description}.")

    def compute_new_variants(
        self,
        master_sheet_path: str,
        ecu_info_path: str,
        system_matrix_path: str,
        hw_info_path: str = "",
        kick_off_path: str = "",
        progress: ProgressCallback = no_progress,
        hex_folder_path: str = "",
        a2l_symbol_name: str = "I14229_numCompID_CA",
    ) -> NewVariantResult:
        self._require_master_sheet(master_sheet_path)
        with self._session():
            progress("Opening the source files...")
            system_matrix = self._system_matrix_factory(system_matrix_path)
            ecu_info_sheet = self._ecu_info_factory(ecu_info_path)
            master_sheet = self._master_sheet_factory(master_sheet_path)
            try:
                hw_info = None
                if hw_info_path:
                    progress("Reading HW info...")
                    hw_info = self._hw_info_factory(hw_info_path)
                    self._load(hw_info, "HW info")

                kick_off = None
                if kick_off_path:
                    progress("Reading the Kick Off Meeting...")
                    kick_off_document = self._kick_off_factory(kick_off_path)
                    self._load(kick_off_document, "Kick Off Meeting")
                    kick_off = kick_off_document.info

                progress("Reading the System Matrix...")
                system_matrix.open()
                self._load(system_matrix, "System Matrix data")

                progress("Reading the ECU Info Sheet...")
                ecu_info_sheet.open()
                self._load(ecu_info_sheet, "ECU Info Sheet data")

                progress("Opening the Master Sheet...")
                master_sheet.open()
                progress("Building the new variants...")
                variants = master_sheet.compute_new_variants(
                    system_matrix.system_info, ecu_info_sheet.ecu_info, hw_info, kick_off
                )
                warnings = []
                if hex_folder_path:
                    calibrations = load_calibration_folder(hex_folder_path, a2l_symbol_name)
                    for variant in variants:
                        expected = str(variant.get("J") or "").strip()
                        if not expected:
                            warnings.append("A new variant has no DWG number to compare with the calibration ID.")
                            continue
                        matching_calibration = next(
                            (
                                item
                                for item in calibrations
                                if component_id_matches(item.component_id, expected)
                            ),
                            None,
                        )
                        if matching_calibration is None:
                            available = ", ".join(
                                f"{item.hex_filename}: {item.component_id}" for item in calibrations
                            )
                            warnings.append(
                                f"{expected}: no calibration HEX file matches the DWG number "
                                f"(found {available})."
                            )
                        else:
                            variant["AZ"] = matching_calibration.hex_filename
                return NewVariantResult(variants, warnings)
            finally:
                master_sheet.close()
                ecu_info_sheet.close()
                system_matrix.close()

    def save_variants(
        self,
        master_sheet_path: str,
        variants: list[dict],
        progress: ProgressCallback = no_progress,
        deleted_rows: Sequence[int] = (),
        deleted_part_numbers: Sequence[str] = (),
    ) -> tuple[list, list[dict], list[dict]]:
        """Writes `variants`, then deletes the variants at `deleted_rows` (their sheet rows).

        A sheet that finds variants by part number (`PartNumberDeleter`) deletes by `deleted_part_numbers` instead.

        Deleting comes last so the "_row" numbers of the written variants are still right while writing.
        Returns (saved, reloaded table rows, WebFlow-ready variants)."""
        self._require_master_sheet(master_sheet_path)
        with self._session():
            master_sheet = self._master_sheet_factory(master_sheet_path)
            try:
                progress("Opening the Master Sheet...")
                master_sheet.open()
                progress(f"Writing {len(variants)} variant(s)...")
                saved = master_sheet.save_variant_rows(variants, save=not deleted_rows)
                if deleted_rows:
                    progress(f"Deleting {len(deleted_rows)} variant(s)...")
                    if isinstance(master_sheet, PartNumberDeleter) and deleted_part_numbers and all(deleted_part_numbers):
                        master_sheet.delete_variants_by_part_number(list(deleted_part_numbers))
                    else:
                        master_sheet.delete_variant_rows(list(deleted_rows))
                progress("Reloading the variants...")
                rows = master_sheet.load_variant_rows()
                available = master_sheet.load_webflow_variants()
                return saved, rows, available
            finally:
                master_sheet.close()

    def load_variants(
        self, master_sheet_path: str, progress: ProgressCallback = no_progress
    ) -> tuple[list[dict], list[dict]]:
        """Returns (table rows, WebFlow-ready variants)."""
        self._require_master_sheet(master_sheet_path)
        with self._session():
            master_sheet = self._master_sheet_factory(master_sheet_path)
            try:
                progress("Opening the Master Sheet...")
                master_sheet.open()
                progress("Reading the variants...")
                rows = master_sheet.load_variant_rows()
                available = master_sheet.load_webflow_variants()
                return rows, available
            finally:
                master_sheet.close()
