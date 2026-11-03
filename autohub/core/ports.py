"""Narrow interfaces the services layer implements and the feature modules depend on.

Each protocol lists only what one client needs, so a fake can stand in for Excel in tests.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Protocol, runtime_checkable

from autohub.core.records import DocumentReader, EcuInfoData, HWLookup, KickOffInfo, SystemMatrixData
from autohub.core.webflow_defaults import WebFlowDefaults


class SheetSession(Protocol):
    """Something that holds an external resource (an Excel instance) between open and close."""

    def open(self) -> None: ...

    def close(self) -> None: ...


class FormBGenerator(Protocol):
    def generate(
        self,
        variants: list[dict],
        output_path: str,
        progress: Callable[[str], None],
        form_information: dict[str, str | date] | None = None,
        master_sheet_path: str = "",
    ) -> object: ...

    def shutdown(self) -> None: ...


class VariantReader(Protocol):
    def load_variant_rows(self) -> list[dict]: ...

    def load_webflow_variants(self) -> list[dict]: ...


class ContainerChecksumSheet(SheetSession, Protocol):
    def write_container_checksums(self, checksums: dict[str, str], save: bool = True) -> int: ...


class VariantWriter(Protocol):
    def save_variant_rows(self, variants: list[dict], save: bool = True) -> list[dict]: ...

    def delete_variant_rows(self, request_rows: list[int], save: bool = True) -> int: ...


@runtime_checkable
class PartNumberDeleter(Protocol):
    """A sheet whose rows move (rows deleted or inserted), so variants are found by part number, not row number."""

    def delete_variants_by_part_number(self, part_numbers: list[str], save: bool = True) -> int: ...


@runtime_checkable
class WebFlowLinkWriter(Protocol):
    """A sheet with a column for the WebFlow job link of each variant."""

    def write_webflow_links(self, links: dict[str, str], save: bool = True) -> int:
        """Part number -> job link; returns how many variants got their link."""
        ...


@runtime_checkable
class WebFlowNumberWriter(Protocol):
    def write_webflow_numbers(self, numbers: dict[str, dict[str, str]], save: bool = True) -> int: ...


class NewVariantSource(Protocol):
    def compute_new_variants(
        self, system_info: SystemMatrixData,
        ecu_info: EcuInfoData,
        hw_info: HWLookup | None = None,
        kick_off: KickOffInfo | None = None,
        variant_defaults: WebFlowDefaults | None = None,
    ) -> list[dict]: ...


class VariantSheet(SheetSession, VariantReader, VariantWriter, NewVariantSource, Protocol):
    """The full Master Sheet session; services annotate narrower views of it where they can."""


class EcuInfoDocument(DocumentReader, SheetSession, Protocol):
    ecu_info: EcuInfoData


class SystemMatrixDocument(DocumentReader, SheetSession, Protocol):
    system_info: SystemMatrixData


class HWInfoDocument(DocumentReader, HWLookup, Protocol):
    records: list[dict[str, Any]]


class KickOffDocument(DocumentReader, Protocol):
    info: KickOffInfo
