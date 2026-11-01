"""Single-submit number import and its known save-before-import confirmation."""
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from . import Constants
from .components import Section, button_is_enabled
from .save_confirmation import SaveBeforeImportConfirmation

class NumberImport:
    def __init__(self, driver: WebDriver, section: Section):
        self.driver = driver
        self.section = section

    def run(self, button_label: str, field_label: str) -> str:
        def available_button(_driver):
            button = self.section.body().find_element(
                By.XPATH, f'.//button[.//span[normalize-space(.)="{button_label}"]]'
            )
            return button if button.is_displayed() and button_is_enabled(button) else False

        button = WebDriverWait(self.driver, Constants.BODY_TIMEOUT).until(available_button)
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        if not button_is_enabled(button):
            raise RuntimeError(f"{button_label} is disabled; import was not started.")
        # Allocating a number may have server-side effects: never retry the click.
        button.click()
        confirmation = SaveBeforeImportConfirmation(self.driver, button_label)

        def imported(_driver):
            if confirmation.pending():
                return False
            field = self.section.body().find_element(
                By.XPATH,
                './/div[contains(@class,"form-group") and '
                f'./div[contains(@class,"control-label") and normalize-space(.)="{field_label}"]]//input',
            )
            value = (field.get_attribute("value") or "").strip()
            return value if value and value not in ("0", "---") else False

        return WebDriverWait(
            self.driver, Constants.WEBFLOW_TIMEOUT,
            ignored_exceptions=(StaleElementReferenceException,),
        ).until(imported)
