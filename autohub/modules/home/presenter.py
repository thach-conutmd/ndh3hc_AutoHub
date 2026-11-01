"""Home page workflows (New variant / Load / Update / Clear); talks to a view and dialogs, never to widgets."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Protocol

from autohub.core.dialogs import Dialogs
from autohub.core.file_fields import FileField
from autohub.core.progress import ProgressCallback, ProgressWindow, no_progress
from autohub.core.settings import SettingsStore
from autohub.core.settings_keys import LATEST_COUNT_CHOICES, LATEST_COUNT_KEY, normalize_latest_count
from autohub.core.variant_schema import VARIANT_FIELD_LABELS
from autohub.modules.home.service import VariantService

_logger = logging.getLogger(__name__)

MASTER_SHEET = "Master Sheet"
NEW_VARIANT_TEXT = "New variants"
UPDATE_TEXT = "Update Master Sheet"
LOAD_TEXT = "Load variants"
NEW_VARIANT_TIP = "Create new variant by reading ECU Info Sheet CR and System Matrix CR."

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
    ):
        self._view = view
        self._service = service
        self._settings = settings
        self._dialogs = dialogs
        self._start_task = start_task
        self._paths: dict[str, str] = {}
        self._edited = False  # the table holds changes that are not in the Master Sheet yet
        self._loaded_rows: list[dict] | None = None  # every variant of the last Load, before the "latest" limit
        self._original_rows: dict[int, dict[str, str]] = {}
        self._deleted_rows: list[int] = []  # Master Sheet rows of variants deleted here, removed on Update
        self._deleted_parts: dict[int, str] = {}  # the same variants' part numbers, by sheet row

    # -- File paths ------------------------------------------------------------------

    def restore_saved_paths(self) -> None:
        saved = self._settings.load()
        for field_name, key in SETTINGS_KEYS.items():
            path = saved.get(key, "")
            if path:
                self._set_path(field_name, path)

    def latest_count(self) -> int:
        return normalize_latest_count(self._settings.load().get(LATEST_COUNT_KEY, 0))

    def set_latest_count(self, count: int) -> None:
        """Saves the limit and, when variants were loaded, shows the table again with the new limit."""
        count = normalize_latest_count(count)
        changed = count != self.latest_count()
        self._settings.update(**{LATEST_COUNT_KEY: count})
        if changed:
            self.refresh_latest_rows()

    def refresh_latest_rows(self) -> None:
        """Applies the saved display limit without silently discarding table edits."""
        if self._loaded_rows is None:
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
        problem = self._service.master_sheet_problem(path)
        if problem:
            _logger.error("Master Sheet not loaded: %s", problem)
            self._dialogs.error(title, problem)
            return
        self._set_path(MASTER_SHEET, path)
        self._settings.update(**{SETTINGS_KEYS[MASTER_SHEET]: path})
        _logger.info("%s file selected: %s", MASTER_SHEET, path)
        self._clear_rows()
        self._view.publish_variants([])
        self._start_load(path, keep_rows=False)

    def _set_path(self, field_name: str, path: str) -> None:
        self._paths[field_name] = path
        self._view.show_file_name(field_name, path)

    def _valid_master_sheet(self, title: str) -> str | None:
        path = self._paths.get(MASTER_SHEET, "")
        if not Path(path).is_file():
            self._dialogs.error(title, "Select a valid Master Sheet file.")
            return None
        return path

    # -- Table -----------------------------------------------------------------------

    def set_webflow_links(self, links: dict[str, str]) -> None:
        if self._loaded_rows is not None:
            for row in self._loaded_rows:
                if row.get("J") in links:
                    row["_webflow_link"] = links[row["J"]]

    def set_webflow_numbers(self, numbers: dict[str, dict[str, str]], persisted: bool = True) -> None:
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
        self._edited = True
        self._view.set_update_state(True, UPDATE_TEXT)

    def clear_table(self) -> None:
        """The Clear button: asks for confirmation first when the table holds variants."""
        count = self._view.row_count()
        if count and not self._dialogs.confirm(
            "Clear table", f"Are you sure you want to clear the table ({count} variant{'s' if count != 1 else ''})?"
        ):
            return
        self._clear_rows()

    def on_selection_changed(self) -> None:
        """Delete selected is only active while at least one row is selected."""
        self._view.set_delete_enabled(bool(self._view.selected_rows()))

    def delete_selected(self) -> None:
        """Removes the selected variants from the table; the Master Sheet follows on Update."""
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
        keep_rows = self._ask_keep_rows(NEW_VARIANT_TEXT)
        if keep_rows is None:
            return
        master_sheet_path = self._valid_master_sheet("AutoHub")
        if master_sheet_path is None:
            return
        sources = self._ask_sources()
        if sources is None:
            return
        ecu_info_path, system_matrix_path, hw_info_path, kick_off_path = (
            sources[field.name] for field in _SOURCE_FIELDS
        )

        paths = (master_sheet_path, ecu_info_path, system_matrix_path, hw_info_path, kick_off_path)
        _logger.info("New variant clicked (%s)", paths)
        self._view.set_new_variant_state(False, "Creating...")
        self._view.set_update_state(False, UPDATE_TEXT)
        window = self._dialogs.open_progress(NEW_VARIANT_TEXT)
        self._start_task(
            lambda: self._service.compute_new_variants(*paths, progress=window.step),
            lambda new_variants: self._finish_new_variant(new_variants, window, keep_rows),
            lambda error: self._fail_new_variant(error, window),
        )

    def _ask_sources(self) -> dict[str, str] | None:
        """The source file paths from one dialog (always empty at first, nothing is remembered), or None when cancelled."""
        chosen = self._dialogs.ask_files(NEW_VARIANT_TEXT, _SOURCE_FIELDS, {})
        if chosen is None:
            return None
        for field in _SOURCE_FIELDS:
            if chosen.get(field.name):
                _logger.info("%s file selected: %s", field.name, chosen[field.name])
        return {field.name: chosen.get(field.name, "") for field in _SOURCE_FIELDS}

    def _finish_new_variant(self, new_variants: list[dict], window: ProgressWindow, keep_rows: bool) -> None:
        self._view.set_new_variant_state(True, NEW_VARIANT_TEXT)
        count = self._show_added_rows(new_variants, keep_rows)
        if count > 0:
            self._view.set_update_state(True, UPDATE_TEXT)  # new rows can be written as they are
            self._edited = True
        _logger.info("Found %d new variant(s) (not yet written)", count)
        if count == 0:
            window.succeed("No new variants. Existing variants were skipped.")
        else:
            window.succeed(
                f"Found {count} new variant{'s' if count != 1 else ''}. Review/edit below, "
                "then click Update to save to the Master Sheet.",
            )

    def _fail_new_variant(self, error: str, window: ProgressWindow) -> None:
        self._view.set_new_variant_state(True, NEW_VARIANT_TEXT)
        self._view.set_update_state(self._edited, UPDATE_TEXT)  # the table is untouched
        _logger.error("New variant failed: %s", error)
        window.fail(error)

    # -- Update Master Sheet (insert new rows / update existing rows) ------------------

    def update_master_sheet(self) -> None:
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
        self._start_task(
            lambda: self._service.save_variants(
                master_sheet_path, variants_to_save, window.step, deleted, parts
            ),
            lambda result: self._finish_update(result, window, deleted),
            lambda error: self._fail_update(error, window),
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
        keep_rows = self._ask_keep_rows(LOAD_TEXT)
        if keep_rows is None:
            return
        master_sheet_path = self._valid_master_sheet(LOAD_TEXT)
        if master_sheet_path is None:
            return
        _logger.info("Load variants clicked (master=%s)", master_sheet_path)
        self._start_load(master_sheet_path, keep_rows)

    def auto_load_variants(self, progress: ProgressCallback = no_progress) -> None:
        """At startup, loads the remembered Master Sheet when it exists and has a supported layout.

        Runs in the calling thread and reports through ``progress`` (the startup dialog), so no
        progress window opens; a failure is only logged.
        """
        master_sheet_path = self._paths.get(MASTER_SHEET, "")
        if not master_sheet_path or self._view.row_count():
            return
        problem = self._service.master_sheet_problem(master_sheet_path)
        if problem:
            _logger.info("Variants not loaded at startup: %s", problem)
            return
        _logger.info("Loading variants at startup (master=%s)", master_sheet_path)
        try:
            result = self._service.load_variants(master_sheet_path, progress)
        except Exception as error:
            _logger.error("Variants not loaded at startup: %s", error)
            return
        count, total = self._apply_load(result, keep_rows=False)
        progress(f"Loaded {count} variant{'s' if count != 1 else ''}.")

    def _start_load(self, master_sheet_path: str, keep_rows: bool) -> None:
        self._view.set_load_state(False, "Loading...")
        window = self._dialogs.open_progress(LOAD_TEXT)
        self._start_task(
            lambda: self._service.load_variants(master_sheet_path, window.step),
            lambda result: self._finish_load(result, window, keep_rows),
            lambda error: self._fail_load(error, window),
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
