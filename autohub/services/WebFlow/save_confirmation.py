"""Confirm only the known save-before-import warning, once per action."""
import logging

from selenium.webdriver.common.by import By

_logger = logging.getLogger(__name__)


class SaveBeforeImportConfirmation:
    def __init__(self, driver, action: str):
        self.driver = driver
        self.action = action
        self.confirmed = False

    def pending(self) -> bool:
        for dialog in self.driver.find_elements(By.CSS_SELECTOR, '[role="dialog"], [role="alertdialog"]'):
            if not dialog.is_displayed():
                continue
            text = " ".join(dialog.text.split()).casefold()
            if "data filled in by you will be saved before import." not in text:
                continue
            if not self.confirmed:
                yes = dialog.find_element(
                    By.XPATH, './/button[normalize-space(.)="Yes" or .//span[normalize-space(.)="Yes"]]'
                )
                if yes.is_displayed() and yes.is_enabled():
                    self.confirmed = True
                    yes.click()
                    _logger.info("Confirmed saving changes before %s: Yes", self.action)
            return True
        return False
