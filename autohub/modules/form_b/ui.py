"""Form B page: select Master Sheet variants and export a filled template."""
from __future__ import annotations

import logging
from datetime import date, datetime

from PySide6.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from autohub.core.dialogs import Dialogs, QtDialogs
from autohub.core.form_b import form_b_phase, manual_phase, master_phase
from autohub.core.ports import FormBGenerator
from autohub.core.settings import JsonSettingsStore, SettingsStore
from autohub.core.settings_keys import (
    DEFAULT_FORM_B_PROJECT_SUFFIX, FORM_B_FIELD_VISIBILITY, FORM_B_PROJECT_SUFFIX_KEY,
)
from autohub.core.workers import TaskRunner
from autohub.modules.form_b.variant_checklist import FormBVariantChecklist
from autohub.ui.theme import set_muted

_logger = logging.getLogger(__name__)
FORM_B_INPUTS_KEY = "form_b_inputs"
_DATE_FIELDS = ("date", "expected_receipt_date")

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
    ("expected_receipt_date", "Expected Receipt Date"),
)
_FORM_PLACEHOLDERS = {
    "department_organization": "e.g. Powertrain Engineering / Release Team",
    "name": "e.g. Alex Nguyen",
    "phone_number": "e.g. +84 28 1234 5678",
    "date": "YYYY-MM-DD",
    "return_to": "e.g. Powertrain Engineering / Alex Nguyen",
    "project_release": "e.g. 6WZX Honda Project",
    "production_project": "e.g. 6WZX MP1",
    "bosch_project_number": "e.g. 328205",
    "ecu_type": "e.g. MG1CS022",
    "expected_receipt_date": "YYYY-MM-DD",
}


class FormBWidget(QWidget):
    def __init__(
        self, service: FormBGenerator, dialogs: Dialogs | None = None,
        settings: SettingsStore | None = None,
    ):
        super().__init__()
        self._service = service
        self._dialogs = dialogs or QtDialogs(self)
        self._settings = settings if settings is not None else JsonSettingsStore()
        self._tasks = TaskRunner()
        self._running = False
        self._variants: list[dict] = []
        self._master_defaults: dict[str, str] = {}
        self._master_reload = False
        self._production_selection: tuple = ()

        title = QLabel("Form B")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        subtitle = QLabel("Select Master Sheet variants to create a formatted Form B workbook.")
        subtitle.setWordWrap(True)
        set_muted(subtitle, True)

        self._checklist = FormBVariantChecklist()
        self._form_fields: dict[str, QLineEdit] = {}
        self._field_containers: dict[str, QWidget] = {}
        saved = self._settings.load().get(FORM_B_INPUTS_KEY, {})
        if not isinstance(saved, dict):
            saved = {}
        information_group = QGroupBox("Form B Information")
        information_grid = self._information_grid = QGridLayout(information_group)
        information_grid.setContentsMargins(12, 10, 12, 10)
        information_grid.setHorizontalSpacing(12)
        information_grid.setVerticalSpacing(6)
        for key, label_text in _FORM_FIELDS:
            container = QWidget()
            field_layout = QVBoxLayout(container)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(3)
            label = QLabel(label_text)
            field = QLineEdit()
            field.setObjectName(key)
            field.setAccessibleName(label_text)
            field.setPlaceholderText(_FORM_PLACEHOLDERS[key])
            if key == "date":
                field.setText(date.today().isoformat())
            elif key not in _DATE_FIELDS and isinstance(saved.get(key), str):
                field.setText(saved[key])
            self._form_fields[key] = field
            field_layout.addWidget(label)
            field_layout.addWidget(field)
            self._field_containers[key] = container
        self._production_warning = QLabel(
            "Selected variants have different Production Project values. Enter Production Project manually."
        )
        self._production_warning.setWordWrap(True)
        self._production_warning.hide()
        information_grid.addWidget(self._production_warning, 4, 0, 1, 3)
        self.apply_settings(self._settings.load())

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
        for key in ("department_organization", "name"):
            self._form_fields[key].textChanged.connect(self._update_return_to)
        self._update_return_to()
        for key, field in self._form_fields.items():
            if key not in _DATE_FIELDS:
                field.textChanged.connect(self._save_inputs)

    def apply_settings(self, settings: dict) -> None:
        applied = {**self._settings.load(), **settings}
        suffix = " ".join(str(applied.get(FORM_B_PROJECT_SUFFIX_KEY, DEFAULT_FORM_B_PROJECT_SUFFIX)).split())
        suffix_changed = hasattr(self, "_project_suffix") and suffix != self._project_suffix
        self._project_suffix = suffix
        if suffix_changed:
            self._master_defaults.pop("project_release", None)
            self._fill_master_information()
        for container in self._field_containers.values():
            self._information_grid.removeWidget(container)
        index = 0
        for key, container in self._field_containers.items():
            visible = key not in FORM_B_FIELD_VISIBILITY or bool(
                applied.get(FORM_B_FIELD_VISIBILITY[key][0], False)
            )
            container.setVisible(visible)
            if visible:
                self._information_grid.addWidget(container, index // 3, index % 3)
                index += 1
        self._information_grid.removeWidget(self._production_warning)
        self._information_grid.addWidget(self._production_warning, (index + 2) // 3, 0, 1, 3)

    def _update_return_to(self) -> None:
        self._form_fields["return_to"].setText(" ".join(
            value for key in ("department_organization", "name")
            if (value := self._form_fields[key].text().strip())
        ))

    def _save_inputs(self) -> None:
        self._settings.update(**{
            FORM_B_INPUTS_KEY: {
                key: field.text().strip()
                for key, field in self._form_fields.items()
                if key not in _DATE_FIELDS
            }
        })

    def set_variants(self, variants: list[dict]) -> None:
        self._variants = variants
        self._master_reload = True
        self._checklist.set_variants(variants)
        self._master_reload = False

    def _update_selection(self, selected: int, total: int) -> None:
        self._fill_master_information()
        self._selection_summary.setText(f"{selected} selected · {total} available")
        self._footer_hint.setText(
            "Ready to export Form B." if selected else
            "Select at least one variant to continue." if total else
            "Load variants on Home to get started."
        )
        self._export_btn.setEnabled(selected > 0 and not self._running)

    def _fill_master_information(self) -> None:
        selected = self._checklist.selected_variants()
        variants = selected or self._variants
        production_selection = tuple(
            (variant["part_number"], variant.get("project"), variant.get("event_name"))
            for variant in selected
        )
        refresh_production = self._master_reload or production_selection != self._production_selection
        self._production_selection = production_selection
        candidates: dict[str, set[str]] = {
            "project_release": set(),
            "production_project": set(),
            "ecu_type": set(),
        }
        for variant in variants:
            project = str(variant.get("project") or "").strip()
            phase = master_phase(variant)
            ecu_type = str(
                variant.get("form_b", {}).get("AP") or variant.get("ecu_type") or ""
            ).strip()
            candidates["project_release"].add(
                " ".join(part for part in (project, self._project_suffix) if part) if project else ""
            )
            if selected:
                candidates["production_project"].add(
                    f"{project} {phase}" if project and phase else ""
                )
            candidates["ecu_type"].add(ecu_type)
        self._production_warning.setVisible(len(candidates["production_project"]) > 1)
        for key, options in candidates.items():
            value = next(iter(options)) if len(options) == 1 else ""
            field = self._form_fields[key]
            if key == "production_project":
                if refresh_production:
                    field.setText(value)
                self._master_defaults[key] = value
                continue
            if (
                value and (self._master_reload or value != self._master_defaults.get(key))
                or not field.text().strip()
                or field.text() == self._master_defaults.get(key)
            ):
                field.setText(value)
            self._master_defaults[key] = value

    def _export(self) -> None:
        self._save_inputs()
        variants = self._checklist.selected_variants()
        if not variants:
            self._dialogs.error("Form B", "Select at least one variant.")
            return
        resolved = self._resolve_phases(variants)
        if resolved is None:
            return
        variants = resolved
        if (
            any(not master_phase(variant) for variant in variants)
            and not self._form_fields["production_project"].text().strip()
        ):
            projects = {
                f"{str(variant.get('project') or '').strip()} {form_b_phase(variant)}"
                for variant in variants
                if str(variant.get("project") or "").strip()
            }
            if len(projects) == 1 and all(variant.get("project") for variant in variants):
                self._form_fields["production_project"].setText(projects.pop())
        form_information, invalid_fields = self._collect_form_information()
        if invalid_fields:
            self._dialogs.error(
                "Form B",
                "Complete the following Form B Information fields:\n" + "\n".join(invalid_fields)
                + (
                    "\n\nEnable the corresponding Show option in Settings > Form B to edit hidden fields."
                    if any(self._field_containers[key].isHidden() and label in invalid_fields
                           for key, label in _FORM_FIELDS) else ""
                ),
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
        master_sheet_path = self._settings.load().get("master_sheet_path", "")
        self._tasks.start(
            lambda: self._service.generate(
                variants, path, window.step, form_information, master_sheet_path=master_sheet_path
            ),
            lambda result: self._finish(result, window),
            lambda error: self._fail(error, window),
        )

    def _resolve_phases(self, variants: list[dict]) -> list[dict] | None:
        resolved = []
        for variant in variants:
            if master_phase(variant):
                resolved.append(variant)
                continue
            label = (
                f"Warning: {variant.get('part_number', 'Variant')}: Master Sheet Project Purpose "
                "does not contain a valid phase/MP number.\n"
                "Enter the phase for this export (e.g. MP1). Cancel to return to Form B."
            )
            prompt = label
            while True:
                value, accepted = QInputDialog.getText(self, "Form B phase warning", prompt)
                if not accepted:
                    return None
                phase = manual_phase(value)
                if phase:
                    resolved.append({**variant, "form_b_phase": phase})
                    break
                prompt = "Warning: Invalid phase. Use MP followed by digits (e.g. MP1).\n" + label
        return resolved

    def _collect_form_information(self) -> tuple[dict[str, str | date], list[str]]:
        values: dict[str, str | date] = {}
        invalid_fields = []
        for key, label in _FORM_FIELDS:
            value = " ".join(self._form_fields[key].text().split())
            if not value:
                invalid_fields.append(label)
            elif key in _DATE_FIELDS:
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
        self._checklist.refresh_checksums()
        self._running = False
        self._checklist.setEnabled(True)
        self._export_btn.setText("Export Form B")
        self._update_selection(len(self._checklist.selected_variants()), self._checklist.variant_count)
        _logger.info("Exported Form B workbook: %s", path)
        window.succeed(f"Form B workbook saved to {path}.")

    def _fail(self, error: str, window) -> None:
        self._checklist.refresh_checksums()
        self._running = False
        self._checklist.setEnabled(True)
        self._export_btn.setText("Export Form B")
        self._update_selection(len(self._checklist.selected_variants()), self._checklist.variant_count)
        _logger.error("Form B export failed: %s", error)
        window.fail(error)

    def shutdown(self) -> None:
        self._service.shutdown()
