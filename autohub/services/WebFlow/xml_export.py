"""Download Export XML through the existing authenticated WebFlow browser."""
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from . import Constants
from .components import button_is_enabled, wait_for, wait_until_idle

MAX_EXPORT_BYTES = 10 * 1024 * 1024
_logger = logging.getLogger(__name__)


def export_xml(driver) -> bytes:
    """Click once and wait for a complete download; never reuse an earlier job's file."""
    if not wait_until_idle(driver, Constants.WEBFLOW_TIMEOUT):
        raise RuntimeError("WebFlow is busy before Export XML.")
    with TemporaryDirectory(prefix="autohub-webflow-export-") as directory:
        try:
            return _download(driver, directory)
        except Exception:
            # Stop Chromium's downloader before cleaning up files it may still hold on Windows.
            try:
                driver.quit()
            except Exception:
                _logger.exception("Could not stop the failed WebFlow XML downloader")
            raise


def _download(driver, directory: str) -> bytes:
    driver.execute_cdp_cmd(
        "Browser.setDownloadBehavior",
        {"behavior": "allow", "downloadPath": directory},
    )

    def action(_driver):
        ribbon = wait_for(driver, By.CLASS_NAME, Constants.BODY_ACTION_RIBBON_CLASS)
        button = ribbon.find_element(
            By.XPATH,
            './/div[contains(concat(" ", normalize-space(@class), " "), " action-tile ")]'
            '[./span[normalize-space(.)="Export XML"]]',
        )
        return button if button.is_displayed() and button_is_enabled(button) else False

    try:
        button = WebDriverWait(
            driver, Constants.BODY_TIMEOUT, ignored_exceptions=(StaleElementReferenceException,),
        ).until(action)
    except TimeoutException as error:
        raise RuntimeError("Export XML action is missing or disabled.") from error
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
    button.click()
    last_size = None

    def downloaded(_driver):
        nonlocal last_size
        files = [path for path in Path(directory).iterdir() if path.is_file()]
        if any(path.suffix.lower() in (".crdownload", ".tmp", ".partial") for path in files):
            last_size = None
            return False
        if not files:
            return False
        if len(files) != 1:
            raise RuntimeError("Export XML produced multiple files; download is ambiguous.")
        path = files[0]
        size = path.stat().st_size
        if size > MAX_EXPORT_BYTES:
            raise RuntimeError("Export XML exceeds the 10 MiB limit.")
        if not size or size != last_size:
            last_size = size
            return False
        return path

    try:
        path = WebDriverWait(driver, Constants.WEBFLOW_TIMEOUT, poll_frequency=0.2).until(downloaded)
    except TimeoutException as error:
        raise RuntimeError("Export XML download timed out or did not complete.") from error
    with path.open("rb") as source:
        data = source.read(MAX_EXPORT_BYTES + 1)
    if len(data) > MAX_EXPORT_BYTES:
        raise RuntimeError("Export XML exceeds the 10 MiB limit.")
    return data
