"""Creation page: pick loaded variants and create/fill WebFlow jobs for them."""
from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from autohub.core.dialogs import Dialogs, QtDialogs
from autohub.core.progress import ProgressWindow
from autohub.core.settings import SettingsStore
from autohub.core.workers import TaskRunner
from autohub.core.webflow_numbers import number_updates
from autohub.modules.creation.config_form import WebFlowSettingsDialog, load_config
from autohub.modules.creation.service import WebFlowJobService
from autohub.modules.creation.variant_checklist import VariantChecklist
from autohub.ui.theme import set_muted

_logger = logging.getLogger(__name__)


class CreationWidget(QWidget):
    webflowLinksUpdated = Signal(dict)
    webflowNumbersUpdated = Signal(dict, bool)

    def __init__(self, service: WebFlowJobService, settings: SettingsStore, dialogs: Dialogs | None = None):
        super().__init__()
        self._dialogs = dialogs or QtDialogs(self)

        self._service = service
        self._tasks = TaskRunner()

        title = QLabel("Create WebFlow jobs")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        subtitle = QLabel("Choose one or more variants loaded from the Master Sheet workflow.")
        set_muted(subtitle, True)

        self._checklist = VariantChecklist()
        self._settings = settings

        self._create_jobs_btn = QPushButton("Create WebFlow jobs")
        self._create_jobs_btn.setFixedWidth(190)
        self._create_jobs_btn.clicked.connect(self._create_webflow_jobs)
        self._settings_btn = QPushButton("Settings")
        self._settings_btn.setFixedWidth(120)
        self._settings_btn.clicked.connect(self._open_settings)
        create_jobs_row = QHBoxLayout()
        create_jobs_row.addWidget(self._settings_btn)
        create_jobs_row.addStretch(1)
        create_jobs_row.addWidget(self._create_jobs_btn)
        create_jobs_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)
        layout.addWidget(self._checklist, stretch=1)
        layout.addSpacing(8)
        layout.addLayout(create_jobs_row)

    def set_variants(self, variants: list[dict]) -> None:
        """Populate the checklist with variants loaded/created on the Home page."""
        self._checklist.set_variants(variants)

    def _open_settings(self) -> None:
        dialog = WebFlowSettingsDialog(load_config(self._settings), self)
        if dialog.exec():
            self._settings.update(**dialog.values())

    def _create_webflow_jobs(self) -> None:
        selected = self._checklist.selected_variants()
        if not selected:
            QMessageBox.critical(self, "Create WebFlow jobs", "Select at least one variant.")
            return

        selected = self._without_declined_duplicates(selected)
        if not selected:
            return

        config = load_config(self._settings)
        if not config.tool_version or not config.routing:
            QMessageBox.critical(self, "Create WebFlow jobs", "Tool version and routing are required.")
            return

        if len({(v.get("ecu_generation"), v.get("brand"), v["ecu_type"]) for v in selected}) != 1:
            QMessageBox.critical(self, "Create WebFlow jobs", "Selected variants must use the same ECU Generation, Brand and ECU Type.")
            return

        _logger.info("Create WebFlow jobs clicked (%d variant(s), config=%s)", len(selected), config)
        master_sheet_path = self._settings.load().get("master_sheet_path", "")
        self._start_task(lambda step: self._service.create_jobs(selected, config, step, master_sheet_path))

    def on_startup(self) -> None:
        """Offers to continue a WebFlow batch that did not finish, e.g. because the app crashed."""
        pending = self._service.pending_batch()
        if not pending:
            return
        names = ", ".join(v.get("part_number", "?") for v in pending["variants"])
        done = len(pending.get("results", []))
        if self._dialogs.confirm(
            "Continue WebFlow jobs",
            "WebFlow job creation did not finish the last time AutoHub ran.\n\n"
            f"Variants: {names}\nCompleted: {done} of {len(pending['variants'])} job(s)\n\n"
            "Continue the work now? Choose No to discard it.",
        ):
            _logger.info("Continuing the unfinished WebFlow batch")
            self._start_task(self._service.resume_jobs)
        else:
            self._service.discard_pending_batch()

    def _start_task(self, work) -> None:
        self._create_jobs_btn.setEnabled(False)
        self._create_jobs_btn.setText("Creating jobs...")
        window = QtDialogs(self).open_progress("Create WebFlow jobs")
        self._tasks.start(
            lambda: work(window.step),
            lambda results: self._finish_webflow_jobs(results, window),
            lambda error: self._fail_webflow_jobs(error, window),
        )

    def _without_declined_duplicates(self, selected: list[dict]) -> list[dict]:
        """Asks before creating a second job for variants that already have a WebFlow link.

        Returns the variants to create; empty when the user cancels or nothing is left."""
        existing = [v for v in selected if self._checklist.has_link(v["part_number"])]
        if not existing:
            return selected
        names = "\n".join(f"  {v['part_number']}" for v in existing)
        answer = self._dialogs.ask_yes_no_cancel(
            "Create WebFlow jobs",
            f"{len(existing)} selected variant(s) already have a WebFlow job:\n{names}\n\n"
            "Create new jobs for them anyway?",
            yes_text="Create anyway",
            no_text="Skip them",
        )
        if answer is None:
            return []
        if answer:
            return selected
        remaining = [v for v in selected if v not in existing]
        if not remaining:
            self._dialogs.info("Create WebFlow jobs", "Every selected variant already has a WebFlow job.")
        return remaining

    def _finish_webflow_jobs(self, results: list[dict], window: ProgressWindow) -> None:
        self._create_jobs_btn.setEnabled(True)
        self._create_jobs_btn.setText("Create WebFlow jobs")
        self._checklist.clear_selection()
        links = {item["PartNumber"]: item["Url"] for item in results if item.get("Url")}
        self._checklist.set_links(links)
        self.webflowLinksUpdated.emit(links)
        numbers = number_updates(results)
        self._checklist.set_numbers(numbers)
        self.webflowNumbersUpdated.emit(numbers, not any(item.get("NumberError") for item in results))
        _logger.info("Created %d WebFlow job(s)", len(results))
        summary = "\n".join(f"{item['PartNumber']}: {item['JobId']}" for item in results)
        warnings = [
            f"{item['PartNumber']}: {warning}"
            for item in results
            for warning in item.get("Warnings", [])
        ]
        if warnings:
            message = (
                f"Created {len(results)} WebFlow job(s), but some requested values could not be changed:\n"
                f"{summary}\n\n" + "\n".join(warnings)
            )
        else:
            message = f"Created and filled {len(results)} WebFlow job(s).\n{summary}"
        link_error = next((item["LinkError"] for item in results if item.get("LinkError")), "")
        if link_error:
            message += f"\n\nThe links were not written to the Master Sheet: {link_error}"
        number_error = next((item["NumberError"] for item in results if item.get("NumberError")), "")
        if number_error:
            message += f"\n\nThe numbers were not written to the Master Sheet: {number_error}"
        message += f"\n\nTotal time: {self._service.last_elapsed_seconds:.1f} seconds."
        window.succeed(message)

    def _fail_webflow_jobs(self, error: str, window: ProgressWindow) -> None:
        self._create_jobs_btn.setEnabled(True)
        self._create_jobs_btn.setText("Create WebFlow jobs")
        self._checklist.clear_selection()
        _logger.error("Create WebFlow jobs failed: %s", error)
        window.fail(f"{error}\n\nTotal time: {self._service.last_elapsed_seconds:.1f} seconds.")

    def shutdown(self) -> None:
        """Called by MainWindow on close so we don't leave a browser session running."""
        self._service.shutdown()
