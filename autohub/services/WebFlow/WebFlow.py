"""WebFlow browser session: opens the dashboard, creates jobs and fills them from variant dicts."""
import logging
import time
from pathlib import Path
from urllib.parse import urlsplit
from typing import Callable

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from autohub.core.progress import ProgressCallback, no_progress

from . import Constants as Constants
from .Body import Body
from .browser import edge_service
from .components import wait_until_idle
from .job_filler import JobFiller
from .job_batch import JobBatch
from .SideMenuBar import SideMenuBar
from .step_log import set_step_observer
from .step_trace import StepTrace

_logger = logging.getLogger(__name__)


def _is_browser_error_page(driver) -> bool:
    return "ERR_UNEXPECTED" in driver.page_source


class WebFlow(webdriver.Edge):

    def __init__(
        self,
        driver_path: str = "",
        base_url: str = "https://rb-pde-int.bosch.com:8881/app/dashboard",
        trace_dir: str = "",
    ):
        _logger.info("Starting the Edge browser (driver path: %s, base URL: %s)", driver_path or "auto", base_url)
        self.driver_path = driver_path
        self.base_url = base_url

        super().__init__(service=edge_service(driver_path), options=Options())
        self.maximize_window()
        self.implicitly_wait(Constants.IMPLICIT_WAIT)

        self.side_menu_bar = SideMenuBar(self)
        self.body = Body(self)
        self.job_filler = JobFiller(self.side_menu_bar, self.body)
        self.general_options: dict[str, list[str]] = {}
        _logger.info("Edge browser started")
        if trace_dir:  # record the page after every step
            set_step_observer(StepTrace(self, Path(trace_dir)))

    def quit(self):
        # A second quit would send DELETE /session to a stopped driver and
        # make urllib3 retry against a refused port for several seconds.
        if getattr(self, "_closed", False):
            return
        self._closed = True
        set_step_observer(None)
        super().quit()

    def __exit__(self, exc_type, exc_val, exc_tb):
        _logger.info("Closing the browser")
        self.quit()

    def open_dashboard_page(self) -> bool:

        _logger.info("Opening the WebFlow dashboard: %s", self.base_url)
        self.get(self.base_url)

        number_attempts = 0
        while self.title != Constants.WEBFLOW_TITLE and number_attempts < Constants.WEBFLOW_MAX_ATTEMPTS:
            self.refresh()
            time.sleep(Constants.WEBFLOW_REFRESH_INTERVAL)
            number_attempts += 1
            _logger.info("Dashboard not ready (title %r), refreshed (attempt %d/%d)", self.title, number_attempts, Constants.WEBFLOW_MAX_ATTEMPTS)

        if self.title != Constants.WEBFLOW_TITLE:
            _logger.error("The WebFlow dashboard did not open after %d attempts", number_attempts)
            self.quit()
            return False

        WebDriverWait(self, Constants.WEBFLOW_TIMEOUT).until(
            EC.invisibility_of_element_located((By.CLASS_NAME, Constants.WEBFLOW_LOADING_SCREEN_CLASS))
        )

        wait_until_idle(self)

        _logger.info("The WebFlow dashboard is open")
        return True

    def job_url(self, job_id: str) -> str:
        url = urlsplit(self.base_url)
        return f"{url.scheme}://{url.netloc}/app/ShowJob/{job_id}"

    def open_job(self, job_id: str) -> bool:
        url = self.job_url(job_id)
        _logger.info("Opening job %s: %s", job_id, url)
        try:
            self.get(url)
            for attempt in range(Constants.WEBFLOW_MAX_ATTEMPTS):
                if not _is_browser_error_page(self):
                    break
                _logger.warning(
                    "Edge showed ERR_UNEXPECTED while opening job %s; refreshing (attempt %d/%d)",
                    job_id, attempt + 1, Constants.WEBFLOW_MAX_ATTEMPTS,
                )
                self.refresh()
                time.sleep(Constants.WEBFLOW_REFRESH_INTERVAL)
            if _is_browser_error_page(self):
                _logger.error(
                    "Edge still shows ERR_UNEXPECTED after %d refresh attempts for job %s",
                    Constants.WEBFLOW_MAX_ATTEMPTS, job_id,
                )
                self.quit()
                return False
            WebDriverWait(self, Constants.WEBFLOW_TIMEOUT).until(
                EC.title_is(Constants.WEBFLOW_TITLE)
            )
            WebDriverWait(self, Constants.WEBFLOW_TIMEOUT).until(
                EC.invisibility_of_element_located((By.CLASS_NAME, Constants.WEBFLOW_LOADING_SCREEN_CLASS))
            )
            if not wait_until_idle(self):
                _logger.error("Job %s is still busy", job_id)
                return False
            WebDriverWait(self, Constants.WEBFLOW_TIMEOUT).until(
                EC.visibility_of_element_located((By.XPATH, Constants.GENERAL_TAB_XPATH))
            )
            return True
        except Exception:
            _logger.exception("Job %s did not finish loading", job_id)
            return False

    def create_and_fill_jobs(
        self,
        variants: list,
        tool_version: str,
        routing: str,
        brand: str = "Honda",
        customer_group: str = "JAP",
        working_mode: str = "Honda_PreRun",
        progress: ProgressCallback = no_progress,
        state: dict | None = None,
        checkpoint: Callable[[], None] | None = None,
    ) -> list:
        checkpoint = checkpoint or (lambda: None)
        self.job_filler.checkpoint = checkpoint
        batch = JobBatch(
            self.body.job_creation, self.open_dashboard_page, self.side_menu_bar.click_new_job,
            self.open_job, self._fill_job, self.job_url, self.quit, _logger,
            max_jobs_per_creation=Constants.BODY_JOBCREATION_MAX_JOBS,
        )
        results = batch.run(variants, tool_version, routing, customer_group, working_mode, progress, state, checkpoint)
        self.general_options = self.body.tab.generaltab.general_options
        return results

    def _fill_job(self, variant: dict) -> list[str]:
        return self.job_filler.fill(variant)
