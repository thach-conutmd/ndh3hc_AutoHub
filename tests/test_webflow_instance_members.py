from unittest.mock import Mock, patch

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
