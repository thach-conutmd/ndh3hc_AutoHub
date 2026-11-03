"""Populate the protected Form B template from Master Sheet variant data."""
from __future__ import annotations

import copy
import logging
import re
from datetime import date
from pathlib import Path
from typing import Callable, Protocol

import openpyxl

from autohub.config import BASE_DIR
from autohub.core.checksums import normalize_crc32
from autohub.core.progress import ProgressCallback, no_progress
from autohub.services.common.encrypted_workbook import decrypt_workbook

_logger = logging.getLogger(__name__)
TEMPLATE_PATH = BASE_DIR / "datas" / "FormB" / "62XS_MP2_FORMB_MG1CS022_20260511.xlsx"
FIRST_BLOCK_ROW = 26
BLOCK_ROWS = 13
BLOCK_SPACING = 1
FOOTER_ROW = 42
VARIANT_COLUMNS = tuple(range(2, 8))


class FormBWebFlow(Protocol):
    def get_container_crc32(self, link: str, filename: str) -> str: ...

    def quit(self) -> None: ...


def _master_values(variant: dict) -> dict:
    values = variant.get("form_b")
    if not isinstance(values, dict):
        raise ValueError(f"{variant.get('part_number', 'Variant')}: Form B data is missing from the Master Sheet row.")
    return values


def _text(values: dict, column: str) -> str:
    value = values.get(column)
    if value is None:
        return ""
    return " ".join(str(value).split())


def _variant_label(customer_hw_number: str, part_number: str) -> str:
    pieces = [piece.strip() for piece in customer_hw_number.split("-")]
    if len(pieces) >= 4:
        return f"{pieces[-3]} -{pieces[-2]}"
    return customer_hw_number or part_number


def _container_filename(values: dict, part_number: str) -> str:
    container = _text(values, "AX")
    if not container:
        raise ValueError(f"{part_number}: Master Sheet column AX has no Container file name.")
    return container if Path(container).suffix.casefold() == ".cnt" else f"{container}.cnt"


def _description(values: dict, column: str) -> str:
    text = _text(values, column)
    return text.split("|")[-1].strip() if column == "AD" else text


def _tp_description(value: str) -> str:
    match = re.search(r"\bTP(?:ROT)?\s*=?\s*(\d+)\b", value, re.IGNORECASE)
    return f"TPROT={match.group(1)}" if match else value


def _safe_filename_part(value: str, label: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    if not value:
        raise ValueError(f"Master Sheet {label} is blank or invalid for the Form B filename.")
    return value


def _output_filename(variants: list[dict], generated_on: date) -> str:
    names = set()
    for variant in variants:
        event_name = str(variant.get("event_name") or "").strip()
        match = re.search(r"(?:_|/)\s*(MP\d+)\s*$", event_name, re.IGNORECASE)
        if not match:
            raise ValueError(
                f"{variant.get('part_number', 'Variant')}: Master Sheet Project Purpose "
                "does not contain a phase (MP number)."
            )
        names.add((
            _safe_filename_part(str(variant.get("project") or ""), "Project"),
            _safe_filename_part(match.group(1).upper(), "Phase"),
            _safe_filename_part(str(variant.get("ecu_type") or ""), "ECU Type"),
        ))
    if len(names) != 1:
        raise ValueError("Selected variants must have the same Master Sheet Project, Phase and ECU Type.")
    project, phase, ecu_type = names.pop()
    return f"{project}_{phase}_FORMB_{ecu_type}_{generated_on:%Y%m%d}.xlsx"


def _variant_values(variant: dict, checksum: str) -> tuple[str, ...]:
    values = _master_values(variant)
    part_number = str(variant.get("part_number") or "Variant")
    customer_hw_number = _text(values, "AR")
    return (
        _variant_label(customer_hw_number, part_number),
        customer_hw_number,
        _text(values, "AN"),
        _text(values, "AX"),
        _text(values, "CY"),
        _text(values, "CZ"),
        _text(values, "CX"),
        _text(values, "AZ"),
        _container_filename(values, part_number),
        checksum,
        _text(values, "AW"),
        _description(values, "AD"),
        _tp_description(_text(values, "BG")),
    )


def _copy_block(sheet, target_row: int) -> None:
    for offset in range(BLOCK_ROWS):
        source_row = FIRST_BLOCK_ROW + offset
        destination_row = target_row + offset
        for column in range(1, sheet.max_column + 1):
            source = sheet.cell(source_row, column)
            destination = sheet.cell(destination_row, column)
            if source.has_style:
                destination._style = copy.copy(source._style)
            if source.number_format:
                destination.number_format = source.number_format
            if source.alignment:
                destination.alignment = copy.copy(source.alignment)
            if source.protection:
                destination.protection = copy.copy(source.protection)
            if source.value is not None:
                destination.value = source.value
        source_dimension = sheet.row_dimensions[source_row]
        if source_dimension.height is not None:
            sheet.row_dimensions[destination_row].height = source_dimension.height
        sheet.row_dimensions[destination_row].hidden = source_dimension.hidden


def export_form_b(
    variants: list[dict],
    checksums: dict[str, str],
    output_path: str | Path,
    template_path: str | Path = TEMPLATE_PATH,
    today: date | None = None,
    form_information: dict[str, str | date] | None = None,
) -> Path:
    if not variants:
        raise ValueError("Select at least one variant to create Form B.")
    template = Path(template_path)
    generated_on = today or date.today()
    destination = Path(output_path).parent / _output_filename(variants, generated_on)
    if destination.resolve() == template.resolve():
        raise ValueError("Choose a new file name; the Form B template cannot be overwritten.")

    workbook = openpyxl.load_workbook(decrypt_workbook(str(template)))
    try:
        sheet = workbook["FormB"] if "FormB" in workbook.sheetnames else workbook.active
        ecu_types = {
            _text(_master_values(variant), "AP")
            for variant in variants
            if _text(_master_values(variant), "AP")
        }
        if len(ecu_types) > 1:
            raise ValueError("Selected variants must use the same Master Sheet ECU HW Name.")
        if ecu_types:
            sheet["B24"] = next(iter(ecu_types))
        sheet["C13"] = generated_on
        if form_information:
            department = form_information["department_organization"]
            name = form_information["name"]
            phone_number = form_information["phone_number"]
            return_to = form_information["return_to"]
            project_release = form_information["project_release"]
            production_project = form_information["production_project"]
            sheet["C3"] = department
            sheet["C4"] = name
            sheet["C5"] = f"Phone No.: {phone_number}"
            sheet["C13"] = form_information["date"]
            sheet["A18"] = f"After confirmation, please return this paper (FORM B) to {return_to}"
            sheet["A21"] = f"(Production release for project) : {project_release}"
            sheet["A22"] = f"For {production_project} production"
            sheet["B23"] = form_information["bosch_project_number"]
            sheet["B24"] = form_information["ecu_type"]
            receipt_date = form_information.get("expected_receipt_date")
            if receipt_date is not None:
                if not isinstance(receipt_date, date):
                    raise ValueError("Expected Receipt Date must be a valid date.")
                sheet["A43"] = f"We appreciate the receipt by {receipt_date.day} {receipt_date:%B %Y}"

        footer_row = FOOTER_ROW
        for start in range(0, len(variants), len(VARIANT_COLUMNS)):
            block = variants[start : start + len(VARIANT_COLUMNS)]
            if start:
                sheet.insert_rows(footer_row, BLOCK_ROWS + BLOCK_SPACING)
                _copy_block(sheet, footer_row)
            block_row = FIRST_BLOCK_ROW if start == 0 else footer_row
            for row in range(block_row, block_row + BLOCK_ROWS):
                for column in VARIANT_COLUMNS:
                    sheet.cell(row, column).value = None
            for column, variant in zip(VARIANT_COLUMNS, block):
                part_number = str(variant.get("part_number") or "")
                checksum = checksums.get(part_number, "")
                cell_values = _variant_values(variant, checksum)
                for offset, value in enumerate(cell_values):
                    sheet.cell(block_row + offset, column, value)
            if start:
                footer_row += BLOCK_ROWS + BLOCK_SPACING
        destination.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(destination)
        _logger.info("Created Form B workbook with %d variants: %s", len(variants), destination)
    finally:
        workbook.close()
    return destination


class FormBService:
    def __init__(
        self,
        webflow_factory: Callable[[], FormBWebFlow],
        template_path: str | Path = TEMPLATE_PATH,
    ):
        self._webflow_factory = webflow_factory
        self._template_path = Path(template_path)
        self._webflow: FormBWebFlow | None = None

    def generate(
        self,
        variants: list[dict],
        output_path: str | Path,
        progress: ProgressCallback = no_progress,
        form_information: dict[str, str | date] | None = None,
    ) -> Path:
        if not variants:
            raise ValueError("Select at least one variant to create Form B.")
        checksums: dict[str, str] = {}
        missing = []
        for variant in variants:
            part_number = str(variant.get("part_number") or "Variant")
            values = _master_values(variant)
            checksum = normalize_crc32(values.get("BA"))
            if checksum:
                checksums[part_number] = checksum
            else:
                missing.append((variant, _container_filename(values, part_number)))

        unlinked = [
            str(variant.get("part_number") or "Variant")
            for variant, _ in missing
            if not str(variant.get("webflow_link") or "").strip()
        ]
        if unlinked:
            raise ValueError(
                "Master Sheet checksum is blank and no WebFlow job is linked for "
                f"{', '.join(unlinked)}."
            )

        if missing:
            self._webflow = self._webflow_factory()
            try:
                for variant, filename in missing:
                    part_number = str(variant.get("part_number") or "Variant")
                    link = str(variant.get("webflow_link") or "").strip()
                    progress(f"Getting {filename} CRC32 from WebFlow for {part_number}...")
                    checksum = normalize_crc32(self._webflow.get_container_crc32(link, filename))
                    if not checksum:
                        raise RuntimeError(f"{part_number}: WebFlow did not provide a CRC32 for {filename}.")
                    checksums[part_number] = checksum
            finally:
                self.shutdown()
        progress("Creating the Form B workbook...")
        return export_form_b(
            variants, checksums, output_path, self._template_path, form_information=form_information
        )

    def shutdown(self) -> None:
        if self._webflow is None:
            return
        try:
            self._webflow.quit()
        finally:
            self._webflow = None
