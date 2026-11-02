"""Upload calibration files to the Request Files list of a WebFlow job."""
from __future__ import annotations

import logging
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from . import Constants
from .components import TabLink, wait_until_idle

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

            row.click()
            upload = request_files.find_element(By.CSS_SELECTOR, 'input[type="file"]')
            self.driver.execute_script(
                "arguments[0].style.display = 'block'; arguments[0].style.visibility = 'visible';", upload
            )
            try:
                upload.send_keys(str(path.resolve()))
            finally:
                self.driver.execute_script(
                    "arguments[0].style.display = 'none'; arguments[0].style.visibility = 'hidden';", upload
                )

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
