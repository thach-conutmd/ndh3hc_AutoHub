"""Optional capabilities a page widget can advertise to the main window.

Small, separate interfaces (instead of one fat page base class) so a page only
implements what it actually needs.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VariantSource(Protocol):
    """Page that publishes variants; ``variantsLoaded`` is a Qt ``Signal(list)``."""

    variantsLoaded: Any


@runtime_checkable
class VariantSink(Protocol):
    """Page that consumes variants published by a ``VariantSource``."""

    def set_variants(self, variants: list[dict]) -> None: ...


@runtime_checkable
class WebFlowLinkSource(Protocol):
    """Page publishing part-number-to-job-link updates through a Qt ``Signal(dict)``."""

    webflowLinksUpdated: Any


@runtime_checkable
class WebFlowLinkSink(Protocol):
    def set_webflow_links(self, links: dict[str, str]) -> None: ...


@runtime_checkable
class WebFlowNumberSource(Protocol):
    webflowNumbersUpdated: Any


@runtime_checkable
class WebFlowNumberSink(Protocol):
    def set_webflow_numbers(self, numbers: dict[str, dict[str, str]], persisted: bool = True) -> None: ...


@runtime_checkable
class SettingsSource(Protocol):
    settingsChanged: Any


@runtime_checkable
class SettingsSink(Protocol):
    def apply_settings(self, changes: dict) -> None: ...


@runtime_checkable
class Closable(Protocol):
    """Page that must release external resources when the app closes."""

    def shutdown(self) -> None: ...


@runtime_checkable
class StartupTask(Protocol):
    """Page with work to offer once the main window is shown (e.g. resume interrupted work)."""

    def on_startup(self) -> None: ...


@runtime_checkable
class LeaveGuard(Protocol):
    """Page that may hold unsaved changes; asked before the user leaves it or closes the app."""

    def confirm_leave(self) -> bool:
        """True when leaving is fine, False to stay on the page."""
        ...
