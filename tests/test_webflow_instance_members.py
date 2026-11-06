from unittest.mock import Mock, patch

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

import pytest

from autohub.services.WebFlow import Constants
from autohub.services.WebFlow.InstanceMembers import InstanceMembers, _matches_user
from autohub.services.WebFlow.WebFlow import WebFlow


def _element(title):
    element = Mock()
    element.get_attribute.return_value = title
    return element


def test_user_title_matches_name_with_or_without_department():
    assert _matches_user("Ngo Huu Dat (MS/EJV5-PS)", "Ngo Huu Dat")
    assert _matches_user("Ngo Huu Dat (MS/EJV5-PS)", "Ngo Huu Dat (MS/EJV5-PS)")
    assert not _matches_user("Ngo Huu Dat Extra (MS/EJV5-PS)", "Ngo Huu Dat")
    assert not _matches_user("Nguyen Buu Thach (MS/EJV5-PS)", "Ngo Huu Dat")


def test_target_roles_skip_plant_introduction_and_keep_dom_order():
    driver = Mock()
    roles = ["Request", "Prerun", "Preparation", "Execution", "Coordination", "Plant Introduction", "Completion"]
    driver.find_elements.return_value = [_element(role) for role in roles]

    assert InstanceMembers(driver)._target_roles() == [
        "Request", "Prerun", "Preparation", "Execution", "Coordination", "Completion",
    ]


def test_target_roles_raise_when_none_are_available():
    driver = Mock()
    driver.find_elements.return_value = [_element("Plant Introduction")]

    with pytest.raises(RuntimeError):
        InstanceMembers(driver)._target_roles()


def test_fill_job_adds_change_engineer_after_saved_job():
    fake_self = Mock()
    fake_self.job_filler.fill.return_value = ["ok"]
    variant = {"ecr": {"change_engineer": "Ngo Huu Dat"}}

    with patch("autohub.services.WebFlow.WebFlow.InstanceMembers") as members, \
            patch("autohub.services.WebFlow.WebFlow.run_step", return_value=True) as step:
        assert WebFlow._fill_job(fake_self, variant) == ["ok"]

    fake_self.job_filler.fill.assert_called_once_with(variant)
    members.assert_called_once_with(fake_self)
    assert step.call_args.args[2] == members.return_value.add_user
    assert step.call_args.args[3] == "Ngo Huu Dat"


@pytest.mark.parametrize("variant", [{}, {"ecr": {}}, {"ecr": {"change_engineer": "  "}}])
def test_fill_job_skips_instance_members_without_change_engineer(variant):
    fake_self = Mock()
    fake_self.job_filler.fill.return_value = ["ok"]

    with patch("autohub.services.WebFlow.WebFlow.run_step") as step:
        assert WebFlow._fill_job(fake_self, variant) == ["ok"]
    step.assert_not_called()


def test_fill_job_raises_when_instance_members_step_fails():
    fake_self = Mock()
    fake_self.job_filler.fill.return_value = []

    with patch("autohub.services.WebFlow.WebFlow.run_step", return_value=False):
        with pytest.raises(RuntimeError, match="Change Engineer"):
            WebFlow._fill_job(fake_self, {"ecr": {"change_engineer": "Ngo Huu Dat"}})


def test_constants_skip_only_plant_introduction():
    assert Constants.INSTANCE_MEMBERS_SKIPPED_ROLES == ("Plant Introduction",)


class _Polls:
    """Stands in for WebDriverWait: calls the condition until it is truthy, or times out after max_polls."""

    def __init__(self, max_polls=5):
        self.max_polls = max_polls
        self.polls = 0

    def __call__(self, driver, timeout):
        outer = self

        class Waiter:
            def until(self, condition):
                for _ in range(outer.max_polls):
                    outer.polls += 1
                    if condition(driver):
                        return True
                raise TimeoutException("timed out")

        return Waiter()


def _row(title=None, stale=False):
    row = Mock()
    if stale:
        row.get_attribute.side_effect = StaleElementReferenceException("stale")
    else:
        row.get_attribute.return_value = title
    return row


def test_filter_relocates_rows_on_every_poll_and_survives_stale_rows():
    driver = Mock()
    driver.find_elements.side_effect = [
        [_row(stale=True)],
        [_row("Ngo Huu Dat (MS/EJV5-PS)")],
        [_row("Ngo Huu Dat (MS/EJV5-PS)")],
    ]
    polls = _Polls()
    with patch("autohub.services.WebFlow.InstanceMembers.WebDriverWait", polls), \
            patch("autohub.services.WebFlow.InstanceMembers.record_checkpoint"):
        InstanceMembers(driver)._wait_for_user_row("Ngo Huu Dat")

    assert driver.find_elements.call_count == 3


def test_filter_waits_for_the_match_to_be_stable_between_two_polls():
    driver = Mock()
    driver.find_elements.side_effect = [
        [_row("Ngo Huu Dat (MS/EJV5-PS)")],
        [_row("Ngo Huu Dat (MS/EJV5-PS)"), _row("Ngo Huu Dat Extra (X)")],
        [_row("Ngo Huu Dat (MS/EJV5-PS)"), _row("Ngo Huu Dat Extra (X)")],
    ]
    with patch("autohub.services.WebFlow.InstanceMembers.WebDriverWait", _Polls()), \
            patch("autohub.services.WebFlow.InstanceMembers.record_checkpoint"):
        InstanceMembers(driver)._wait_for_user_row("Ngo Huu Dat")
    assert driver.find_elements.call_count == 2


def test_timeout_names_the_searched_user():
    driver = Mock()
    driver.find_elements.return_value = [_row("Someone Else (X)")]
    with patch("autohub.services.WebFlow.InstanceMembers.WebDriverWait", _Polls(max_polls=2)):
        with pytest.raises(TimeoutException, match="'Ngo Huu Dat'"):
            InstanceMembers(driver)._wait_for_user_row("Ngo Huu Dat")


def test_filter_box_is_retried_only_on_stale_element():
    box = Mock()
    box.send_keys.side_effect = [StaleElementReferenceException("stale"), None]
    driver = Mock()
    driver.find_element.return_value = box
    with patch("autohub.services.WebFlow.InstanceMembers.time.sleep"):
        InstanceMembers(driver)._type_filter("Ngo Huu Dat")
    assert box.send_keys.call_count == 2


def test_filter_box_gives_up_after_the_short_retry_budget():
    box = Mock()
    box.send_keys.side_effect = StaleElementReferenceException("stale")
    driver = Mock()
    driver.find_element.return_value = box
    with patch("autohub.services.WebFlow.InstanceMembers.time.sleep"):
        with pytest.raises(StaleElementReferenceException):
            InstanceMembers(driver)._type_filter("Ngo Huu Dat")
    assert box.send_keys.call_count == Constants.INSTANCE_MEMBERS_STALE_RETRIES + 1


def test_filter_records_checkpoints_in_order_and_failure_with_error():
    driver = Mock()
    driver.find_element.return_value = Mock()
    driver.find_elements.return_value = [_row("Ngo Huu Dat (MS/EJV5-PS)")]
    with patch("autohub.services.WebFlow.InstanceMembers.WebDriverWait", _Polls(max_polls=3)), \
            patch("autohub.services.WebFlow.InstanceMembers.record_checkpoint") as record:
        InstanceMembers(driver)._filter("Ngo Huu Dat")
    stages = [c.args[0].split(" for ")[0] for c in record.call_args_list]
    assert stages == ["Instance Members before filter", "Instance Members after entering user name",
                      "Instance Members results refreshed", "Instance Members user found"]

    with patch("autohub.services.WebFlow.InstanceMembers.WebDriverWait", _Polls(max_polls=1)), \
            patch("autohub.services.WebFlow.InstanceMembers.record_checkpoint") as record:
        driver.find_elements.return_value = []
        with pytest.raises(TimeoutException):
            InstanceMembers(driver)._filter("Ngo Huu Dat")
    failed = record.call_args_list[-1]
    assert failed.args[1] is False and "TimeoutException" in failed.kwargs["error"]
