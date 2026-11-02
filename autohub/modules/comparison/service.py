"""Sequential comparison orchestration, independent of Qt and concrete browser adapters."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .comparison import ComparisonRow, compare_parameters
from .matching import (
    master_parameters, match_variant, validate_export_link, validate_link, variant_identity,
)
from .xml_parser import parse_xml

_logger = logging.getLogger(__name__)
Progress = Callable[[int, str, str], None]


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
                    target = parse_xml(export(variant.get("webflow_link") or ""))
                    validate_export_link(target, variant.get("webflow_link") or "")
                    base = None
                    base_link = (variant.get("base_webflow_link") or "").strip()
                    if base_link:
                        progress(index, "Exporting Base XML", "")
                        try:
                            base = parse_xml(export(base_link))
                            validate_export_link(base, base_link)
                        except Exception as error:
                            raise ValueError(f"Base XML: {error}") from error
                    progress(index, "Comparing", "")
                    matched = match_variant(master_variants, target)
                    if variant_identity(matched) != variant_identity(variant):
                        raise ValueError("Export XML does not match the selected Variant + SW Part Number.")
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
