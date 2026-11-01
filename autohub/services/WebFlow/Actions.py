import logging
from typing import Callable

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from . import Constants as Constants
from .components import scroll_into_view_if_hidden, wait_for, wait_until_idle
from .toast import toast_severity

_logger = logging.getLogger(__name__)


def save_before_action(save: Callable[[], bool], action: str) -> bool:
    if not save():
        raise RuntimeError(f"Could not save the job before {action}; {action} was not started.")
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
        """Clicks Save and confirms its success toast; an error toast or no toast is a failure."""
        button = self.get_button_by_text("save")
        if button is None:
            return False
        if "disabled" in button.get_attribute("class"):
            return True
        button.click()
        return self._saved_toast_shown()

    def _saved_toast_shown(self) -> bool:
        def severity(driver):
            for toast in driver.find_elements(By.CSS_SELECTOR, Constants.TOAST_MESSAGE_CSS):
                found = toast_severity(toast.get_attribute("class"))
                if found in ("success", "error"):
                    return found, " ".join((toast.text or "").split())
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
