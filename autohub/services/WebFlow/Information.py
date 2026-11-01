from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from . import Constants as Constants
from .components import Section, wait_until_idle


class Information:

    def __init__(self, driver: WebDriver):
        self.driver = driver
        self._job_information = Section(
            driver, Constants.BODY_INFORMATION_TITLE_XPATH, Constants.BODY_INFORMATION_BODY_CSS, scroll=False
        )

    def is_job_information_expanded(self) -> bool:
        return self._job_information.is_expanded()

    # Unlike the tab sections, these report whether they clicked (False: nothing to do) and let a
    # missing header raise.
    def expand_job_information(self) -> bool:
        if self.is_job_information_expanded():
            return False
        self._job_information.toggle()
        return True

    def collapse_job_information(self) -> bool:
        if not wait_until_idle(self.driver, Constants.WEBFLOW_TIMEOUT):
            return False
        if not self.is_job_information_expanded():
            return True
        self._job_information.toggle()
        WebDriverWait(self.driver, Constants.BODY_TIMEOUT).until(
            lambda _driver: self._job_information.is_collapsed()
        )
        return True
