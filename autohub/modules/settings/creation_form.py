"""WebFlow connection and ECR settings form embedded in the Settings page."""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QFormLayout, QLineEdit,
    QListWidget, QListWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from autohub.config import LOG_DIR
from autohub.core.com import com_session
from autohub.core.settings import SettingsStore
from autohub.core.settings_keys import (
    DEFAULT_WEBFLOW_MAX_ATTEMPTS, RECORD_PAGES_KEY, WEBFLOW_MAX_ATTEMPTS_KEY, WEBFLOW_RETRY_ENABLED_KEY,
)
from autohub.modules.creation.service import WebFlowConfig

_DEFAULTS = {
    "webflow_base_url": "https://rb-pde-int.bosch.com:8881/app/dashboard",
    "tool_version": "PD W0002 (Productive)",
    "routing": "Honda_MG1CS022",
}
_logger = logging.getLogger(__name__)

CHANGE_REASON_OPTIONS = (
    "Correction of a situation (e.g. out of audits, legal requirements, specification)",
    "Customer requirement (Target: Customer covers costs)",
    "New supplier / increase of capacity / relocation / standards / others",
    "Q-Problem (in the plant, at supplier or customer site)",
)


def _trace_dir() -> str:
    return str(LOG_DIR / "webflow_trace" / datetime.now().strftime("%Y%m%d_%H%M%S"))


def _query_active_directory(username: str, domain: str) -> tuple[str, str] | None:
    """Return the directory display name and department for the current domain account."""
    labels = domain.rstrip(".").split(".")
    if not labels or any(
        not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
        for label in labels
    ):
        raise ValueError("USERDNSDOMAIN must be a valid DNS domain name.")
    base_dn = ",".join(f"DC={label}" for label in labels)
    escaped_username = (
        username.replace("\\", r"\5c")
        .replace("*", r"\2a")
        .replace("(", r"\28")
        .replace(")", r"\29")
        .replace("\0", r"\00")
    )
    ldap_filter = f"(&(objectCategory=person)(objectClass=user)(sAMAccountName={escaped_username}))"

    import win32com.client

    with com_session():
        connection = win32com.client.Dispatch("ADODB.Connection")
        recordset = None
        try:
            connection.Provider = "ADsDSOObject"
            connection.Open("Active Directory Provider")
            command = win32com.client.Dispatch("ADODB.Command")
            command.ActiveConnection = connection
            command.CommandText = (
                f"<LDAP://{base_dn}>;{ldap_filter};displayName,department,cn;subtree"
            )
            result = command.Execute()
            recordset = result[0] if isinstance(result, tuple) else result
            if recordset.EOF:
                return None
            fields = recordset.Fields
            display_name = fields.Item("displayName").Value or fields.Item("cn").Value or ""
            department = fields.Item("department").Value or ""
            return str(display_name).strip(), str(department).strip()
        finally:
            try:
                if recordset is not None:
                    recordset.Close()
            finally:
                connection.Close()


def _change_engineer_from_environment(fallback: str) -> str:
    username = os.environ.get("USERNAME", "").strip()
    domain = os.environ.get("USERDNSDOMAIN", "").strip()
    if not username or not domain:
        return fallback
    try:
        profile = _query_active_directory(username, domain)
    except Exception:
        _logger.warning("Could not load Change engineer details from Active Directory.", exc_info=True)
        return fallback
    if profile is None or not profile[0]:
        _logger.warning("Active Directory did not return a full name for USERNAME=%s.", username)
        return fallback
    full_name, department = profile
    if not department or full_name.casefold().endswith(f"({department})".casefold()):
        return full_name
    return f"{full_name} ({department})"


def load_config(settings: SettingsStore) -> WebFlowConfig:
    saved = settings.load()
    return WebFlowConfig(
        driver_path="",
        base_url=str(saved.get("webflow_base_url", _DEFAULTS["webflow_base_url"])).strip(),
        tool_version=str(saved.get("tool_version", _DEFAULTS["tool_version"])).strip(),
        routing=str(saved.get("routing", _DEFAULTS["routing"])).strip(),
        trace_dir=_trace_dir() if saved.get(RECORD_PAGES_KEY, True) else "",
        change_engineer=_change_engineer_from_environment(
            str(saved.get("change_engineer", "")).strip()
        ),
        cost_allocation=str(saved.get("cost_allocation", "")).strip(),
        change_reason=str(saved.get("change_reason", "")).strip(),
        max_attempts=saved.get(WEBFLOW_MAX_ATTEMPTS_KEY, DEFAULT_WEBFLOW_MAX_ATTEMPTS),
        retry_enabled=saved.get(WEBFLOW_RETRY_ENABLED_KEY, True),
    )


class CreationSettingsForm(QWidget):
    def __init__(self, config: WebFlowConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self._base_url = QLineEdit(config.base_url)
        self._tool_version = QLineEdit(config.tool_version)
        self._routing = QLineEdit(config.routing)
        self._change_engineer = QLineEdit(config.change_engineer)
        self._change_engineer.setToolTip(
            "Automatically loaded from the current Windows Active Directory profile when available."
        )
        self._cost_allocation = QLineEdit(config.cost_allocation)
        self._reason_popup = QDialog(self, Qt.Popup)
        self._reason_search = QLineEdit()
        self._reason_search.setPlaceholderText("Search Change Reason")
        self._reason_search.setClearButtonEnabled(True)
        self._reason_all = QCheckBox("Select all")
        self._change_reason = QListWidget()
        self._change_reason.setSelectionMode(QAbstractItemView.NoSelection)
        selected = {
            value.strip().casefold(): value.strip()
            for value in config.change_reason.replace("\n", "|").split("|") if value.strip()
        }
        known = {value.casefold() for value in CHANGE_REASON_OPTIONS}
        previous = [value for key, value in selected.items() if key not in known]
        for value in (*CHANGE_REASON_OPTIONS, *previous):
            item = QListWidgetItem(value)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if value.casefold() in selected else Qt.Unchecked)
            if value in previous:
                item.setToolTip("Previously saved value; not one of the recorded WebFlow options.")
            self._change_reason.addItem(item)
        self._change_reason.setMinimumHeight(110)
        self._change_reason.setMinimumWidth(
            self._change_reason.sizeHintForColumn(0) + 2 * self._change_reason.frameWidth() + 16
        )
        self._change_reason.setFixedHeight(
            sum(self._change_reason.sizeHintForRow(index) for index in range(self._change_reason.count()))
            + 2 * self._change_reason.frameWidth()
        )
        popup_layout = QVBoxLayout(self._reason_popup)
        popup_layout.addWidget(self._reason_search)
        popup_layout.addWidget(self._reason_all)
        popup_layout.addWidget(self._change_reason)
        self._reason_button = QToolButton()
        self._reason_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._reason_button.setArrowType(Qt.DownArrow)
        self._reason_button.setMinimumWidth(self._change_reason.minimumWidth())
        self._reason_button.clicked.connect(self._show_reasons)
        self._reason_search.textChanged.connect(self._filter_reasons)
        self._reason_all.clicked.connect(self._select_all_reasons)
        self._change_reason.itemChanged.connect(self._update_reason_summary)
        self._update_reason_summary()
        for field in (
            self._base_url, self._tool_version, self._routing,
            self._change_engineer, self._cost_allocation,
        ):
            field.setMinimumWidth(field.fontMetrics().horizontalAdvance(field.text()) + 24)

        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(12)
        form.addRow("Base URL:", self._base_url)
        form.addRow("Tool version:", self._tool_version)
        form.addRow("Routing:", self._routing)
        form.addRow("Change engineer:", self._change_engineer)
        form.addRow("Cost allocation:", self._cost_allocation)
        form.addRow("Change Reason:", self._reason_button)

    def restore(self, values: dict) -> None:
        for key, field in (
            ("webflow_base_url", self._base_url), ("tool_version", self._tool_version),
            ("routing", self._routing), ("change_engineer", self._change_engineer),
            ("cost_allocation", self._cost_allocation),
        ):
            field.setText(values[key])
        selected = {value.casefold() for value in values["change_reason"].split("|")}
        for index in range(self._change_reason.count()):
            item = self._change_reason.item(index)
            item.setCheckState(Qt.Checked if item.text().casefold() in selected else Qt.Unchecked)

    def _show_reasons(self) -> None:
        self._reason_search.clear()
        self._reason_popup.adjustSize()
        self._reason_popup.move(self._reason_button.mapToGlobal(self._reason_button.rect().bottomLeft()))
        self._reason_popup.show()
        self._reason_search.setFocus()

    def _filter_reasons(self, text: str) -> None:
        for index in range(self._change_reason.count()):
            item = self._change_reason.item(index)
            item.setHidden(text.casefold() not in item.text().casefold())

    def _select_all_reasons(self, checked: bool) -> None:
        for index in range(self._change_reason.count()):
            item = self._change_reason.item(index)
            if not item.isHidden():
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def _update_reason_summary(self) -> None:
        selected = [
            self._change_reason.item(index).text()
            for index in range(self._change_reason.count())
            if self._change_reason.item(index).checkState() == Qt.Checked
        ]
        summary = "; ".join(selected) or "---"
        display = selected[0] if selected else "---"
        if len(selected) > 1:
            display += f" (+{len(selected) - 1})"
        self._reason_button.setText(display)
        self._reason_button.setToolTip(summary)
        blocked = self._reason_all.blockSignals(True)
        self._reason_all.setChecked(len(selected) == self._change_reason.count())
        self._reason_all.blockSignals(blocked)

    def values(self) -> dict:
        return {
            "webflow_base_url": self._base_url.text().strip(),
            "tool_version": self._tool_version.text().strip(),
            "routing": self._routing.text().strip(),
            "change_engineer": self._change_engineer.text().strip(),
            "cost_allocation": self._cost_allocation.text().strip(),
            "change_reason": "|".join(
                self._change_reason.item(index).text()
                for index in range(self._change_reason.count())
                if self._change_reason.item(index).checkState() == Qt.Checked
            ),
        }
