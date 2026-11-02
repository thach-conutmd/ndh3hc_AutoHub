"""Upload calibration files to the Request Files list of a WebFlow job."""
from __future__ import annotations

import logging
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import Constants
from .components import TabLink, button_is_enabled, wait_until_idle

_logger = logging.getLogger(__name__)


class FilesTab:
    def __init__(self, driver):
        self.driver = driver
        self._tab = TabLink(driver, Constants.FILES_TAB_XPATH)

    def select_files_tab(self) -> bool:
        return self._tab.select()

    def upload_calibration_hex(self, file_path: str) -> bool:
        path = Path(file_path)
        if path.suffix.casefold() != ".hex" or not path.is_file():
            _logger.error("Calibration HEX file is missing or invalid: %s", path)
            return False

        try:
            request_files = self.driver.find_element(By.ID, "REQUEST")
            rows = request_files.find_elements(By.CSS_SELECTOR, "tbody tr")
            target = None
            for item in rows:
                cells = item.find_elements(By.CSS_SELECTOR, "td")
                if cells and cells[0].text.strip() == "Calibration file":
                    target = item, cells
                    break
            if target is None:
                _logger.error("WebFlow Request Files has no Calibration file row")
                return False
            row, cells = target
            if len(cells) >= 3 and path.name in cells[2].text:
                _logger.info("Calibration HEX file %s is already attached", path.name)
                return True

            control = request_files.find_element(By.XPATH, "./ancestor::app-filelistcontrol[1]")
            upload = control.find_element(By.CSS_SELECTOR, 'input[type="file"]')
            add_button = row.find_element(By.CSS_SELECTOR, 'button[name="btnFile"]')
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", add_button)
            WebDriverWait(self.driver, Constants.BODY_TIMEOUT).until(EC.element_to_be_clickable(add_button))
            if not button_is_enabled(add_button):
                _logger.error("Calibration file + button is disabled")
                return False
            # Run WebFlow's row-specific handler without opening an OS file dialog.
            self.driver.execute_script(
                "const input = arguments[0];"
                "input._autoHubPreventChooser = event => event.preventDefault();"
                "input.addEventListener('click', input._autoHubPreventChooser);",
                upload,
            )
            try:
                add_button.click()
            finally:
                self.driver.execute_script(
                    "const input = arguments[0];"
                    "input.removeEventListener('click', input._autoHubPreventChooser);"
                    "delete input._autoHubPreventChooser;",
                    upload,
                )
            upload.send_keys(str(path.resolve()))

            def uploaded(_driver):
                current_rows = request_files.find_elements(By.CSS_SELECTOR, "tbody tr")
                for current in current_rows:
                    cells = current.find_elements(By.CSS_SELECTOR, "td")
                    if len(cells) >= 3 and cells[0].text.strip() == "Calibration file":
                        return path.name in cells[2].text
                return False

            WebDriverWait(self.driver, Constants.WEBFLOW_TIMEOUT).until(uploaded)
            if not wait_until_idle(self.driver, Constants.WEBFLOW_TIMEOUT):
                _logger.error("WebFlow remained busy after uploading %s", path.name)
                return False
            _logger.info("Uploaded calibration HEX file %s", path.name)
            return True
        except Exception:
            _logger.exception("Could not upload calibration HEX file %s", path)
            return False
