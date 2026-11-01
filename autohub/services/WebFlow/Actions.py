import logging
from typing import Callable

from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from . import Constants as Constants
from .Information import Information
from .components import button_is_enabled, scroll_into_view_if_hidden, wait_for, wait_until_idle
from .step_log import run_step
from .toast import toast_severity

_logger = logging.getLogger(__name__)


def save_before_action(save: Callable[[], bool], action: str) -> bool:
    if not save():
        raise RuntimeError(f"Could not save the job before {action}; {action} was not started.")
    return True


def close_import_success(driver: WebDriver) -> bool:
    for toast in driver.find_elements(By.CSS_SELECTOR, Constants.TOAST_MESSAGE_CSS):
        if (
            not toast.is_displayed()
            or toast_severity(toast.get_attribute("class")) != "success"
            or " ".join((toast.text or "").split()).casefold() != "success imported successfully"
        ):
            continue
        try:
            close = toast.find_element(By.CSS_SELECTOR, 'button.p-toast-icon-close[aria-label="Close"]')
            if not button_is_enabled(close):
                _logger.error("Import-success toast Close button is disabled")
                return False
            close.click()
            WebDriverWait(driver, Constants.BODY_TIMEOUT).until(lambda _driver: not toast.is_displayed())
        except StaleElementReferenceException:
            _logger.debug("Import-success toast disappeared before it could be closed")
        except TimeoutException:
            _logger.exception("Import-success toast did not close")
            return False
    return True


class Actions:

    def __init__(self, driver: WebDriver):
        self.driver = driver

    def get_button_by_text(self, text: str):
        try:
            action_ribbon = wait_for(self.driver, By.CLASS_NAME, Constants.BODY_ACTION_RIBBON_CLASS)
            scroll_into_view_if_hidden(self.driver, action_ribbon)

            buttons = action_ribbon.find_elements(By.TAG_NAME, "div")
            button_texts = action_ribbon.find_elements(By.TAG_NAME, "span")

            for button, title in zip(buttons, button_texts,):
                if title.text.strip().lower() == text.strip().lower():
                    return button

            return None
        except Exception:
            _logger.warning("Could not read the action ribbon", exc_info=True)
            return None

    def save(self) -> bool:
        """Skip disabled Save; otherwise confirm the save and collapse job information."""
        def submit(_driver):
            button = self.get_button_by_text("save")
            if button is None:
                return False
            if not button_is_enabled(button):
                return "unchanged"
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            if not button.is_displayed():
                return False
            button.click()
            return "submitted"

        try:
            if not wait_until_idle(self.driver, Constants.WEBFLOW_TIMEOUT):
                _logger.error("WebFlow is still busy before Save")
                return False
            outcome = WebDriverWait(
                self.driver, Constants.SAVE_TIMEOUT,
                ignored_exceptions=(ElementClickInterceptedException, StaleElementReferenceException),
            ).until(submit)
        except TimeoutException:
            _logger.exception("Save did not become available before the timeout")
            return False
        if outcome == "unchanged":
            _logger.info("Save is disabled; no changes to save")
            return True
        if not self._saved_toast_shown():
            return False
        return run_step(
            _logger, "Collapse the job information after Save",
            Information(self.driver).collapse_job_information,
        )

    def _saved_toast_shown(self) -> bool:
        def severity(driver):
            for toast in driver.find_elements(By.CSS_SELECTOR, Constants.TOAST_MESSAGE_CSS):
                found = toast_severity(toast.get_attribute("class"))
                text = " ".join((toast.text or "").split())
                if found == "error" or (found == "success" and "saved successfully" in text.casefold()):
                    return found, text
            return False

        try:
            found, text = WebDriverWait(self.driver, Constants.SAVE_TIMEOUT).until(severity)
        except TimeoutException:
            _logger.error("WebFlow showed no confirmation after Save")
            return False
        if found == "error":
            _logger.error("WebFlow could not save: %s", text)
            return False
        if "saved successfully" not in text.casefold():
            _logger.error("WebFlow showed an unexpected save confirmation: %s", text)
            return False
        _logger.info("WebFlow confirmed the save: %s", text)
        return True

    def accept(self) -> bool:
        button = self.get_button_by_text("accept")
        if button is None:
            return False
        if "disabled" in button.get_attribute("class"):
            return True
        button.click()
        return wait_until_idle(self.driver)
