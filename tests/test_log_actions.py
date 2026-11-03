import logging
from unittest.mock import Mock

import pytest

from autohub.core import logger
from autohub.core.settings import JsonSettingsStore
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
    monkeypatch.setattr(logger, "LOG_FILE_PATH", path)
    open_url = Mock(return_value=opened)
    monkeypatch.setattr(ui.QDesktopServices, "openUrl", open_url)
    dialogs = Mock()
    page = ui.SettingsWidget(MemorySettings(), dialogs)
    page._open_log.click()
    assert open_url.call_args.args[0].toLocalFile() == str(path)
    assert dialogs.error.called is not opened
    assert not page._apply.isEnabled()


def test_open_missing_log_shows_error(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(logger, "LOG_FILE_PATH", tmp_path / "missing.log")
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


@pytest.fixture
def isolated_logging(monkeypatch, tmp_path):
    root = logging.getLogger()
    handlers, level, disabled = root.handlers[:], root.level, root.manager.disable
    for handler in handlers:
        root.removeHandler(handler)
    monkeypatch.setattr(logger, "LOG_FILE_PATH", tmp_path / "initial" / "autohub.log")
    logging.disable(logging.NOTSET)
    try:
        yield root
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
            handler.close()
        for handler in handlers:
            root.addHandler(handler)
        root.setLevel(level)
        logging.disable(disabled)


def test_log_location_defaults_to_existing_logs_folder():
    assert logger.log_location({}) == logger.LOG_DIR.resolve()


def test_switch_log_location_keeps_other_handlers_and_writes_only_to_new_file(
    isolated_logging, tmp_path
):
    first, second = tmp_path / "first", tmp_path / "second" / "nested"
    logger.setup_logging(location=first)
    other = logging.FileHandler(tmp_path / "other.log")
    isolated_logging.addHandler(other)
    logging.info("first entry")
    logger.set_log_location(second)
    logging.info("second entry")
    assert logger.log_file_path() == second / "autohub.log"
    assert "first entry" in (first / "autohub.log").read_text()
    assert "second entry" not in (first / "autohub.log").read_text()
    assert "second entry" in (second / "autohub.log").read_text()
    assert other in isolated_logging.handlers
    logger.clear_log_file()
    assert (second / "autohub.log").read_text() == ""
    logging.info("after clearing")
    assert "after clearing" in (second / "autohub.log").read_text()
    logger.setup_logging(location=second)
    assert len([
        handler for handler in isolated_logging.handlers
        if isinstance(handler, logging.FileHandler)
    ]) == 2
    assert len([
        handler for handler in isolated_logging.handlers
        if handler.name == "autohub.console"
    ]) == 1


def test_invalid_log_location_keeps_active_file(isolated_logging, tmp_path, monkeypatch):
    first = tmp_path / "first"
    logger.setup_logging(location=first)
    handlers = isolated_logging.handlers[:]
    monkeypatch.setattr(logger, "TemporaryFile", Mock(side_effect=PermissionError("Not writable")))
    with pytest.raises(PermissionError, match="Not writable"):
        logger.set_log_location(tmp_path / "unwritable")
    assert logger.log_file_path() == first / "autohub.log"
    assert isolated_logging.handlers == handlers
    logging.info("still logging")
    assert "still logging" in (first / "autohub.log").read_text()


def test_log_location_rejects_file_instead_of_folder(isolated_logging, tmp_path):
    path = tmp_path / "file"
    path.touch()
    with pytest.raises(FileExistsError):
        logger.set_log_location(path)


def test_saved_log_location_restores_and_open_clear_use_applied_location(
    qapp, tmp_path, monkeypatch, isolated_logging
):
    settings = JsonSettingsStore(tmp_path / "settings.json")
    dialogs = Mock()
    page = ui.SettingsWidget(settings, dialogs)
    chosen = tmp_path / "custom logs"
    page._log_location.setText(str(chosen))
    assert page._apply.isEnabled()
    assert logger.LOG_LOCATION_KEY not in settings.load()
    page._apply.click()
    assert not page._apply.isEnabled()
    assert settings.load()[logger.LOG_LOCATION_KEY] == str(chosen)
    assert (chosen / "autohub.log").is_file()
    reopened = ui.SettingsWidget(settings, dialogs)
    assert reopened._log_location.text() == str(chosen)

    open_url = Mock(return_value=True)
    monkeypatch.setattr(ui.QDesktopServices, "openUrl", open_url)
    page._log_location.setText(str(tmp_path / "not applied"))
    page._open_log.click()
    assert open_url.call_args.args[0].toLocalFile() == str(chosen / "autohub.log")
    (chosen / "autohub.log").write_text("clear this", encoding="utf-8")
    dialogs.confirm.return_value = True
    page._clear_log.click()
    assert (chosen / "autohub.log").read_text() == ""
    dialogs.error.assert_not_called()


@pytest.mark.parametrize("selected", ["", "/selected/logs"])
def test_browse_log_location_marks_only_selected_folder_as_unsaved(qapp, monkeypatch, selected):
    settings = MemorySettings()
    page = ui.SettingsWidget(settings, Mock())
    original = page._log_location.text()
    browse = Mock(return_value=selected)
    monkeypatch.setattr(ui.QFileDialog, "getExistingDirectory", browse)
    page._browse_log_location.click()
    assert page._log_location.text() == (selected or original)
    assert page._apply.isEnabled() is bool(selected)
    assert logger.LOG_LOCATION_KEY not in settings.load()


def test_invalid_folder_prevents_settings_apply(qapp, tmp_path, monkeypatch):
    settings, dialogs = MemorySettings(), Mock()
    page = ui.SettingsWidget(settings, dialogs)
    page._log_location.setText(str(tmp_path / "unwritable"))
    monkeypatch.setattr(ui, "set_log_location", Mock(side_effect=PermissionError("Not writable")))
    page._apply.click()
    dialogs.error.assert_called_once()
    assert "Not writable" in dialogs.error.call_args.args[1]
    assert page._apply.isEnabled()
    assert settings.load() == {}


def test_discard_restores_log_location_and_other_settings(qapp):
    settings, dialogs = MemorySettings(), Mock()
    dialogs.ask_yes_no_cancel.return_value = False
    page = ui.SettingsWidget(settings, dialogs)
    original = page._current()
    page._log_location.setText("/unapplied/logs")
    page._logging.setChecked(not page._logging.isChecked())
    assert page.confirm_leave()
    assert page._current() == original
    assert not page._apply.isEnabled()


def test_startup_uses_saved_log_location(qapp, tmp_path, monkeypatch, isolated_logging):
    import main

    folder = tmp_path / "startup logs"
    settings = MemorySettings({logger.LOG_LOCATION_KEY: str(folder)})
    _, apply_settings = main.startup_steps(qapp, settings, {})[0]
    apply_settings()
    logging.info("startup entry")
    assert logger.log_file_path() == folder / "autohub.log"
    assert "startup entry" in (folder / "autohub.log").read_text()
