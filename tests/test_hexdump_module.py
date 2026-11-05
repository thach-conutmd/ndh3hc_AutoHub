"""Tests for the Hexdump module widget and its placeholder backend."""
import time

from autohub.core.ports import HexdumpInputError
from autohub.modules.hexdump.module import HexdumpModule
from autohub.modules.hexdump.ui import HexdumpWidget
from autohub.modules.hexdump.unavailable import UnavailableHexdumpService


class FakeAnalysis:
    def __init__(self, summary="OK", range_result=(3, 9), error=None):
        self.summary = summary
        self.range_result = range_result
        self.error = error
        self.calls: list = []

    def modes(self):
        return ("block", "cnt")

    def check_settings(self, path):
        self.calls.append(("check", path))
        if self.error:
            raise HexdumpInputError(self.error)
        return self.summary

    def find_range(self, mode, path, key):
        self.calls.append(("find", mode, path, key))
        if self.error:
            raise HexdumpInputError(self.error)
        return self.range_result


class FakePicker:
    def __init__(self, path=""):
        self.path = path

    def pick_file(self, title, file_filter):
        return self.path


def _wait_idle(qapp, widget, timeout=5.0):
    deadline = time.monotonic() + timeout
    while widget._busy and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert not widget._busy, "background task did not finish"


def test_module_is_named_hexdump_and_builds_widget(qapp):
    module = HexdumpModule(lambda: FakeAnalysis())
    assert module.display_name == "Hexdump"
    widget = module.create_widget()
    try:
        assert isinstance(widget, HexdumpWidget)
    finally:
        widget.close()


def test_widget_lists_modes_from_service(qapp):
    widget = HexdumpWidget(FakeAnalysis(), dialogs=FakePicker())
    try:
        assert [widget._mode.itemText(i) for i in range(widget._mode.count())] == ["block", "cnt"]
    finally:
        widget.close()


def test_find_range_shows_lines_and_passes_inputs(qapp):
    service = FakeAnalysis(range_result=(3, 9))
    widget = HexdumpWidget(service, dialogs=FakePicker())
    try:
        widget._mode.setCurrentText("cnt")
        widget._dump_path.setText("dump.txt")
        widget._key.setText("KEY")
        widget._find_range()
        _wait_idle(qapp, widget)
        assert service.calls == [("find", "cnt", "dump.txt", "KEY")]
        assert widget._range_result.text() == "Lines 3 – 9"
    finally:
        widget.close()


def test_find_range_reports_service_error_without_traceback(qapp):
    widget = HexdumpWidget(FakeAnalysis(error="key 'X' not found"), dialogs=FakePicker())
    try:
        widget._dump_path.setText("dump.txt")
        widget._key.setText("X")
        widget._find_range()
        _wait_idle(qapp, widget)
        assert widget._range_result.text() == "Not found: key 'X' not found"
    finally:
        widget.close()


def test_find_range_requires_dump_and_key(qapp):
    service = FakeAnalysis()
    widget = HexdumpWidget(service, dialogs=FakePicker())
    try:
        widget._find_range()
        assert widget._range_result.text() == "Enter a dump file and a key."
        assert service.calls == []
    finally:
        widget.close()


def test_settings_check_shows_summary_and_errors(qapp):
    service = FakeAnalysis(summary="OK: 1 file(s)")
    widget = HexdumpWidget(service, dialogs=FakePicker())
    try:
        widget._settings_path.setText("job.toml")
        widget._check_settings()
        _wait_idle(qapp, widget)
        assert widget._settings_result.toPlainText() == "OK: 1 file(s)"

        service.error = "[common]: unknown parameter 'X'"
        widget._check_settings()
        _wait_idle(qapp, widget)
        assert widget._settings_result.toPlainText() == "Settings are invalid:\n[common]: unknown parameter 'X'"
    finally:
        widget.close()


def test_browse_fills_path_field(qapp):
    widget = HexdumpWidget(FakeAnalysis(), dialogs=FakePicker(path="picked.toml"))
    try:
        widget._pick(widget._settings_path, "Select", "*.toml")
        assert widget._settings_path.text() == "picked.toml"
    finally:
        widget.close()


def test_placeholder_backend_reports_unavailable_on_every_action(qapp):
    widget = HexdumpWidget(UnavailableHexdumpService(), dialogs=FakePicker())
    try:
        widget._dump_path.setText("dump.txt")
        widget._key.setText("KEY")
        widget._find_range()
        _wait_idle(qapp, widget)
        assert widget._range_result.text() == "Not found: The Hexdump service is not available yet."
    finally:
        widget.close()
