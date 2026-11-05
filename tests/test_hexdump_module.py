"""Tests for the Hexdump module: service adapter error conversion and widget behavior."""
import time

import pytest

from autohub.core.ports import HexdumpInputError
from autohub.modules.hexdump.module import HexdumpModule
from autohub.modules.hexdump.ui import HexdumpWidget
from autohub.services.HexdumpAnalyzer.exceptions import HexdumpSettingsError
from autohub.services.HexdumpAnalyzer.range_finder import find_range
from autohub.services.HexdumpAnalyzer.service import HexdumpService

DFLASH_TEXT = """+-------+
| Id: 7
| Name: BLK_A
| Info: x
+-------+
+-------+
| Id: 8
| Name: BLK_B
| Info: y
+-------+
"""


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


def _settings_toml(path_to_source) -> str:
    return f"""
[[file]]
FILE = '{path_to_source}'
APP = "notepad"
MODE = "block"

[[file.shot]]
name = "first"
key = "BLK_A"
"""


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


def test_service_find_range_matches_direct_call(tmp_path):
    dump = tmp_path / "dump.txt"
    dump.write_text(DFLASH_TEXT, encoding="utf-8")
    assert HexdumpService().find_range("block", str(dump), "BLK_B") == find_range("block", str(dump), "BLK_B")


def test_service_find_range_converts_missing_key_and_file(tmp_path):
    dump = tmp_path / "dump.txt"
    dump.write_text(DFLASH_TEXT, encoding="utf-8")
    with pytest.raises(HexdumpInputError):
        HexdumpService().find_range("block", str(dump), "NOPE")
    with pytest.raises(HexdumpInputError):
        HexdumpService().find_range("block", str(tmp_path / "absent.txt"), "BLK_A")


def test_service_find_range_rejects_unknown_mode(tmp_path):
    with pytest.raises(HexdumpInputError, match="unknown MODE"):
        HexdumpService().find_range("bogus", str(tmp_path), "KEY")


def test_service_check_settings_converts_errors_to_messages(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text('[common]\nFOO = 1\n', encoding="utf-8")
    with pytest.raises(HexdumpInputError) as info:
        HexdumpService().check_settings(str(bad))
    assert "unknown parameter 'FOO'" in str(info.value)
    assert "Nothing to capture" in str(info.value)


def test_service_check_settings_summarizes_valid_file(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text(DFLASH_TEXT, encoding="utf-8")
    settings_file = tmp_path / "job.toml"
    settings_file.write_text(_settings_toml(source), encoding="utf-8")
    summary = HexdumpService().check_settings(str(settings_file))
    assert summary.startswith("OK: 1 file(s), 1 shot(s), output folder 'out'.")
    assert "MODE=block" in summary and "- first: key=BLK_A" in summary


def test_service_settings_error_is_wrapped_not_leaked(tmp_path):
    with pytest.raises(HexdumpInputError) as info:
        HexdumpService().check_settings(str(tmp_path / "missing.toml"))
    assert not isinstance(info.value, HexdumpSettingsError)
    assert "Settings file not found" in str(info.value)
