from unittest.mock import Mock

import pytest
from selenium.common.exceptions import StaleElementReferenceException

from autohub.services.WebFlow.save_confirmation import SaveBeforeImportConfirmation


def warning():
    dialog = Mock()
    dialog.text = (
        "WARNING\nFollowing fields were changed without saving: Hardware part number\n"
        "Data filled in by you will be saved before import. Do you want to continue?"
    )
    dialog.is_displayed.return_value = True
    yes = dialog.find_element.return_value
    yes.is_displayed.return_value = yes.is_enabled.return_value = True
    driver = Mock()
    driver.find_elements.return_value = [dialog]
    return driver, dialog, yes


def test_confirms_pictured_warning_once_and_waits_for_it_to_close():
    driver, dialog, yes = warning()
    confirmation = SaveBeforeImportConfirmation(driver, "Import")
    assert confirmation.pending()
    assert confirmation.pending()
    yes.click.assert_called_once()
    dialog.is_displayed.return_value = False
    assert not confirmation.pending()


@pytest.mark.parametrize("visible,enabled", [(False, True), (True, False)])
def test_waits_for_yes_to_be_available(visible, enabled):
    driver, _, yes = warning()
    yes.is_displayed.return_value = visible
    yes.is_enabled.return_value = enabled
    confirmation = SaveBeforeImportConfirmation(driver, "Import")
    assert confirmation.pending()
    yes.click.assert_not_called()
    yes.is_displayed.return_value = yes.is_enabled.return_value = True
    assert confirmation.pending()
    yes.click.assert_called_once()


def test_does_not_confirm_unrelated_warning():
    driver, dialog, yes = warning()
    dialog.text = "Do you want to delete this job?"
    assert not SaveBeforeImportConfirmation(driver, "Import").pending()
    yes.click.assert_not_called()


def test_uncertain_yes_click_is_never_repeated():
    driver, _, yes = warning()
    yes.click.side_effect = StaleElementReferenceException()
    confirmation = SaveBeforeImportConfirmation(driver, "Import")
    with pytest.raises(StaleElementReferenceException):
        confirmation.pending()
    assert confirmation.pending()
    yes.click.assert_called_once()
