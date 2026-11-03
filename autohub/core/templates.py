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
    missing_message="Form B template is not available. Please select a valid template in Settings.",
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

    def resolve(self, spec: TemplateSpec) -> str:
        """The first usable path: the configured template, then the built-in default. Empty when neither works."""
        candidates = dict.fromkeys(p for p in (self.configured(spec), self._defaults.get(spec.name, "")) if p)
        for candidate in candidates:
            if not self._check(spec, candidate):
                return candidate
        return ""

    def problem(self, spec: TemplateSpec, path: str | None = None) -> str:
        """Empty when ``path`` (or the resolved template when omitted) is usable; otherwise the spec's message."""
        if path is None:
            return "" if self.resolve(spec) else spec.missing_message
        return self._check(spec, str(path).strip())

    def _check(self, spec: TemplateSpec, checked: str) -> str:
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
        resolved = self.resolve(spec)
        if not resolved:
            raise ValueError(spec.missing_message)
        return resolved

    def seed_default(self, spec: TemplateSpec) -> None:
        """First run: configure the built-in default as the active template when nothing was configured yet."""
        if self._settings is None or spec.settings_key in self._settings.load():
            return
        default = self._defaults.get(spec.name, "")
        if default and not self._check(spec, default):
            self.save(spec, default)

    def save(self, spec: TemplateSpec, path: str) -> None:
        if self._settings is None:
            raise RuntimeError("No settings store is configured for templates.")
        self._settings.update(**{spec.settings_key: path})
