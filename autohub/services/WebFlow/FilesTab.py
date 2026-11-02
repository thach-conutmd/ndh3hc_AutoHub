"""Read Execution Files metadata and upload calibration files to a WebFlow job."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from autohub.core.checksums import crc32_file, normalize_crc32

from . import Constants
from .components import TabLink, button_is_enabled, wait_until_idle

_logger = logging.getLogger(__name__)


class FilesTab:
    def __init__(self, driver):
        self.driver = driver
        self._tab = TabLink(driver, Constants.FILES_TAB_XPATH)

    def select_files_tab(self) -> bool:
        return self._tab.select()

    def container_crc32(self, filename: str) -> str:
        _, _, crc_column, cells = self._execution_file(filename)
        try:
            checksum = normalize_crc32(cells[crc_column].text)
        except ValueError:
            _logger.warning(
                "WebFlow returned an invalid CRC32 for %s; calculating it from the downloaded file", filename
            )
            checksum = ""
        if checksum:
            return checksum
        _logger.info("WebFlow has no CRC32 for %s; downloading it to calculate CRC32", filename)
        return self._download_container_crc32(filename)

    def _execution_file(self, filename: str):
        execution = self.driver.find_element(By.ID, "EXECUTION")
        table = execution.find_element(By.CSS_SELECTOR, "table")
        headers = table.find_elements(By.CSS_SELECTOR, "thead th")
        labels = [header.text.strip().casefold() for header in headers]
        try:
            file_column = labels.index("file")
            crc_column = labels.index("crc32")
        except ValueError as error:
            raise RuntimeError("WebFlow Execution Files table is missing its File or CRC32 column.") from error
        rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
        wanted = Path(filename.replace("\\", "/")).name.casefold()
        for row in rows:
            cells = row.find_elements(By.CSS_SELECTOR, "td")
            if len(cells) <= max(file_column, crc_column):
                continue
            names = {
                Path(value.strip().replace("\\", "/")).name.casefold()
                for value in cells[file_column].text.splitlines()
                if value.strip()
            }
            if wanted in names:
                return row, file_column, crc_column, cells
        raise RuntimeError(f"WebFlow Execution Files has no file named {Path(filename).name}.")

    def _download_container_crc32(self, filename: str) -> str:
        with tempfile.TemporaryDirectory(prefix="autohub-container-") as directory:
            self.driver.execute_cdp_cmd(
                "Browser.setDownloadBehavior",
                {"behavior": "allow", "downloadPath": directory},
            )
            row, file_column, _, _ = self._execution_file(filename)
            cell = row.find_elements(By.CSS_SELECTOR, "td")[file_column]
            links = cell.find_elements(By.CSS_SELECTOR, "a:not(.disable-link)")
            (links[0] if links else cell).click()
            last_size = None

            def downloaded(_driver):
                nonlocal last_size
                files = [path for path in Path(directory).iterdir() if path.is_file()]
                if any(path.suffix.casefold() in (".crdownload", ".tmp", ".partial") for path in files):
                    last_size = None
                    return False
                if not files:
                    return False
                if len(files) != 1:
                    raise RuntimeError(f"Downloading {filename} produced multiple files.")
                path = files[0]
                size = path.stat().st_size
                if not size or size != last_size:
                    last_size = size
                    return False
                return path

            try:
                path = WebDriverWait(self.driver, Constants.WEBFLOW_TIMEOUT, poll_frequency=0.2).until(downloaded)
            except TimeoutException as error:
                raise RuntimeError(f"Could not download {filename} from WebFlow to calculate its CRC32.") from error
            return crc32_file(path)

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
