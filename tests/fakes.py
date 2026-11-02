"""Test doubles: they stand in for Excel, Selenium, Qt dialogs and the settings file."""
from __future__ import annotations

from contextlib import contextmanager

from autohub.modules.home.service import VariantService


class MemorySettings:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def load(self) -> dict:
        return dict(self.data)

    def update(self, **kwargs) -> dict:
        self.data.update(kwargs)
        return dict(self.data)


class FakeWebFlow:
    instances: list = []

    def __init__(self, driver_path="", base_url="", trace_dir=""):
        self.trace_dir = trace_dir
        self.quit_calls = 0
        FakeWebFlow.instances.append(self)

    def create_and_fill_jobs(self, variants, tool_version, routing, progress=None, state=None, checkpoint=None):
        return [{"PartNumber": v["part_number"], "JobId": "1"} for v in variants]

    def quit(self):
        self.quit_calls += 1


class FakeDocument:
    """A reader that never touches Excel."""

    def __init__(self, path="", ok=True, error="", **data):
        self.path = path
        self.ok = ok
        self.last_error = error
        self.opened = self.closed = False
        self.__dict__.update(data)

    def open(self):
        self.opened = True

    def close(self):
        self.closed = True

    def load_data(self) -> bool:
        return self.ok


class FakeMasterSheet(FakeDocument):
    def __init__(self, path="", new_rows=None, rows=None, webflow=None, **kwargs):
        super().__init__(path, **kwargs)
        self.new_rows, self.rows, self.webflow = new_rows or [], rows or [], webflow or []
        self.saved = None
        self.deleted = None
        self.compute_args = None

    def compute_new_variants(self, system_info, ecu_info, hw_info=None, kick_off=None):
        self.compute_args = (system_info, ecu_info, hw_info, kick_off)
        return self.new_rows

    def save_variant_rows(self, variants, save=True):
        self.saved = variants
        return [{"PartNumber": v.get("J")} for v in variants]

    def delete_variant_rows(self, request_rows, save=True):
        self.deleted = list(request_rows)
        return len(request_rows)

    def load_variant_rows(self):
        return self.rows

    def load_webflow_variants(self):
        return self.webflow


@contextmanager
def no_session():
    yield


def build_service(master=None, ecu=None, matrix=None, hw=None, kick_off=None) -> VariantService:
    return VariantService(
        master_sheet_factory=lambda path: master or FakeMasterSheet(path),
        ecu_info_factory=lambda path: ecu or FakeDocument(path, ecu_info={"Main": []}),
        system_matrix_factory=lambda path: matrix or FakeDocument(path, system_info={"GeneralInfo": []}),
        hw_info_factory=lambda path: hw or FakeDocument(path),
        session_factory=no_session,
        kick_off_factory=lambda path: kick_off or FakeDocument(path, info={}),
        master_sheet_checker=lambda _path: "",
    )


class FakeProgress:
    """Records what a progress window would show; results also land in the dialogs' infos / errors."""

    def __init__(self, dialogs, title):
        self.dialogs, self.title = dialogs, title
        self.steps: list = []

    def step(self, text):
        self.steps.append(text)

    def succeed(self, text):
        self.dialogs.infos.append((self.title, text))

    def fail(self, text):
        self.dialogs.errors.append((self.title, text))


class FakeDialogs:
    def __init__(
        self, files=(), hw_answer=False, kick_off_answer=False, table_answer=True, confirm_answer=True,
        hex_folder_answer=False,
    ):
        self.files = list(files)
        self.hw_answer = hw_answer
        self.kick_off_answer = kick_off_answer
        self.hex_folder_answer = hex_folder_answer
        self.table_answer = table_answer  # True clears the table, False keeps it, None cancels
        self.confirm_answer = confirm_answer
        self.confirmed: list = []
        self.asked: list = []
        self.infos: list = []
        self.errors: list = []
        self.picked: list = []
        self.save_path = ""
        self.windows: list = []

    def pick_file(self, title, file_filter):
        self.picked.append(title)
        return self.files.pop(0) if self.files else ""

    def pick_files(self, title, file_filter):
        self.picked.append(title)
        if not self.files:
            return []
        selected = self.files.pop(0)
        return selected if isinstance(selected, list) else [selected]

    def save_file(self, title, default_name, file_filter):
        self.saved = (title, default_name, file_filter)
        return self.save_path

    def confirm(self, title, text):
        self.confirmed.append((title, text))
        return self.confirm_answer

    def info(self, title, text):
        self.infos.append((title, text))

    def error(self, title, text):
        self.errors.append((title, text))

    def ask_files(self, title, fields, initial):
        """Hands out `files` in field order; optional fields only when their answer flag is set."""
        self.asked_fields = [field.name for field in fields]
        self.initial = dict(initial)
        wanted = {
            "HW Info": self.hw_answer,
            "Kick Off": self.kick_off_answer,
            "Calibration folder": self.hex_folder_answer,
        }
        chosen = {}
        for field in fields:
            if not field.required and not wanted.get(field.name):
                chosen[field.name] = ""
            elif self.files:
                chosen[field.name] = self.files.pop(0)
            elif field.required:
                return None  # the user cancelled before choosing every required file
            else:
                chosen[field.name] = ""
        return chosen

    def open_progress(self, title):
        progress = FakeProgress(self, title)
        self.windows.append(progress)
        return progress

    def ask_yes_no_cancel(self, title, text, yes_text=None, no_text=None):
        self.asked.append(text)
        if "still contains" in text or "did not apply" in text or "already have a WebFlow" in text:
            self.asked_labels = (yes_text, no_text)
            return self.table_answer
        return self.kick_off_answer if "Kick Off" in text else self.hw_answer


class FakeView:
    def __init__(self):
        self.rows: list = []
        self.states: dict = {}
        self.file_names: dict = {}
        self.published: list = []
        self.selected: list = []

    def show_file_name(self, field_name, path):
        self.file_names[field_name] = path

    def show_rows(self, rows):
        self.rows = list(rows)

    def read_rows(self):
        return list(self.rows)

    def row_count(self):
        return len(self.rows)

    def clear_rows(self):
        self.rows = []

    def selected_rows(self):
        return list(self.selected)

    def remove_rows(self, rows):
        self.rows = [row for i, row in enumerate(self.rows) if i not in rows]

    def set_new_variant_state(self, enabled, text):
        self.states["new"] = (enabled, text)

    def set_load_state(self, enabled, text):
        self.states["load"] = (enabled, text)

    def set_update_state(self, enabled, text):
        self.states["update"] = (enabled, text)

    def set_clear_enabled(self, enabled):
        self.states["clear"] = enabled

    def set_delete_enabled(self, enabled):
        self.states["delete"] = enabled

    def publish_variants(self, variants):
        self.published.append(variants)

    def set_workspace_enabled(self, enabled, busy=False):
        self.states["workspace"] = enabled


def run_inline(func, on_ok, on_error):
    """Task starter that runs synchronously, so presenter flows are testable without threads."""
    try:
        result = func()
    except Exception as error:
        on_error(str(error))
    else:
        on_ok(result)
