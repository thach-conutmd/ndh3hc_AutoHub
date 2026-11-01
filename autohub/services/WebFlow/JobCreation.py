import logging
from typing import Callable

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from autohub.core.webflow_links import job_number

from . import Constants as Constants
from .components import select_dropdown, wait_for
from .dropdown import read_options
from .step_log import run_step

_logger = logging.getLogger(__name__)


class JobCreation:

    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.number_of_jobs = 0
        self.new_jobs_ids = []
    
    def is_job_creation_page(self) -> bool:
        try:
            wait_for(self.driver, By.CLASS_NAME, Constants.BODY_JOBCREATION_PAGE_CLASS, timeout=10)
            return True
        except Exception:
            _logger.debug("The job creation page is not shown", exc_info=True)
            return False

    def get_number_of_jobs(self) -> int:
        return self.number_of_jobs

    def get_new_jobs_ids(self) -> list:
        return self.new_jobs_ids

    def confirm_button(self):
        try:
            return wait_for(self.driver, By.CSS_SELECTOR, Constants.BODY_JOBCREATION_CONFIRM_BTN_CSS)
        except Exception:
            _logger.debug("No job creation confirm button", exc_info=True)
            return None

    def jobs_creation(self, ecu_generation: str, 
                           ecu_type: str , 
                           tool_version: str, 
                           routing: str, 
                           number_of_jobs: int,
                           brand: str = "Honda",
                           customer_group: str = "JAP", 
                           working_mode: str = "Honda_PreRun",
                           before_submit: Callable[[], None] | None = None) -> bool:
        self.number_of_jobs = 0
        self.new_jobs_ids = []

        for label, value, select in (
            ("ECU generation", ecu_generation, self.select_ecu_generation),
            ("brand", brand, self.select_brand),
            ("ECU type", ecu_type, self.select_ecu_type),
            ("customer group", customer_group, self.select_customer_group),
            ("working mode", working_mode, self.select_working_mode),
            ("tool version", tool_version, self.select_tool_version),
            ("routing", routing, self.select_routing),
            ("number of jobs", number_of_jobs, self.select_number_of_jobs),
        ):
            if value:
                if not run_step(_logger, f"Job creation form: select {label} = {value}", select, value):
                    _logger.error("WebFlow job creation stopped: could not select %s = %s", label, value)
                    return False

        if before_submit is not None:
            before_submit()
        if not run_step(_logger, "Confirm the job creation", self._confirm_creation):
            return False

        success = run_step(_logger, "Wait for WebFlow to finish creating the jobs", self._wait_until_jobs_created)

        if success:
            self.number_of_jobs = number_of_jobs

            current_url = self.driver.current_url
            current_id = job_number(current_url)

            for _ in range(number_of_jobs):
                self.new_jobs_ids.append(str(current_id))
                current_id += 1
            _logger.info("WebFlow created job id(s): %s (url %s)", ", ".join(self.new_jobs_ids), current_url)
        else:
            _logger.error("WebFlow job creation did not succeed")

        return success

    def _confirm_creation(self) -> bool:
        def click_confirm(driver) -> bool:
            button = EC.element_to_be_clickable(
                (By.CSS_SELECTOR, Constants.BODY_JOBCREATION_CONFIRM_BTN_CSS)
            )(driver)
            if not button:
                return False
            button.click()
            return True

        try:
            # Angular can replace the button between lookup and click. Only a rejected
            # stale click is retried; a successful submission must never be repeated.
            WebDriverWait(
                self.driver, Constants.BODY_TIMEOUT,
                ignored_exceptions=(StaleElementReferenceException,),
            ).until(click_confirm)
            return True
        except TimeoutException:
            _logger.exception("Could not click the WebFlow job creation confirm button")
            return False

    def _wait_until_jobs_created(self) -> bool:
        """Creating several jobs is slow: wait (up to WEBFLOW_TIMEOUT) for the spinner to go and the URL to end in the new job number."""
        def done(driver) -> bool:
            busy = driver.find_elements(By.CLASS_NAME, Constants.WEBFLOW_ACTIVITY_INDICATOR_CLASS)
            return not any(element.is_displayed() for element in busy) and job_number(driver.current_url) is not None

        try:
            WebDriverWait(
                self.driver, Constants.WEBFLOW_TIMEOUT,
                ignored_exceptions=(StaleElementReferenceException,),
            ).until(done)
            return True
        except TimeoutException:
            _logger.error(
                "WebFlow did not finish creating the jobs within %ds (page: %s)", Constants.WEBFLOW_TIMEOUT, self.driver.current_url
            )
            return False

    def get_options(self) -> dict | None:
        return read_options(self.driver, Constants.BODY_JOBCREATION_OPTIONS_CLASS, Constants.BODY_JOBCREATION_OPTIONS_MAX_ITEMS)

    def _select(self, title_xpath: str, value: str, similar: bool = False) -> bool:
        return select_dropdown(
            self.driver, title_xpath, Constants.BODY_JOBCREATION_BTN_CSS, value, self.get_options, similar=similar
        )

    def select_ecu_generation(self, ecu_generation: str = "---") -> bool:
        return self._select(Constants.BODY_JOBCREATION_ECUGEN_XPATH, ecu_generation)

    def select_brand(self, brand: str = "---") -> bool:
        return self._select(Constants.BODY_JOBCREATION_BRAND_XPATH, brand)

    def select_ecu_type(self, ecu_type: str = "---") -> bool:
        return self._select(Constants.BODY_JOBCREATION_ECUTYPE_XPATH, ecu_type)

    def select_customer_group(self, customer_group: str = "---") -> bool:
        return self._select(Constants.BODY_JOBCREATION_CUSTGRP_XPATH, customer_group)

    def select_working_mode(self, working_mode: str = "---") -> bool:
        return self._select(Constants.BODY_JOBCREATION_WRKMODE_XPATH, working_mode)

    def select_tool_version(self, tool_version: str = "---") -> bool:
        # Tool version labels carry a status suffix, e.g. "PD W0002" is offered as "PD W0002 (Productive)".
        return self._select(Constants.BODY_JOBCREATION_TOOLVER_XPATH, tool_version, similar=True)

    def select_routing(self, routing: str = "---") -> bool:
        return self._select(Constants.BODY_JOBCREATION_ROUTING_XPATH, routing)

    def select_number_of_jobs(self, number_of_jobs: int = 1) -> bool:
        # WebFlow labels the counts with a leading space (" 1", " 2", ...)
        return self._select(Constants.BODY_JOBCREATION_NUMBER_XPATH, f" {number_of_jobs}")
