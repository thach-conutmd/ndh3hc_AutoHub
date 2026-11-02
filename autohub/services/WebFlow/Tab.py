from selenium.webdriver.remote.webdriver import WebDriver

from .CustomerTab import CustomerTab
from .ECUTab import ECUTab
from .FilesTab import FilesTab
from .GeneralTab import GeneralTab


class Tab:
    """The General / ECU / Customer tabs of an opened job."""

    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.generaltab = GeneralTab(self.driver)
        self.ecutab = ECUTab(self.driver)
        self.customertab = CustomerTab(self.driver)
        self.filestab = FilesTab(self.driver)
