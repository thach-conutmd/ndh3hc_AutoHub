import logging
from unittest.mock import Mock

import pytest

from autohub.core import logger
from autohub.modules.settings import ui
from tests.fakes import MemorySettings


def test_clear_log_preserves_active_handler_and_new_entries(tmp_path, monkeypatch):
    path = tmp_path / "autohub.log"
    monkeypatch.setattr(logger, "LOG_FILE_PATH", path)
    handler = logging.FileHandler(path, encoding="utf-8")
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        handler.emit(logging.makeLogRecord({"msg": "old entry"}))
        logger.clear_log_file()
        assert path.read_text(encoding="utf-8") == ""
        handler.emit(logging.makeLogRecord({"msg": "new entry"}))
        assert path.read_text(encoding="utf-8") == "new entry\n"
    finally:
        root.removeHandler(handler)
        handler.close()


def test_clear_missing_log_reports_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(logger, "LOG_FILE_PATH", tmp_path / "missing.log")
    with pytest.raises(FileNotFoundError):
        logger.clear_log_file()


@pytest.mark.parametrize("opened", [True, False])
def test_open_log_uses_default_application(qapp, tmp_path, monkeypatch, opened):
    path = tmp_path / "autohub.log"
    path.touch()
    monkeypatch.setattr(ui, "LOG_FILE_PATH", path)
    open_url = Mock(return_value=opened)
    monkeypatch.setattr(ui.QDesktopServices, "openUrl", open_url)
    dialogs = Mock()
    page = ui.SettingsWidget(MemorySettings(), dialogs)
    page._open_log.click()
    assert open_url.call_args.args[0].toLocalFile() == str(path)
    assert dialogs.error.called is not opened
    assert not page._apply.isEnabled()


def test_open_missing_log_shows_error(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "LOG_FILE_PATH", tmp_path / "missing.log")
    open_url = Mock()
    monkeypatch.setattr(ui.QDesktopServices, "openUrl", open_url)
    dialogs = Mock()
    page = ui.SettingsWidget(MemorySettings(), dialogs)
    page._open_log.click()
    open_url.assert_not_called()
    dialogs.error.assert_called_once()


@pytest.mark.parametrize("confirmed", [True, False])
def test_clear_log_requires_confirmation(qapp, monkeypatch, confirmed):
    clear = Mock()
    monkeypatch.setattr(ui, "clear_log_file", clear)
    dialogs = Mock()
    dialogs.confirm.return_value = confirmed
    page = ui.SettingsWidget(MemorySettings(), dialogs)
    page._clear_log.click()
    assert clear.called is confirmed
    assert dialogs.info.called is confirmed
    assert not page._apply.isEnabled()


def test_clear_log_failure_shows_error(qapp, monkeypatch):
    monkeypatch.setattr(ui, "clear_log_file", Mock(side_effect=PermissionError("Access denied")))
    dialogs = Mock()
    dialogs.confirm.return_value = True
    page = ui.SettingsWidget(MemorySettings(), dialogs)
    page._clear_log.click()
    dialogs.error.assert_called_once()
    dialogs.info.assert_not_called()
