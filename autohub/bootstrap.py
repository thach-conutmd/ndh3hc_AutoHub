"""Composition root: the only place that knows which concrete classes implement the interfaces."""
from __future__ import annotations

from autohub.core.batch_journal import JsonBatchJournal
from autohub.core.com import com_session
from autohub.core.module_base import AutoHubModule
from autohub.core.settings import JsonSettingsStore, SettingsStore
from autohub.modules.comparison.module import ComparisonModule
from autohub.modules.creation.module import CreationModule
from autohub.modules.creation.service import WebFlowJobService
from autohub.modules.home.module import HomeModule
from autohub.modules.home.service import VariantService
from autohub.modules.settings.module import SettingsModule
from autohub.services.EcuInfoSheet.EcuInfoSheet import EcuInfoSheet
from autohub.services.HWInfo.HWInfo import HWInfo
from autohub.services.KickOff.KickOff import KickOffMeeting
from autohub.services.MasterSheet.master_sheet_factory import master_sheet_format_error, open_master_sheet
from autohub.services.SystemMatrix.SystemMatrix import SystemMatrix
from autohub.services.WebFlow.WebFlow import WebFlow


def build_variant_service() -> VariantService:
    return VariantService(
        master_sheet_factory=open_master_sheet,
        ecu_info_factory=EcuInfoSheet,
        system_matrix_factory=SystemMatrix,
        hw_info_factory=HWInfo,
        session_factory=com_session,
        kick_off_factory=KickOffMeeting,
        master_sheet_checker=master_sheet_format_error,
    )


def build_modules(settings: SettingsStore | None = None) -> list[AutoHubModule]:
    """Sidebar modules in display order. To add a feature, build and append its module here."""
    settings = settings or JsonSettingsStore()
    return [
        HomeModule(build_variant_service, settings),
        CreationModule(lambda: WebFlowJobService(WebFlow, open_master_sheet, com_session, journal=JsonBatchJournal()), settings),
        ComparisonModule(),
        SettingsModule(settings),
    ]
