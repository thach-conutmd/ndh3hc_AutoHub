"""Configured .xlsx templates: path persistence, validation and missing/invalid reporting."""
from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from autohub.core.settings import SettingsStore
from autohub.core.settings_keys import DEFAULT_MASTER_SHEET_TEMPLATE_KEY, FORM_B_TEMPLATE_KEY

_logger = logging.getLogger(__name__)

LoadCheck = Callable[[str], str]  # returns a reason when the file cannot be used, "" when it can


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    settings_key: str
    label: str
    missing_message: str


MASTER_SHEET_TEMPLATE = TemplateSpec(
    name="master_sheet",
    settings_key=DEFAULT_MASTER_SHEET_TEMPLATE_KEY,
    label="Default Master Sheet Template",
    missing_message="Default Master Sheet template not found. Please select a valid template.",
)
FORM_B_TEMPLATE = TemplateSpec(
    name="form_b",
    settings_key=FORM_B_TEMPLATE_KEY,
    label="Default Form B Template",
    missing_message="Form B template is not available. Please select a valid Form B template in Settings.",
)


class TemplateManager:
    """One place for template path lookup, validation and saving.

    ``defaults`` supplies the bundled path used when nothing is configured.
    ``load_checks`` supplies the deep check (for example "opens as a workbook") keyed by spec name.
    """

    def __init__(
        self,
        settings: SettingsStore | None = None,
        *,
        defaults: Mapping[str, str] | None = None,
        load_checks: Mapping[str, LoadCheck] | None = None,
    ):
        self._settings = settings
        self._defaults = dict(defaults or {})
        self._load_checks = dict(load_checks or {})

    def configured(self, spec: TemplateSpec) -> str:
        if self._settings is None:
            return ""
        return str(self._settings.load().get(spec.settings_key, "") or "").strip()

    def path(self, spec: TemplateSpec) -> str:
        """The configured path, else the bundled default (empty when neither exists)."""
        return self.configured(spec) or self._defaults.get(spec.name, "")

    def problem(self, spec: TemplateSpec, path: str | None = None) -> str:
        """Empty when the template is usable; otherwise the spec's missing/invalid message."""
        checked = (self.path(spec) if path is None else str(path).strip())
        if not checked or Path(checked).suffix.lower() != ".xlsx" or not Path(checked).is_file():
            _logger.warning("%s template is missing or not an .xlsx file: %r", spec.label, checked)
            return spec.missing_message
        check = self._load_checks.get(spec.name)
        if check is None:
            return ""
        try:
            reason = check(checked)
        except Exception as error:
            _logger.exception("%s template could not be loaded", spec.label)
            reason = str(error) or type(error).__name__
        if reason:
            _logger.warning("%s template rejected (%s): %s", spec.label, checked, reason)
            return spec.missing_message
        return ""

    def require(self, spec: TemplateSpec) -> str:
        """The usable template path; raises ValueError with the spec's message otherwise."""
        problem = self.problem(spec)
        if problem:
            raise ValueError(problem)
        return self.path(spec)

    def save(self, spec: TemplateSpec, path: str) -> None:
        if self._settings is None:
            raise RuntimeError("No settings store is configured for templates.")
        self._settings.update(**{spec.settings_key: path})
