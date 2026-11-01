import pytest
from PySide6.QtWidgets import QWidget

import main
from autohub.ui.startup_dialog import StartupDialog


def test_startup_dialog_reports_each_step_and_hands_over_to_the_window(qapp):
    dialog = StartupDialog(2)
    dialog.start()
    assert dialog.isVisible() and dialog.progress == 0
    dialog.step("Loading modules...")
    assert dialog.status == "Loading modules..."
    dialog.advance()
    dialog.advance()
    dialog.advance()  # never overflows
    assert dialog.progress == 2

    window = QWidget()
    dialog.finish(window)
    assert window.isVisible() and not dialog.isVisible()
    assert dialog.status == "Ready"
    window.close()


def test_run_startup_runs_steps_in_order_and_fills_progress(qapp):
    seen, ran = [], []
    dialog = StartupDialog(2)
    dialog.step = lambda message: seen.append((message, dialog.progress))
    main.run_startup([("one", lambda: ran.append(1)), ("two", lambda: ran.append(2))], dialog)
    assert ran == [1, 2]
    assert seen == [("one", 0), ("two", 1)]
    assert dialog.progress == 2


def test_run_startup_stops_at_a_failing_step(qapp):
    ran = []
    dialog = StartupDialog(2)

    def fail():
        raise RuntimeError("broken settings")

    with pytest.raises(RuntimeError, match="broken settings"):
        main.run_startup([("bad", fail), ("never", lambda: ran.append(1))], dialog)
    assert ran == [] and dialog.progress == 0


def test_startup_steps_build_the_main_window(qapp, tmp_path, monkeypatch):
    import sys
    import types

    from autohub.core.settings import JsonSettingsStore

    if "win32com.client" not in sys.modules:  # Windows-only COM package; not used until a file is opened
        try:
            import win32com.client  # noqa: F401
        except ImportError:
            win32com = types.ModuleType("win32com")
            win32com.client = types.ModuleType("win32com.client")
            monkeypatch.setitem(sys.modules, "win32com", win32com)
            monkeypatch.setitem(sys.modules, "win32com.client", win32com.client)
    monkeypatch.setattr(main, "set_dark_titlebar", lambda *_: None)
    state = {"dark": True}
    steps = main.startup_steps(qapp, JsonSettingsStore(tmp_path / "settings.json"), state)
    assert [message for message, _ in steps] == [
        "Applying settings and logging...",
        "Preparing interface...",
        "Loading modules and configuration...",
        "Building main window...",
    ]
    main.run_startup(steps, StartupDialog(len(steps)))
    assert state["modules"] and state["window"] is not None
    state["window"].deleteLater()
