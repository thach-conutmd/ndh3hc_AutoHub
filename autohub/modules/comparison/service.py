"""Sequential comparison orchestration, independent of Qt and concrete browser adapters."""
from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from .comparison import ComparisonRow, compare_parameters, compare_xml_datasets
from .matching import (
    master_parameters, match_variant, validate_export_link, validate_link, variant_identity,
)
from .xml_parser import MAX_XML_BYTES, ParameterMap, comparison_parameters, parse_xml

_logger = logging.getLogger(__name__)
Progress = Callable[[int, str, str], None]


class _ComparisonCancelled(Exception):
    pass


def compare_xml_files(
    base_path: str, target_paths: str | Sequence[str], progress: Progress = lambda *_: None,
    cancelled: Callable[[], bool] = lambda: False,
) -> list[ComparisonRow] | None:
    """Read local exports without a browser or Master Sheet; never write either source."""
    targets = [target_paths] if isinstance(target_paths, str) else list(target_paths)
    if not targets:
        raise ValueError("Target XML: select at least one XML file.")
    sources = [("Base", base_path), *(("Target", path) for path in targets)]
    for label, path in sources:
        if not path or not Path(path).is_file() or Path(path).suffix.casefold() != ".xml":
            raise ValueError(f"{label} XML: select an existing XML file ({Path(path).name}).")

    def read(label: str, path: str) -> ParameterMap:
        try:
            with open(path, "rb") as source:
                return comparison_parameters(parse_xml(source.read(MAX_XML_BYTES + 1)))
        except (OSError, ValueError) as error:
            raise ValueError(f"{label} XML: {error} ({Path(path).name})") from error

    def cancel() -> None:
        for index in range(len(targets)):
            progress(index, "Cancelled", "")

    if cancelled():
        cancel()
        return None
    progress(0, "Parsing Base XML", "")
    base = read("Base", base_path)

    def datasets() -> Iterator[ParameterMap]:
        for index, path in enumerate(targets):
            if cancelled():
                raise _ComparisonCancelled
            progress(index, "Parsing Target XML", "")
            target = read("Target", path)
            progress(index, "Comparing", "")
            yield target

    if cancelled():
        cancel()
        return None
    try:
        rows = compare_xml_datasets(
            base, datasets(), on_target=lambda index: progress(index, "Completed", ""),
        )
    except _ComparisonCancelled:
        cancel()
        return None
    if cancelled():
        cancel()
        return None
    return rows


class ExportSession(Protocol):
    def open_dashboard_page(self) -> bool: ...

    def export_job_xml(self, link: str) -> bytes: ...

    def quit(self) -> None: ...


@dataclass
class VariantResult:
    variant: str
    software: str
    rows: list[ComparisonRow] = field(default_factory=list)
    error: str = ""
    cancelled: bool = False


class ComparisonService:
    def __init__(self, webflow_factory: Callable[..., ExportSession]):
        self._factory = webflow_factory

    def run(
        self, selected: list[dict], master_variants: list[dict],
        connection: dict | None = None, progress: Progress = lambda *_: None,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> list[VariantResult]:
        if not selected:
            return []
        session: ExportSession | None = None
        connection = connection or {}

        def export(link: str) -> bytes:
            nonlocal session
            validated = validate_link(link)
            try:
                if session is None:
                    session = self._factory(**connection)
                    if not session.open_dashboard_page():
                        raise RuntimeError("Could not open the authenticated WebFlow dashboard.")
                return session.export_job_xml(validated)
            except Exception:
                if session is not None:
                    try:
                        session.quit()
                    except Exception:
                        _logger.exception("Could not close the failed Comparison WebFlow browser")
                    session = None
                raise

        results = []
        try:
            for index in range(len(selected)):
                progress(index, "Pending", "")
            for index, variant in enumerate(selected):
                result = VariantResult(
                    str(variant.get("part_number") or ""),
                    str(variant.get("hardware", {}).get("software_part_number") or ""),
                )
                results.append(result)
                if cancelled():
                    result.cancelled = True
                    progress(index, "Cancelled", "")
                    continue
                try:
                    progress(index, "Exporting Target XML", "")
                    target = comparison_parameters(parse_xml(export(variant.get("webflow_link") or "")))
                    validate_export_link(target, variant.get("webflow_link") or "")
                    base = None
                    base_link = (variant.get("base_webflow_link") or "").strip()
                    if base_link:
                        progress(index, "Exporting Base XML", "")
                        try:
                            base = comparison_parameters(parse_xml(export(base_link)))
                            validate_export_link(base, base_link)
                        except Exception as error:
                            raise ValueError(f"Base XML: {error}") from error
                    progress(index, "Comparing", "")
                    matched = match_variant(master_variants, target)
                    if variant_identity(matched) != variant_identity(variant):
                        raise ValueError("Export XML does not match the selected variant's Master Sheet identity.")
                    result.rows = compare_parameters(master_parameters(matched), target, base)
                    progress(index, "Completed", "")
                except Exception as error:
                    _logger.exception("Comparison failed for %s | %s", result.variant, result.software)
                    result.error = str(error) or type(error).__name__
                    progress(index, "Failed", result.error)
            return results
        finally:
            if session is not None:
                try:
                    session.quit()
                except Exception:
                    _logger.exception("Could not close the Comparison WebFlow browser")
