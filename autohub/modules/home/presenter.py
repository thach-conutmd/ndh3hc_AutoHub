"""Home page workflows (New variant / Load / Update / Clear); talks to a view and dialogs, never to widgets."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Protocol

from autohub.core.dialogs import Dialogs
from autohub.core.a2l_hex import DEFAULT_COMP_ID_SYMBOL
from autohub.core.file_fields import FileField
from autohub.core.progress import ProgressCallback, ProgressWindow, no_progress
from autohub.core.settings import SettingsStore
from autohub.core.templates import MASTER_SHEET_TEMPLATE, TemplateManager
from autohub.core.webflow_defaults import new_variant_defaults
from autohub.core.settings_keys import (
    A2L_COMP_ID_SYMBOL_KEY,
    CALIBRATION_FOLDER_PATH_KEY,
    LATEST_COUNT_CHOICES,
    LATEST_COUNT_KEY,
    normalize_latest_count,
)
from autohub.core.variant_schema import VARIANT_FIELD_LABELS
from autohub.modules.home.service import NewVariantResult, VariantService

_logger = logging.getLogger(__name__)

MASTER_SHEET = "Master Sheet"
NEW_VARIANT_TEXT = "New variants"
UPDATE_TEXT = "Update Master Sheet"
LOAD_TEXT = "Load variants"
NEW_VARIANT_TIP = (
    "Create new variants by reading ECU Info Sheet CR and System Matrix CR. "
    "Optionally select a folder containing one A2L file and one calibration HEX file."
)

# Field label -> settings.json key. Only the Master Sheet is remembered; the New variant source files are not.
SETTINGS_KEYS = {"Master Sheet": "master_sheet_path"}
_EXCEL_FILTER = "Excel Files (*.xlsx)"
_HW_INFO_FILTER = "HW info (*.xlsx *.eml *.msg);;All files (*.*)"
_KICK_OFF_FILTER = "Kick Off Meeting (*.pptx)"

_SOURCE_FIELDS = (
    FileField("ECU Info Sheet", _EXCEL_FILTER),
    FileField("System Matrix", _EXCEL_FILTER),
    FileField("HW Info", _HW_INFO_FILTER, required=False, hint="Bosch HW / B-number (.xlsx, .eml or .msg)"),
    FileField("Kick Off", _KICK_OFF_FILTER, required=False, hint="Kick Off Meeting (.pptx)"),
    FileField(
        "Calibration folder", "", required=False,
        hint="Folder containing one .a2l file and one .hex file", directory=True,
    ),
)


class HomeView(Protocol):
    """What the presenter needs from the page; implemented by HomeWidget and by test fakes."""

    def show_file_name(self, field_name: str, path: str) -> None: ...

    def show_rows(self, rows: list[dict]) -> None: ...

    def read_rows(self) -> list[dict]: ...

    def row_count(self) -> int: ...

    def clear_rows(self) -> None: ...

    def selected_rows(self) -> list[int]: ...

    def remove_rows(self, rows: list[int]) -> None: ...

    def set_new_variant_state(self, enabled: bool, text: str) -> None: ...

    def set_load_state(self, enabled: bool, text: str) -> None: ...

    def set_update_state(self, enabled: bool, text: str) -> None: ...

    def set_clear_enabled(self, enabled: bool) -> None: ...

    def set_delete_enabled(self, enabled: bool) -> None: ...

    def publish_variants(self, variants: list[dict]) -> None: ...

    def set_workspace_enabled(self, enabled: bool, busy: bool = False) -> None: ...


#: Runs `func` off the UI thread and reports back: start(func, on_ok, on_error).
TaskStarter = Callable[[Callable, Callable, Callable], None]


class HomePresenter:
    def __init__(
        self,
        view: HomeView,
        service: VariantService,
        settings: SettingsStore,
        dialogs: Dialogs,
        start_task: TaskStarter,
        templates: TemplateManager | None = None,
    ):
        self._view = view
        self._service = service
        self._settings = settings
        self._dialogs = dialogs
        self._start_task = start_task
        self._templates = templates or TemplateManager(
            settings, load_checks={MASTER_SHEET_TEMPLATE.name: service.master_sheet_problem},
        )
        self._paths: dict[str, str] = {}
        self._edited = False  # the table holds changes that are not in the Master Sheet yet
        self._loaded_rows: list[dict] | None = None  # every variant of the last Load, before the "latest" limit
        self._original_rows: dict[int, dict[str, str]] = {}
        self._deleted_rows: list[int] = []  # Master Sheet rows of variants deleted here, removed on Update
        self._deleted_parts: dict[int, str] = {}  # the same variants' part numbers, by sheet row
        self._master_valid = False
        self._busy = False
        self._operation = ""
        self._revision = 0
        self._refresh_actions()

    # -- File paths ------------------------------------------------------------------

    def restore_saved_paths(self) -> None:
        saved = self._settings.load()
        for field_name, key in SETTINGS_KEYS.items():
            path = saved.get(key, "")
            if self._paths.get(field_name) and self._paths[field_name] != path:
                self._invalidate_master()
            if path:
                problem = self._master_problem(path)
                if problem:
                    _logger.error("Master Sheet not restored: %s", problem)
                    self._invalidate_master()
                else:
                    self._activate_master(path)

    def _refresh_actions(self) -> None:
        ready = self._master_valid and not self._busy
        # Without a loaded Master Sheet, New variant still works when a default template is configured.
        can_create = (self._master_valid or bool(self._templates.configured(MASTER_SHEET_TEMPLATE))) and not self._busy
        self._view.set_new_variant_state(
            can_create, "Creating..." if self._busy and self._operation == NEW_VARIANT_TEXT else NEW_VARIANT_TEXT,
        )
        self._view.set_load_state(ready, "Loading..." if self._busy and self._operation == LOAD_TEXT else LOAD_TEXT)
        self._view.set_update_state(
            ready and self._edited, "Updating..." if self._busy and self._operation == UPDATE_TEXT else UPDATE_TEXT,
        )
        self._view.set_clear_enabled(ready and self._view.row_count() > 0)
        self._view.set_delete_enabled(ready and bool(self._view.selected_rows()))
        self._view.set_workspace_enabled(ready, self._busy)

    def _master_problem(self, path: str) -> str:
        if not path or not Path(path).is_file():
            return "Select a valid Master Sheet file."
        try:
            return self._service.master_sheet_problem(path)
        except Exception as error:
            _logger.exception("Master Sheet validation failed")
            return f"Could not validate the Master Sheet: {error}"

    def _active_master_problem(self) -> str:
        path = self._paths.get(MASTER_SHEET, "")
        if not self._master_valid:
            return "Select a valid Master Sheet file."
        if self._settings.load().get("master_sheet_path", "") != path:
            return "The active Master Sheet changed. Load and validate it again."
        return self._master_problem(path)

    def _activate_master(self, path: str) -> None:
        self._revision += 1
        self._master_valid = True
        self._set_path(MASTER_SHEET, path)
        self._settings.update(master_sheet_path=path)
        self._refresh_actions()

    def _invalidate_master(self) -> None:
        associated = bool(self._paths.get(MASTER_SHEET)) or self._view.row_count() > 0
        self._revision += 1
        self._master_valid = False
        self._set_path(MASTER_SHEET, "")
        self._settings.update(master_sheet_path="")
        self._clear_rows()
        if associated:
            self._view.publish_variants([])
        self._refresh_actions()

    def revalidate_master_sheet(self, title: str = f"Load {MASTER_SHEET}") -> bool:
        """Used when the active workbook changes or disappears from disk."""
        if not self._master_valid:
            return False
        return self._valid_master_sheet(title) is not None

    def _run_task(self, func, on_ok, on_error, window: ProgressWindow, operation: str, check=None) -> None:
        """Only the still-valid workspace may consume a background operation's result.

        `check` replaces the active Master Sheet check (used when the work starts from the default template)."""
        if check is None:
            problem = self._active_master_problem()
            if problem:
                self._invalidate_master()
                window.fail(problem)
                return
        else:
            problem = check()
            if problem:
                window.fail(problem)
                return
        revision = self._revision
        self._busy = True
        self._operation = operation
        self._refresh_actions()

        def finish(result=None, error: str = "") -> None:
            self._busy = False
            if revision != self._revision:
                self._refresh_actions()
                window.fail("The active Master Sheet changed. Load and validate it again.")
                return
            problem = self._active_master_problem() if check is None else ""
            if problem:
                self._invalidate_master()
                error = problem
            if error:
                on_error(error)
            else:
                on_ok(result)
            self._refresh_actions()

        self._start_task(func, lambda result: finish(result), lambda error: finish(error=error))

    def latest_count(self) -> int:
        return normalize_latest_count(self._settings.load().get(LATEST_COUNT_KEY, 0))

    def set_latest_count(self, count: int) -> None:
        """Saves the limit and, when variants were loaded, shows the table again with the new limit."""
        count = normalize_latest_count(count)
        changed = count != self.latest_count()
        self._settings.update(**{LATEST_COUNT_KEY: count})
        if changed:
            self.refresh_latest_rows()

    def refresh_new_variant_state(self) -> None:
        """Called when the default template setting changes."""
        self._refresh_actions()

    def refresh_latest_rows(self) -> None:
        """Applies the saved display limit without silently discarding table edits."""
        if self._loaded_rows is None:
            return
        if self._busy or self._valid_master_sheet("Latest variants") is None:
            return
        if self._edited and not self._dialogs.confirm(
            "Latest variants",
            "The table has changes that are not in the Master Sheet yet. Showing the new number of latest "
            "variants discards them.\n\nContinue?",
        ):
            return
        self._show_rows(latest_rows(self._loaded_rows, self.latest_count()))

    def browse_master_sheet(self) -> None:
        """Load Master Sheet: picks a file, clears the table and loads that sheet's variants."""
        if self._busy:
            return
        title = f"Load {MASTER_SHEET}"
        path = self._dialogs.pick_file("Select file", _EXCEL_FILTER)
        if not path:
            return
        if self._edited and not self._dialogs.confirm(
            title,
            "The table has changes that are not in the Master Sheet yet. Loading another Master Sheet "
            "discards them.\n\nContinue?",
        ):
            return
        self._invalidate_master()
        problem = self._master_problem(path)
        if problem:
            _logger.error("Master Sheet not loaded: %s", problem)
            self._dialogs.error(title, problem)
            return
        self._activate_master(path)
        _logger.info("%s file selected: %s", MASTER_SHEET, path)
        self._start_load(path, keep_rows=False)

    def _set_path(self, field_name: str, path: str) -> None:
        self._paths[field_name] = path
        self._view.show_file_name(field_name, path)

    def _valid_master_sheet(self, title: str) -> str | None:
        problem = self._active_master_problem()
        if problem:
            self._invalidate_master()
            self._dialogs.error(title, problem)
            return None
        return self._paths[MASTER_SHEET]

    # -- Table -----------------------------------------------------------------------

    def set_webflow_links(self, links: dict[str, str]) -> None:
        if not self._master_valid or self._valid_master_sheet("Update WebFlow links") is None:
            return
        if self._loaded_rows is not None:
            for row in self._loaded_rows:
                if row.get("J") in links:
                    row["_webflow_link"] = links[row["J"]]

    def set_webflow_numbers(self, numbers: dict[str, dict[str, str]], persisted: bool = True) -> None:
        if not self._master_valid or self._valid_master_sheet("Update WebFlow numbers") is None:
            return
        if self._loaded_rows is not None:
            for row in self._loaded_rows:
                row.update(numbers.get(row.get("J"), {}))
        # Treat imported cells as the baseline without clearing unrelated edits.
        for row in self._view.read_rows():
            original = self._original_rows.get(row.get("_row"))
            if original is not None and persisted:
                original.update(numbers.get(row.get("J"), {}))
        if not persisted and numbers:
            self.on_table_edited()

    def _show_rows(self, rows: list[dict]) -> None:
        self._view.show_rows(rows)
        self._original_rows = {
            int(row["_row"]): _row_values(row)
            for row in rows
            if row.get("_row") is not None
        }
        self._edited = False
        self._deleted_rows = []
        self._deleted_parts = {}
        self._view.set_update_state(False, UPDATE_TEXT)
        self._view.set_clear_enabled(self._view.row_count() > 0)
        self.on_selection_changed()

    def _ask_keep_rows(self, title: str) -> bool | None:
        """True to keep the rows already in the table, False to replace them, None to cancel the action.

        Nothing is removed here: replaced rows only go once the new ones arrive, so a cancelled or failed
        action never loses the table."""
        count = self._view.row_count()
        if count == 0:
            return False
        answer = self._dialogs.ask_yes_no_cancel(
            title,
            f"The table still contains {count} variant{'s' if count != 1 else ''}.\n\n"
            "Clear: replace them with the new ones.\nKeep: leave them and add the new ones below.",
            yes_text="Clear",
            no_text="Keep",
        )
        return None if answer is None else not answer

    def _show_added_rows(self, rows: list[dict], keep: bool) -> int:
        """Shows `rows`; when `keep`, after the rows already in the table, skipping ones it already holds.

        Returns how many of `rows` ended up in the table."""
        if not keep:
            self._show_rows(rows)
            return len(rows)
        existing = self._view.read_rows()
        unsaved, deleted, deleted_parts = self._edited, self._deleted_rows, self._deleted_parts
        original_rows = dict(self._original_rows)
        known = {_row_identity(row) for row in existing}
        added = [row for row in rows if _row_identity(row) not in known]
        self._show_rows(existing + added)
        self._original_rows.update(original_rows)
        self._original_rows.update(
            {
                int(row["_row"]): _row_values(row)
                for row in added
                if row.get("_row") is not None
            }
        )
        self._deleted_rows, self._deleted_parts = deleted, deleted_parts  # kept rows keep their pending deletions too
        if unsaved or deleted or any(row.get("_row") is None for row in existing + added):
            self._view.set_update_state(True, UPDATE_TEXT)
            self._edited = True
        return len(added)

    def on_table_edited(self) -> None:
        if self._busy or self._valid_master_sheet("Edit variants") is None:
            return
        self._edited = True
        self._view.set_update_state(True, UPDATE_TEXT)

    def clear_table(self) -> None:
        """The Clear button: asks for confirmation first when the table holds variants."""
        if self._busy or self._valid_master_sheet("Clear table") is None:
            return
        count = self._view.row_count()
        if count and not self._dialogs.confirm(
            "Clear table", f"Are you sure you want to clear the table ({count} variant{'s' if count != 1 else ''})?"
        ):
            return
        self._clear_rows()

    def on_selection_changed(self) -> None:
        """Delete selected is only active while at least one row is selected."""
        self._view.set_delete_enabled(self._master_valid and not self._busy and bool(self._view.selected_rows()))

    def delete_selected(self) -> None:
        """Removes the selected variants from the table; the Master Sheet follows on Update."""
        if self._busy or self._valid_master_sheet("Delete variants") is None:
            return
        selected = self._view.selected_rows()
        if not selected:
            self._dialogs.info("Delete variants", "Select one or more variants (rows) to delete.")
            return
        count = len(selected)
        plural = "s" if count != 1 else ""
        if not self._dialogs.confirm(
            "Delete variants",
            f"Delete {count} selected variant{plural}?\n\n"
            f"They are removed from the Master Sheet when you click '{UPDATE_TEXT}'.",
        ):
            return
        rows = self._view.read_rows()
        self._deleted_rows += [rows[i]["_row"] for i in selected if rows[i].get("_row")]
        self._deleted_parts.update({rows[i]["_row"]: rows[i].get("J", "") for i in selected if rows[i].get("_row")})
        self._view.remove_rows(selected)
        _logger.info("Deleted %d variant(s) from the table (%d pending in the sheet)", count, len(self._deleted_rows))
        self._view.set_clear_enabled(self._view.row_count() > 0)
        self.on_selection_changed()
        self.on_table_edited()

    def _clear_rows(self) -> None:
        self._loaded_rows = None
        self._edited = False
        self._original_rows = {}
        self._deleted_rows = []
        self._deleted_parts = {}
        self._view.clear_rows()
        self._view.set_update_state(False, UPDATE_TEXT)
        self._view.set_clear_enabled(False)
        self.on_selection_changed()
        _logger.info("Variant table cleared")

    # -- New variant (compute only, nothing written yet) -------------------------------

    def new_variant(self) -> None:
        if self._busy:
            return
        if self._master_valid:
            master_sheet_path = self._valid_master_sheet("AutoHub")
            if master_sheet_path is None:
                return
            template_check = None
        else:
            # A loaded Master Sheet always wins; without one, the configured template is copied.
            master_sheet_path = self._templates.path(MASTER_SHEET_TEMPLATE)
            template_check = lambda: self._templates.problem(MASTER_SHEET_TEMPLATE)  # noqa: E731
        keep_rows = self._ask_keep_rows(NEW_VARIANT_TEXT)
        if keep_rows is None:
            return
        sources = self._ask_sources()
        if sources is None:
            return
        ecu_info_path, system_matrix_path, hw_info_path, kick_off_path, hex_folder_path = (
            sources[field.name] for field in _SOURCE_FIELDS
        )
        a2l_symbol_name = str(
            self._settings.load().get(A2L_COMP_ID_SYMBOL_KEY, DEFAULT_COMP_ID_SYMBOL)
        ).strip()
        if not a2l_symbol_name:
            a2l_symbol_name = DEFAULT_COMP_ID_SYMBOL
        variant_defaults = new_variant_defaults(self._settings.load())

        paths = (master_sheet_path, ecu_info_path, system_matrix_path, hw_info_path, kick_off_path)
        _logger.info("New variant clicked (%s)", paths)
        self._view.set_new_variant_state(False, "Creating...")
        self._view.set_update_state(False, UPDATE_TEXT)
        window = self._dialogs.open_progress(NEW_VARIANT_TEXT)
        self._run_task(
            lambda: self._service.compute_new_variants(
                *paths,
                progress=window.step,
                hex_folder_path=hex_folder_path,
                a2l_symbol_name=a2l_symbol_name,
                variant_defaults=variant_defaults,
                copy_template=template_check is not None,
            ),
            lambda result: self._finish_new_variant(result, window, keep_rows),
            lambda error: self._fail_new_variant(error, window),
            window, NEW_VARIANT_TEXT, check=template_check,
        )

    def _ask_sources(self) -> dict[str, str] | None:
        """The source file paths from one dialog (always empty at first, nothing is remembered), or None when cancelled."""
        chosen = self._dialogs.ask_files(NEW_VARIANT_TEXT, _SOURCE_FIELDS, {})
        if chosen is None:
            return None
        for field in _SOURCE_FIELDS:
            if chosen.get(field.name):
                _logger.info("%s file selected: %s", field.name, chosen[field.name])
        calibration_folder = chosen.get("Calibration folder", "")
        if calibration_folder:
            self._settings.update(**{CALIBRATION_FOLDER_PATH_KEY: calibration_folder})
        return {field.name: chosen.get(field.name, "") for field in _SOURCE_FIELDS}

    def _finish_new_variant(self, result: NewVariantResult, window: ProgressWindow, keep_rows: bool) -> None:
        self._view.set_new_variant_state(True, NEW_VARIANT_TEXT)
        if result.created_master_sheet:
            self._activate_master(result.created_master_sheet)
        count = self._show_added_rows(result.variants, keep_rows)
        if count > 0:
            self._view.set_update_state(True, UPDATE_TEXT)  # new rows can be written as they are
            self._edited = True
        _logger.info("Found %d new variant(s) (not yet written)", count)
        if count == 0:
            message = "No new variants. Existing variants were skipped."
        else:
            message = (
                f"Found {count} new variant{'s' if count != 1 else ''}. Review/edit below, "
                "then click Update to save to the Master Sheet."
            )
        if result.warnings:
            message += "\n\nCalibration ID warning(s):\n- " + "\n- ".join(result.warnings)
        if result.created_master_sheet:
            message = f"Created {Path(result.created_master_sheet).name} from the default template.\n\n" + message
        window.succeed(message)

    def _fail_new_variant(self, error: str, window: ProgressWindow) -> None:
        self._view.set_new_variant_state(True, NEW_VARIANT_TEXT)
        self._view.set_update_state(self._edited, UPDATE_TEXT)  # the table is untouched
        _logger.error("New variant failed: %s", error)
        window.fail(error)

    # -- Update Master Sheet (insert new rows / update existing rows) ------------------

    def update_master_sheet(self) -> None:
        if self._busy:
            return
        if self._view.row_count() == 0 and not self._deleted_rows:
            return
        master_sheet_path = self._valid_master_sheet("Update variants")
        if master_sheet_path is None:
            return

        deleted = list(self._deleted_rows)
        parts = [self._deleted_parts.get(row, "") for row in deleted]
        variants = self._view.read_rows()
        variants_to_save = [
            row
            for row in variants
            if row.get("_row") is None
            or (
                int(row["_row"]) in self._original_rows
                and _row_values(row) != self._original_rows[int(row["_row"])]
            )
        ]
        if not variants_to_save and not deleted:
            self._dialogs.info(
                "Update variants",
                "No changed variants to update.",
            )
            return

        changed_rows = [
            f"- {_part_number_value(row.get('J')) or '(blank)'}"
            for row in variants_to_save
            if row.get("_row") is not None
        ]
        new_parts = [
            f"- {_part_number_value(row.get('J')) or '(blank)'}"
            for row in variants_to_save
            if row.get("_row") is None
        ]
        text = (
            f"Are you sure you want to update the Master Sheet with {len(variants_to_save)} variant(s)?"
            "\n\nOnly changed existing rows will be updated."
        )
        if changed_rows:
            text += "\n\nChanged variants:\n" + "\n".join(changed_rows)
        if new_parts:
            text += "\n\nNew variants to add:\n" + "\n".join(new_parts)
        if deleted:
            text += f"\n\n{len(deleted)} variant(s) will be deleted from the Master Sheet."
        if not self._dialogs.confirm("Update variants", text):
            return
        _logger.info("Update variants clicked (%d variant(s))", len(variants_to_save))
        self._view.set_update_state(False, "Updating...")
        window = self._dialogs.open_progress("Update variants")
        self._run_task(
            lambda: self._service.save_variants(
                master_sheet_path, variants_to_save, window.step, deleted, parts
            ),
            lambda result: self._finish_update(result, window, deleted),
            lambda error: self._fail_update(error, window),
            window, UPDATE_TEXT,
        )

    def _finish_update(self, result, window: ProgressWindow, deleted: list[int]) -> None:
        saved, rows, available = result
        count = len(saved)
        _logger.info("Updated %d variant(s) in the Master Sheet", count)
        self._loaded_rows = rows
        self._show_rows(latest_rows(rows, self.latest_count()))
        message = f"Updated {count} variant{'s' if count != 1 else ''} in the Master Sheet."
        if deleted:
            message += f" Deleted {len(deleted)}."
        skipped = sorted({key for item in saved if isinstance(item, dict) for key in item.get("Unmapped", [])})
        if skipped:
            labels = ", ".join(VARIANT_FIELD_LABELS.get(key, key) for key in skipped)
            message += f"\nNot stored in this Master Sheet layout: {labels}."
        window.succeed(message)
        self._view.publish_variants(available)

    def _fail_update(self, error: str, window: ProgressWindow) -> None:
        self._view.set_update_state(True, UPDATE_TEXT)
        _logger.error("Update variants failed: %s", error)
        window.fail(error)

    # -- Load variants -----------------------------------------------------------------

    def load_variants(self) -> None:
        if self._busy:
            return
        master_sheet_path = self._valid_master_sheet(LOAD_TEXT)
        if master_sheet_path is None:
            return
        keep_rows = self._ask_keep_rows(LOAD_TEXT)
        if keep_rows is None:
            return
        _logger.info("Load variants clicked (master=%s)", master_sheet_path)
        self._start_load(master_sheet_path, keep_rows)

    def reload_variants(self) -> None:
        """Reloads the Master Sheet without asking, keeping the rows (and edits) already in the table."""
        if self._busy:
            return
        master_sheet_path = self._valid_master_sheet(LOAD_TEXT)
        if master_sheet_path is not None:
            self._start_load(master_sheet_path, True)

    def auto_load_variants(self, progress: ProgressCallback = no_progress) -> None:
        """At startup, loads the remembered Master Sheet when it exists and has a supported layout.

        Runs in the calling thread and reports through ``progress`` (the startup dialog), so no
        progress window opens; a failure is only logged.
        """
        master_sheet_path = self._paths.get(MASTER_SHEET, "")
        if not self._master_valid or self._busy or self._view.row_count():
            return
        problem = self._active_master_problem()
        if problem:
            _logger.info("Variants not loaded at startup: %s", problem)
            self._invalidate_master()
            return
        _logger.info("Loading variants at startup (master=%s)", master_sheet_path)
        revision = self._revision
        try:
            result = self._service.load_variants(master_sheet_path, progress)
        except Exception as error:
            _logger.error("Variants not loaded at startup: %s", error)
            if revision == self._revision and self._active_master_problem():
                self._invalidate_master()
            return
        if revision != self._revision:
            _logger.error("Variants not loaded at startup: the active Master Sheet changed.")
            return
        problem = self._active_master_problem()
        if problem:
            _logger.error("Variants not loaded at startup: %s", problem)
            self._invalidate_master()
            return
        count, total = self._apply_load(result, keep_rows=False)
        progress(f"Loaded {count} variant{'s' if count != 1 else ''}.")

    def _start_load(self, master_sheet_path: str, keep_rows: bool) -> None:
        self._view.set_load_state(False, "Loading...")
        window = self._dialogs.open_progress(LOAD_TEXT)
        self._run_task(
            lambda: self._service.load_variants(master_sheet_path, window.step),
            lambda result: self._finish_load(result, window, keep_rows),
            lambda error: self._fail_load(error, window),
            window, LOAD_TEXT,
        )

    def _finish_load(self, result, window: ProgressWindow, keep_rows: bool) -> None:
        self._view.set_load_state(True, LOAD_TEXT)
        count, total = self._apply_load(result, keep_rows)
        note = f" (latest {count} of {total})" if count != total else ""
        window.succeed(f"Loaded {count} variant{'s' if count != 1 else ''} from the Master Sheet{note}.")

    def _apply_load(self, result, keep_rows: bool) -> tuple[int, int]:
        rows, available = result
        self._loaded_rows = rows
        shown = latest_rows(rows, self.latest_count())
        self._show_added_rows(shown, keep_rows)
        count, total = len(shown), len(rows)
        _logger.info("Loaded %d of %d variant(s)", count, total)
        self._view.publish_variants(available)
        return count, total

    def _fail_load(self, error: str, window: ProgressWindow) -> None:
        self._view.set_load_state(True, LOAD_TEXT)
        _logger.error("Load variants failed: %s", error)
        window.fail(error)


def latest_rows(rows: list[dict], count: int) -> list[dict]:
    """The `count` newest variants (the sheet lists the oldest first); 0 keeps all of them."""
    return rows[-count:] if 0 < count < len(rows) else rows


def _row_identity(row: dict) -> tuple:
    """Sheet row number for rows from the Master Sheet, else the variant key (purpose, part number, program id)."""
    if row.get("_row") is not None:
        return ("sheet", row["_row"])
    return ("new", row.get("H"), row.get("J"), row.get("BI"))


def _part_number_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def _row_values(row: dict) -> dict[str, str]:
    return {
        key: _part_number_value(value)
        for key, value in row.items()
        if not key.startswith("_")
    }
