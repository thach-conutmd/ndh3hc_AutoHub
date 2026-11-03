"""Cancels the open WebFlow job: the action ribbon "Cancel", then the reason dialog and its Confirm button."""
import logging

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import Constants as Constants
from .Actions import Actions
from .components import button_is_enabled, wait_for, wait_until_idle

_logger = logging.getLogger(__name__)

CANCEL_REASON_CSS = "textarea.dialog-textarea"
CANCEL_DIALOG_XPATH = "./ancestor::div[.//button[@label='Confirm']][1]"
CANCEL_CONFIRM_XPATH = ".//button[@label='Confirm']"


def cancel_open_job(driver, reason: str) -> None:
    """Raises when the job cannot be cancelled or WebFlow keeps the cancel dialog open."""
    tile = Actions(driver).get_button_by_text("Cancel")
    if tile is None or not button_is_enabled(tile):
        raise RuntimeError("The Cancel action is not available for this WebFlow job.")
    tile.click()

    reason_field = wait_for(driver, By.CSS_SELECTOR, CANCEL_REASON_CSS)
    reason_field.clear()
    reason_field.send_keys(reason)
    dialog = reason_field.find_element(By.XPATH, CANCEL_DIALOG_XPATH)
    confirm = WebDriverWait(driver, Constants.BODY_TIMEOUT).until(
        lambda _: next(
            (b for b in dialog.find_elements(By.XPATH, CANCEL_CONFIRM_XPATH) if button_is_enabled(b)),
            None,
        )
    )
    confirm.click()
    WebDriverWait(driver, Constants.WEBFLOW_TIMEOUT).until(EC.staleness_of(reason_field))
    wait_until_idle(driver)
    _logger.info("WebFlow job cancelled with reason: %s", reason)
