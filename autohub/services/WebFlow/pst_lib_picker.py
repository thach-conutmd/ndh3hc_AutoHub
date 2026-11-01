"""Select a unique PST library entry using the recorded PVER dialog."""
import logging

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from . import Constants
from .components import Section
from .save_confirmation import SaveBeforeImportConfirmation

_logger = logging.getLogger(__name__)


class PstLibPicker:
    def __init__(self, driver: WebDriver, section: Section):
        self.driver = driver
        self.section = section

    def select(self, pver: str) -> bool:
        pver = pver.strip()
        if not pver:
            _logger.error("Cannot select PST_Lib without a PVER")
            return False
        parts = pver.split("_", 2)
        search_value = f"{parts[0]}_{parts[1]}/{parts[2]}" if "/" not in pver and len(parts) == 3 else pver
        expected = pver.partition(";")[0].replace("/", "_").casefold()
        if not self.section.expand():
            return False
        try:
            button = WebDriverWait(self.driver, Constants.BODY_TIMEOUT).until(
                lambda _driver: self.section.body().find_element(
                    By.XPATH, './/button[.//span[normalize-space(.)="Pick PST_Lib"]]'
                )
            )
            if not button.is_displayed() or not button.is_enabled():
                _logger.error("Pick PST_Lib is not available")
                return False
            button.click()
            confirmation = SaveBeforeImportConfirmation(self.driver, "Pick PST_Lib")

            def selection_dialog(_driver):
                if confirmation.pending():
                    return False
                for dialog in self.driver.find_elements(By.CSS_SELECTOR, '[role="dialog"]'):
                    if dialog.is_displayed() and "PST_Lib and PVER selection" in dialog.text:
                        return dialog
                return False

            dialog = WebDriverWait(
                self.driver, Constants.WEBFLOW_TIMEOUT,
                ignored_exceptions=(StaleElementReferenceException,),
            ).until(selection_dialog)
            search = dialog.find_element(
                By.CSS_SELECTOR, 'input[placeholder^="Search for Program identification"]'
            )
            search.clear()
            search.send_keys(search_value)
            search.send_keys(Keys.ENTER)

            def matching_rows(_driver):
                rows = []
                for row in dialog.find_elements(By.CSS_SELECTOR, "table tbody tr"):
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if (
                        cells and row.is_displayed()
                        and cells[0].text.strip().partition(";")[0].replace("/", "_").casefold() == expected
                    ):
                        rows.append(row)
                return rows or False

            rows = WebDriverWait(
                self.driver, Constants.WEBFLOW_TIMEOUT,
                ignored_exceptions=(StaleElementReferenceException,),
            ).until(matching_rows)
            if len(rows) != 1:
                _logger.error(
                    "Expected one PST_Lib Program Identification matching PVER %r, found %d", pver, len(rows),
                )
                return False
            rows[0].click()

            def enabled_pick(_driver):
                for current_dialog in self.driver.find_elements(By.CSS_SELECTOR, '[role="dialog"]'):
                    if "PST_Lib and PVER selection" not in current_dialog.text:
                        continue
                    pick_button = current_dialog.find_element(
                        By.XPATH, './/button[.//span[normalize-space(.)="Pick PST"]]'
                    )
                    if pick_button.is_displayed() and pick_button.is_enabled():
                        return pick_button
                return False

            pick = WebDriverWait(self.driver, Constants.BODY_TIMEOUT).until(enabled_pick)
            identification = rows[0].find_elements(By.TAG_NAME, "td")[0].text.strip()
            pick.click()

            def dialog_closed(_driver):
                if confirmation.pending():
                    return False
                try:
                    return not dialog.is_displayed()
                except StaleElementReferenceException:
                    return True

            WebDriverWait(self.driver, Constants.WEBFLOW_TIMEOUT).until(dialog_closed)
            _logger.info("Selected PST_Lib Program Identification %r for PVER %s", identification, pver)
            return True
        except Exception:
            _logger.exception("Could not select PST_Lib for PVER %r", pver)
            return False
