import pytest

from autohub.core.capabilities import Closable, StartupTask, VariantSink, VariantSource
from autohub.core.settings import JsonSettingsStore
from autohub.modules.creation.service import WebFlowConfig, WebFlowJobService
from autohub.modules.creation.ui import CreationWidget
from autohub.modules.home.ui import HomeWidget
from tests.fakes import FakeDialogs, FakeWebFlow, MemorySettings, build_service


def test_json_settings_store_roundtrip(tmp_path):
    store = JsonSettingsStore(tmp_path / "s.json")
    assert store.load() == {}
    store.update(a=1)
    store.update(b=2)
    assert store.load() == {"a": 1, "b": 2}


def test_webflow_service_releases_browser_after_success_and_quits_only_once():
    FakeWebFlow.instances.clear()
    service = WebFlowJobService(webflow_factory=FakeWebFlow)
    config = WebFlowConfig("", "url", "v", "r")
    variants = [{"part_number": "P1", "ecu_type": "E"}]

    assert service.create_jobs(variants, config) == [{"PartNumber": "P1", "JobId": "1"}]
    service.create_jobs(variants, config)
    first, second = FakeWebFlow.instances
    assert first.quit_calls == 1 and second.quit_calls == 1

    service.shutdown()  # app close after a successful run
    assert second.quit_calls == 1


def test_webflow_service_keeps_failed_browser_until_shutdown():
    class FailingWebFlow(FakeWebFlow):
        def create_and_fill_jobs(self, variants, tool_version, routing, progress=None, state=None, checkpoint=None):
            raise RuntimeError("boom")

    FakeWebFlow.instances.clear()
    service = WebFlowJobService(webflow_factory=FailingWebFlow, sleep=lambda _seconds: None)
    with pytest.raises(RuntimeError):
        service.create_jobs([{"part_number": "P1", "ecu_type": "E"}], WebFlowConfig("", "url", "v", "r"))
    *earlier, browser = FakeWebFlow.instances
    assert len(earlier) == 4 and all(b.quit_calls == 1 for b in earlier)  # one browser per attempt
    assert browser.quit_calls == 0

    service.shutdown()
    service.shutdown()
    assert browser.quit_calls == 1


def test_webflow_quit_is_idempotent(monkeypatch):
    from selenium import webdriver
    from autohub.services.WebFlow.WebFlow import WebFlow

    calls = []
    monkeypatch.setattr(webdriver.Edge, "quit", lambda self: calls.append(self))
    browser = object.__new__(WebFlow)
    browser.quit()
    browser.quit()
    assert len(calls) == 1


def test_pages_expose_capabilities(qapp):
    home = HomeWidget(build_service(), MemorySettings(), FakeDialogs())
    creation = CreationWidget(WebFlowJobService(webflow_factory=FakeWebFlow), MemorySettings())
    assert isinstance(home, VariantSource)
    assert isinstance(creation, VariantSink)
    assert isinstance(creation, Closable)
    assert isinstance(creation, StartupTask)


def _two_variant_creation(settings=None):
    creation = CreationWidget(WebFlowJobService(webflow_factory=FakeWebFlow), settings or MemorySettings())
    creation.set_variants(
        [
            {"part_number": "P1", "ecu_type": "E", "event": "A"},
            {"part_number": "P2", "ecu_type": "E", "event": "A"},
        ]
    )
    for checkbox in creation._checklist._checkboxes.values():
        checkbox.setChecked(True)
    return creation


def selected_part_numbers(creation):
    return [v["part_number"] for v in creation._checklist.selected_variants()]


def test_checklist_selection_starts_empty_and_is_not_persisted(qapp):
    settings = MemorySettings({"selected_variants": ["P2"]})
    creation = CreationWidget(WebFlowJobService(webflow_factory=FakeWebFlow), settings)
    creation.set_variants([{"part_number": "P2", "ecu_type": "E", "event": "B"}])
    assert selected_part_numbers(creation) == []
    creation._checklist._checkboxes["P2"].setChecked(True)
    assert selected_part_numbers(creation) == ["P2"]
    assert settings.data["selected_variants"] == ["P2"]  # untouched stale value


def test_reloading_variants_clears_the_selection(qapp):
    creation = _two_variant_creation()
    assert selected_part_numbers(creation) == ["P1", "P2"]
    creation.set_variants([{"part_number": "P1", "ecu_type": "E", "event": "A"}])
    assert selected_part_numbers(creation) == []
    assert not creation._checklist._checkboxes["P1"].isChecked()


def test_selection_hidden_by_the_event_filter_is_cleared_too(qapp):
    creation = _two_variant_creation()
    creation._checklist._event_filter.setCurrentText("No such event")
    creation._checklist.clear_selection()
    assert selected_part_numbers(creation) == []


def test_finished_or_failed_webflow_run_clears_the_selection(qapp):
    from unittest.mock import Mock

    creation = _two_variant_creation()
    creation._finish_webflow_jobs([{"PartNumber": "P1", "JobId": "7", "Url": "http://x/app/ShowJob/7"}], Mock())
    assert selected_part_numbers(creation) == []
    assert not any(cb.isChecked() for cb in creation._checklist._checkboxes.values())

    creation = _two_variant_creation()
    creation._fail_webflow_jobs("Failed", Mock())
    assert selected_part_numbers(creation) == []


def test_progress_dialog_can_only_be_closed_after_the_action_finished():
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QApplication

    from autohub.core.progress_dialog import ProgressDialog

    QApplication.instance() or QApplication([])
    dialog = ProgressDialog("Load variants")
    dialog.step("Reading...")
    QApplication.processEvents()
    event = QCloseEvent()
    dialog.closeEvent(event)
    dialog.reject()
    assert not event.isAccepted() and dialog.isVisible()

    dialog.succeed("Loaded 3 variants from the Master Sheet.")
    QApplication.processEvents()
    assert dialog._buttons.isEnabled() and "Loaded 3 variants" in dialog._status.text()
    event = QCloseEvent()
    dialog.closeEvent(event)
    assert event.isAccepted()
    dialog.reject()


def test_file_form_dialog_needs_the_required_files(tmp_path):
    from PySide6.QtWidgets import QApplication, QDialogButtonBox

    from autohub.core.file_fields import FileField
    from autohub.core.file_form_dialog import FileFormDialog

    QApplication.instance() or QApplication([])
    real = tmp_path / "a.xlsx"
    real.write_bytes(b"x")
    dialog = FileFormDialog("New variant", [FileField("ECU", "*"), FileField("HW", "*", required=False)], {})
    ok = dialog._buttons.button(QDialogButtonBox.Ok)
    assert not ok.isEnabled()
    dialog._edits["ECU"].setText(str(real))
    assert ok.isEnabled()
    dialog._edits["HW"].setText(str(tmp_path / "missing.eml"))
    assert not ok.isEnabled() and "not found" in dialog._message.text()
    dialog._edits["HW"].setText("")
    assert ok.isEnabled() and dialog.values() == {"ECU": str(real), "HW": ""}


def test_create_jobs_reports_progress_and_forwards_it():
    seen = []
    service = WebFlowJobService(FakeWebFlow)
    config = WebFlowConfig(driver_path="", base_url="u", tool_version="t", routing="r")
    service.create_jobs([{"part_number": "P1"}], config, seen.append)
    assert seen == ["Starting the browser..."]


def test_creation_completion_and_failure_show_total_time(qapp):
    from unittest.mock import Mock

    service = WebFlowJobService(FakeWebFlow)
    service.last_elapsed_seconds = 125.5
    creation = CreationWidget(service, MemorySettings())
    window = Mock()
    creation._finish_webflow_jobs([], window)
    assert "Total time: 125.5 seconds." in window.succeed.call_args.args[0]
    creation._fail_webflow_jobs("Failed", window)
    assert "Failed\n\nTotal time: 125.5 seconds." == window.fail.call_args.args[0]


class _LinkSheet:
    def __init__(self, path):
        self.written = None
        self.closed = False

    def open(self):
        pass

    def close(self):
        self.closed = True

    def write_webflow_links(self, links, save=True):
        _LinkSheet.last = links
        return len(links)


class _FlowWithUrl(FakeWebFlow):
    def create_and_fill_jobs(self, variants, tool_version, routing, progress=None, state=None, checkpoint=None):
        return [{"PartNumber": v["part_number"], "JobId": "7", "Url": "http://x/app/ShowJob/7"} for v in variants]


def test_create_jobs_writes_links_to_the_master_sheet():
    service = WebFlowJobService(_FlowWithUrl, _LinkSheet)
    config = WebFlowConfig(driver_path="", base_url="u", tool_version="t", routing="r")
    results = service.create_jobs([{"part_number": "P1"}], config, master_sheet_path="m.xlsx")
    assert _LinkSheet.last == {"P1": "http://x/app/ShowJob/7"}
    assert "LinkError" not in results[0]


def test_create_jobs_reports_a_sheet_without_a_link_column():
    class NoLinks(_LinkSheet):
        write_webflow_links = None

    service = WebFlowJobService(_FlowWithUrl, NoLinks)
    config = WebFlowConfig(driver_path="", base_url="u", tool_version="t", routing="r")
    results = service.create_jobs([{"part_number": "P1"}], config, master_sheet_path="m.xlsx")
    assert "no WebFlow link column" in results[0]["LinkError"]


def test_webflow_link_text_is_wf_plus_the_job_number():
    from autohub.core.webflow_links import is_link, webflow_link_text

    assert webflow_link_text("https://h:8881/app/ShowJob/16406") == "WF16406"
    assert webflow_link_text("https://h:8881/app/ShowJob/16406/") == "WF16406"
    assert webflow_link_text("nothing") == ""
    assert is_link("https://x") and not is_link("WF218076")


def _creation_with_link(qapp, answer):
    from tests.fakes import FakeDialogs

    dialogs = FakeDialogs(table_answer=answer)
    settings = MemorySettings()
    creation = CreationWidget(WebFlowJobService(webflow_factory=FakeWebFlow), settings, dialogs=dialogs)
    creation.set_variants([
        {"part_number": "P1", "ecu_type": "E", "event": "A", "webflow_link": "https://h/app/ShowJob/1"},
        {"part_number": "P2", "ecu_type": "E", "event": "A"},
    ])
    for checkbox in creation._checklist._checkboxes.values():
        checkbox.setChecked(True)
    return creation, dialogs


def test_variants_with_a_webflow_link_ask_before_a_second_job(qapp):
    creation, dialogs = _creation_with_link(qapp, True)
    chosen = creation._without_declined_duplicates(creation._checklist.selected_variants())
    assert [v["part_number"] for v in chosen] == ["P1", "P2"] and "P1" in dialogs.asked[0]

    creation, _ = _creation_with_link(qapp, False)
    chosen = creation._without_declined_duplicates(creation._checklist.selected_variants())
    assert [v["part_number"] for v in chosen] == ["P2"]

    creation, _ = _creation_with_link(qapp, None)
    assert creation._without_declined_duplicates(creation._checklist.selected_variants()) == []


def test_no_question_when_no_selected_variant_has_a_link(qapp):
    creation, dialogs = _creation_with_link(qapp, None)
    only_new = [v for v in creation._checklist.selected_variants() if v["part_number"] == "P2"]
    assert creation._without_declined_duplicates(only_new) == only_new and dialogs.asked == []


def test_load_config_records_pages_unless_switched_off():
    from autohub.modules.creation.config_form import load_config

    assert "webflow_trace" in load_config(MemorySettings()).trace_dir
    assert load_config(MemorySettings({"record_webflow_pages": False})).trace_dir == ""
