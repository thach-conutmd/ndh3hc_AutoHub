"""Form B page: select Master Sheet variants and export a filled template."""
from __future__ import annotations

import logging
from datetime import date, datetime

from PySide6.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from autohub.core.dialogs import Dialogs, QtDialogs
from autohub.core.ports import FormBGenerator
from autohub.core.workers import TaskRunner
from autohub.modules.creation.variant_checklist import VariantChecklist
from autohub.ui.theme import set_muted

_logger = logging.getLogger(__name__)

_FORM_FIELDS = (
    ("department_organization", "Department / Organization"),
    ("name", "Name"),
    ("phone_number", "Phone Number"),
    ("date", "Date"),
    ("return_to", "Return To"),
    ("project_release", "Project / Production Release Project"),
    ("production_project", "Production Project"),
    ("bosch_project_number", "Bosch Project Number"),
    ("ecu_type", "ECU-Type"),
)


class FormBWidget(QWidget):
    def __init__(self, service: FormBGenerator, dialogs: Dialogs | None = None):
        super().__init__()
        self._service = service
        self._dialogs = dialogs or QtDialogs(self)
        self._tasks = TaskRunner()
        self._running = False

        title = QLabel("Form B")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        subtitle = QLabel("Select Master Sheet variants to create a formatted Form B workbook.")
        subtitle.setWordWrap(True)
        set_muted(subtitle, True)

        self._checklist = VariantChecklist()
        self._form_fields: dict[str, QLineEdit] = {}
        information_group = QGroupBox("Form B Information")
        information_grid = QGridLayout(information_group)
        information_grid.setContentsMargins(12, 10, 12, 10)
        information_grid.setHorizontalSpacing(12)
        information_grid.setVerticalSpacing(6)
        for index, (key, label_text) in enumerate(_FORM_FIELDS):
            field_layout = QVBoxLayout()
            field_layout.setSpacing(3)
            label = QLabel(label_text)
            field = QLineEdit()
            field.setObjectName(key)
            field.setAccessibleName(label_text)
            if key == "date":
                field.setPlaceholderText("YYYY-MM-DD")
            self._form_fields[key] = field
            field_layout.addWidget(label)
            field_layout.addWidget(field)
            information_grid.addLayout(field_layout, index // 3, index % 3)

        selection_title = QLabel("Select variants")
        selection_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self._selection_summary = QLabel("0 selected · 0 available")
        set_muted(self._selection_summary, True)
        selection_header = QHBoxLayout()
        selection_header.addWidget(selection_title)
        selection_header.addStretch(1)
        selection_header.addWidget(self._selection_summary)
        selection_group = QGroupBox()
        selection_group.setStyleSheet(
            "QGroupBox { border: 1px solid palette(mid); border-radius: 8px; margin-top: 4px; }"
        )
        selection_layout = QVBoxLayout(selection_group)
        selection_layout.setContentsMargins(14, 14, 14, 14)
        selection_layout.setSpacing(12)
        selection_layout.addLayout(selection_header)
        selection_layout.addWidget(self._checklist, 1)

        self._export_btn = QPushButton("Export Form B")
        self._export_btn.setMinimumWidth(180)
        self._export_btn.setMinimumHeight(36)
        self._export_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._export)
        self._footer_hint = QLabel("Select at least one variant to continue.")
        set_muted(self._footer_hint, True)
        footer = QHBoxLayout()
        footer.addWidget(self._footer_hint)
        footer.addStretch(1)
        footer.addWidget(self._export_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(information_group)
        layout.addWidget(selection_group, stretch=1)
        layout.addLayout(footer)

        self._checklist.selectionChanged.connect(self._update_selection)

    def set_variants(self, variants: list[dict]) -> None:
        self._checklist.set_variants(variants)

    def _update_selection(self, selected: int, total: int) -> None:
        self._selection_summary.setText(f"{selected} selected · {total} available")
        self._footer_hint.setText(
            "Ready to export Form B." if selected else
            "Select at least one variant to continue." if total else
            "Load variants on Home to get started."
        )
        self._export_btn.setEnabled(selected > 0 and not self._running)

    def _export(self) -> None:
        variants = self._checklist.selected_variants()
        if not variants:
            self._dialogs.error("Form B", "Select at least one variant.")
            return
        form_information, invalid_fields = self._collect_form_information()
        if invalid_fields:
            self._dialogs.error(
                "Form B",
                "Complete the following Form B Information fields:\n" + "\n".join(invalid_fields),
            )
            return
        path = self._dialogs.save_file("Export Form B", "Form_B.xlsx", "Excel workbook (*.xlsx)")
        if not path:
            return
        window = self._dialogs.open_progress("Export Form B")
        self._running = True
        self._checklist.setEnabled(False)
        self._export_btn.setEnabled(False)
        self._export_btn.setText("Exporting...")
        self._tasks.start(
            lambda: self._service.generate(variants, path, window.step, form_information),
            lambda result: self._finish(result, window),
            lambda error: self._fail(error, window),
        )

    def _collect_form_information(self) -> tuple[dict[str, str | date], list[str]]:
        values: dict[str, str | date] = {}
        invalid_fields = []
        for key, label in _FORM_FIELDS:
            value = " ".join(self._form_fields[key].text().split())
            if not value:
                invalid_fields.append(label)
            elif key == "date":
                try:
                    parsed = datetime.strptime(value, "%Y-%m-%d").date()
                except ValueError:
                    invalid_fields.append(f"{label} (use YYYY-MM-DD)")
                else:
                    values[key] = parsed
            else:
                values[key] = value
        return values, invalid_fields

    def _finish(self, path, window) -> None:
        self._running = False
        self._checklist.setEnabled(True)
        self._export_btn.setText("Export Form B")
        self._update_selection(len(self._checklist.selected_variants()), self._checklist.variant_count)
        _logger.info("Exported Form B workbook: %s", path)
        window.succeed(f"Form B workbook saved to {path}.")

    def _fail(self, error: str, window) -> None:
        self._running = False
        self._checklist.setEnabled(True)
        self._export_btn.setText("Export Form B")
        self._update_selection(len(self._checklist.selected_variants()), self._checklist.variant_count)
        _logger.error("Form B export failed: %s", error)
        window.fail(error)

    def shutdown(self) -> None:
        self._service.shutdown()
