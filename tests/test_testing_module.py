import pytest
from PySide6.QtWidgets import QPushButton

from autohub.modules.testing.add_instance_member_dialog import AddInstanceMemberDialog
from autohub.modules.testing.features import add_instance_member_feature
import autohub.modules.testing.module as testing_module
from autohub.modules.testing.service import InstanceMemberTestService, validate_job_number
import autohub.modules.testing.ui as testing_ui
from tests.fakes import FakeDialogs


class FakeSession:
    def __init__(self, dashboard=True, added=True, quit_error=False):
        self.dashboard = dashboard
        self.added = added
        self.quit_error = quit_error
        self.calls = []
        self.quit_calls = 0

    def open_dashboard_page(self):
        self.calls.append("dashboard")
        return self.dashboard

    def add_instance_member(self, job_id, name):
        self.calls.append(("add", job_id, name))
        return self.added

    def quit(self):
        self.quit_calls += 1
        if self.quit_error:
            raise OSError("browser already closed")


def make_service(session, default_user="Default Engineer"):
    return InstanceMemberTestService(lambda: session, lambda: default_user)


def wait_for_worker(qapp, dialog):
    dialog._worker.wait(5000)
    qapp.processEvents()


def test_validate_job_number_requires_digits():
    assert validate_job_number(" 12345 ") == "12345"
    with pytest.raises(ValueError, match="enter a job number"):
        validate_job_number("  ")
    with pytest.raises(ValueError, match="digits only"):
        validate_job_number("12a")


def test_add_user_uses_entered_user_and_closes_session():
    session = FakeSession()
    assert make_service(session).add_user("123", " Jane Doe ") == "Jane Doe"
    assert session.calls == ["dashboard", ("add", "123", "Jane Doe")]
    assert session.quit_calls == 1


def test_add_user_falls_back_to_change_engineer_when_blank():
    session = FakeSession()
    assert make_service(session, "Change Eng (Dept)").add_user("123", "") == "Change Eng (Dept)"
    assert session.calls[-1] == ("add", "123", "Change Eng (Dept)")


def test_add_user_without_user_or_default_raises_before_browser_starts():
    opened = []
    service = InstanceMemberTestService(lambda: opened.append(1) or FakeSession(), lambda: "")
    with pytest.raises(ValueError, match="Change Engineer in Settings"):
        service.add_user("123", "")
    assert opened == []


def test_add_user_reports_dashboard_failure_and_still_quits():
    session = FakeSession(dashboard=False)
    with pytest.raises(RuntimeError, match="dashboard"):
        make_service(session).add_user("123", "Jane")
    assert session.quit_calls == 1


def test_add_user_reports_instance_member_failure():
    session = FakeSession(added=False)
    with pytest.raises(RuntimeError, match="Could not add Jane to Instance Members of job 123"):
        make_service(session).add_user("123", "Jane")
    assert session.quit_calls == 1


def test_quit_error_does_not_mask_success():
    session = FakeSession(quit_error=True)
    assert make_service(session).add_user("123", "Jane") == "Jane"


def test_dialog_rejects_invalid_job_without_starting_work(qapp):
    dialogs = FakeDialogs()
    started = []
    service = InstanceMemberTestService(lambda: started.append(1) or FakeSession(), lambda: "Default")
    dialog = AddInstanceMemberDialog(service, dialogs)
    dialog._on_add()
    assert dialogs.errors and "enter a job number" in dialogs.errors[0][1]
    assert started == []


def test_dialog_runs_add_and_reports_success(qapp):
    dialogs = FakeDialogs()
    session = FakeSession()
    dialog = AddInstanceMemberDialog(make_service(session), dialogs)
    dialog._job.setText("777")
    dialog._on_add()
    wait_for_worker(qapp, dialog)
    assert "Default Engineer was added to Instance Members of job 777." in dialogs.infos[0][1]
    assert session.calls[-1] == ("add", "777", "Default Engineer")


def test_dialog_shows_error_from_service(qapp):
    dialogs = FakeDialogs()
    dialog = AddInstanceMemberDialog(make_service(FakeSession(added=False)), dialogs)
    dialog._job.setText("777")
    dialog._user.setText("Jane")
    dialog._on_add()
    wait_for_worker(qapp, dialog)
    assert "Could not add Jane" in dialogs.errors[0][1]
    assert dialog._job.isEnabled()


def test_testing_page_lists_feature_buttons(qapp):
    feature = add_instance_member_feature(make_service(FakeSession()), lambda parent: FakeDialogs())
    module = testing_module.TestingModule([feature])
    page = module.create_widget()
    assert isinstance(page, testing_ui.TestingWidget)
    assert [button.text() for button in page.findChildren(QPushButton)] == ["Add User to Instance Members"]
    assert module.display_name == "Test"


def test_features_are_placed_in_their_group_frame_with_compact_width():
    from PySide6.QtWidgets import QGroupBox
    from unittest.mock import Mock
    from autohub.modules.testing.features import TestFeature

    page = testing_ui.TestingWidget([
        TestFeature("Add User to Instance Members", Mock()),
        TestFeature("Other", Mock(), group="Other"),
    ])
    groups = {g.title(): g for g in page.findChildren(QGroupBox)}
    assert set(groups) == {"WebFlow", "Other"}
    assert [b.text() for b in groups["WebFlow"].findChildren(QPushButton)] == ["Add User to Instance Members"]
    assert all(b.width() == b.maximumWidth() <= 240 for b in page.findChildren(QPushButton))
