"""Sheet-backed controls in the General tab's collapsible panels."""
import logging

from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from autohub.core.webflow_fields import HARDWARE_FIELDS
from autohub.core.webflow_options import resolve_option_values

from . import Constants
from .components import Section, checkbox_value, pause, scroll_into_view_if_hidden, wait_until_idle
from .number_import import NumberImport
from .pst_lib_picker import PstLibPicker

_logger = logging.getLogger(__name__)
_FIELDS = {key: (label, kind) for _, key, label, kind in HARDWARE_FIELDS}
_FIELDS["software_name"] = ("Software name", "text")
_FIELDS.update({
    "change_engineer": ("Change engineer ( Outlook Display Name )", "text"),
    "cost_allocation": ("Cost allocation", "text"),
    "change_reason": ("Change Reason", "multi"),
    "ecr_notes": ("ECR notes", "textarea"),
})
_PANEL_FIELDS = {
    "General info": (
        "vehicle_model", "engine_family", "power", "emission_norm", "immobilizer",
        "transmission", "displacement", "market", "model_year", "cylinders",
    ),
    "Bosch logistic info": (
        "project_number_first", "project_number_second", "hardware_part_number",
        "development_number", "ecu_hardware_name",
    ),
    "Customer logistic info": (
        "customer_order_number", "customer_hardware_part_number",
        "customer_software_part_number", "car", "customer_name",
    ),
    "Ident Numbers": ("lead_plant", "program_version", "software_part_number", "software_name", "data_version"),
    "ECR Information": ("ecr_number", "change_engineer", "cost_allocation", "change_reason", "ecr_notes"),
    "Classification": (),
}
_FIELD_PANELS = {key: panel for panel, keys in _PANEL_FIELDS.items() for key in keys}


class HardwareFields:
    def __init__(self, driver):
        self.driver = driver
        self.imported_software_part_number = ""
        self.imported_ecr_number = ""
        self.sections = {
            panel: Section(driver, f'//span[normalize-space(.)="{panel}"]', 'div[style^="display:"]')
            for panel in _PANEL_FIELDS
        }

    def prepare_classification(self) -> bool:
        section = self.sections["Classification"]
        if not section.fill_input(
            'input[placeholder="Has to match to number of variants (Calibration hex files) selected in input files"]', "1"
        ):
            return False
        try:
            for label in ("Time limitation required?", "Successor to Time Limited Delivery ECU?"):
                form = section.body().find_element(
                    By.XPATH, f'.//div[contains(@class,"control-label") and normalize-space(.)="{label}"]/..'
                )
                for _ in range(3):
                    checkbox = form.find_element(By.CSS_SELECTOR, 'div[role="checkbox"]')
                    if checkbox_value(checkbox) is False:
                        break
                    if checkbox.get_attribute("aria-disabled") == "true":
                        _logger.error("Classification checkbox %s is disabled", label)
                        return False
                    checkbox.click()
                    pause()
                else:
                    _logger.error("Classification checkbox %s did not reach X (false)", label)
                    return False
                _logger.info("WebFlow %s = False (X)", label)
            _logger.info("WebFlow Number of variants = 1")
            return True
        except Exception:
            _logger.exception("Could not prepare Classification before Lead Plant")
            return False

    def _loaded_options(self, value: str) -> dict:
        def loaded(_driver):
            for panel in self.driver.find_elements(By.CSS_SELECTOR, ".p-dropdown-panel"):
                if not panel.is_displayed():
                    continue
                options = {
                    item.get_attribute("aria-label"): item
                    for item in panel.find_elements(By.CSS_SELECTOR, 'li[role="option"]')
                }
                if value in options:
                    return options
            return False

        return WebDriverWait(
            self.driver, Constants.WEBFLOW_TIMEOUT,
            ignored_exceptions=(StaleElementReferenceException,),
        ).until(loaded)

    def _select_plant(self, form, value: str) -> bool:
        control = form.find_element(By.CSS_SELECTOR, "p-dropdown")
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", control)
        trigger = control.find_element(By.CSS_SELECTOR, ".p-dropdown-trigger")
        WebDriverWait(self.driver, Constants.BODY_TIMEOUT).until(EC.element_to_be_clickable(trigger))
        current = control.find_element(By.CSS_SELECTOR, '[role="combobox"]')
        if current.get_attribute("aria-label") == value:
            return True
        trigger.click()
        options = self._loaded_options(value)
        option = options[value]
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'nearest'});", option)
        WebDriverWait(self.driver, Constants.BODY_TIMEOUT).until(EC.element_to_be_clickable(option))
        option.click()
        wait_until_idle(self.driver, Constants.WEBFLOW_TIMEOUT)

        def selected(_driver):
            return form.find_element(By.CSS_SELECTOR, 'p-dropdown [role="combobox"]').get_attribute("aria-label") == value

        WebDriverWait(
            self.driver, Constants.WEBFLOW_TIMEOUT,
            ignored_exceptions=(StaleElementReferenceException,),
        ).until(selected)
        _logger.info("WebFlow Lead Plant = %s", value)
        return True

    def import_software_part_number(self) -> bool:
        self.imported_software_part_number = ""
        section = self.sections["Ident Numbers"]
        if not section.expand():
            return False
        try:
            value = self._import_number("Ident Numbers", "Import from pool", "Software part number")
            self.imported_software_part_number = value
            wait_until_idle(self.driver, Constants.WEBFLOW_TIMEOUT)
            _logger.info("WebFlow imported Software part number = %s", value)
            for key in ("software_name", "customer_software_part_number"):
                if not self.fill(key, value):
                    _logger.error("Could not copy imported software part number %s into %s", value, key)
                    return False
                _logger.info("WebFlow %s = %s", _FIELDS[key][0], value)
            return True
        except Exception:
            _logger.exception("Could not import the software part number from pool")
            return False

    def import_from_race(self) -> bool:
        section = self.sections["Classification"]
        if not section.expand():
            _logger.error("Could not open Classification to import from Race")
            return False
        try:
            def available_button(_driver):
                button = section.body().find_element(
                    By.XPATH, './/button[.//span[normalize-space(.)="Import from Race"]]'
                )
                return button if button.is_displayed() and button.is_enabled() else False

            button = WebDriverWait(self.driver, Constants.BODY_TIMEOUT).until(available_button)
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            button.click()
            if not wait_until_idle(self.driver, Constants.WEBFLOW_TIMEOUT):
                _logger.error("WebFlow did not become idle after Import from Race")
                return False
            _logger.info("WebFlow Import from Race clicked after filling Hardware part number")
            return True
        except Exception:
            _logger.exception("Could not import from Race after filling Hardware part number")
            return False

    def pick_pst_lib(self, pver: str) -> bool:
        """Selects the unique Program Identification matching the sheet PVER, excluding its revision."""
        return PstLibPicker(self.driver, self.sections["Ident Numbers"]).select(pver)

    def fill(self, key: str, value: str) -> bool:
        label, kind = _FIELDS[key]
        section = self.sections[_FIELD_PANELS[key]]
        if not section.expand():
            return False
        title_xpath = f'.//div[contains(@class,"control-label") and normalize-space(.)="{label}"]'
        try:
            title = section.body().find_element(By.XPATH, title_xpath)
            form = title.find_element(By.XPATH, "..")
            if kind == "dropdown":
                return self._select_plant(form, value)
            if kind == "multi":
                return self._select_multiple(form, value, key)
            field = form.find_element(By.CSS_SELECTOR, "textarea" if kind == "textarea" else 'input[type="text"]')
            scroll_into_view_if_hidden(self.driver, field)
            if not field.is_enabled() or field.get_attribute("readonly") is not None:
                _logger.error("WebFlow field %s is read-only; requested %r", label, value)
                return False
            field.clear()
            field.send_keys(value)
            pause()
            return field.get_attribute("value") == value
        except Exception:
            _logger.exception("Could not fill WebFlow field %s = %r", label, value)
            return False

    def import_ecr(self) -> bool:
        self.imported_ecr_number = ""
        section = self.sections["ECR Information"]
        if not section.expand():
            return False
        try:
            self.imported_ecr_number = self._import_number("ECR Information", "ECR Import", "ECR number")
            _logger.info("WebFlow imported ECR number = %s", self.imported_ecr_number)
            return True
        except Exception:
            _logger.exception("Could not import ECR information")
            return False

    def _import_number(self, panel: str, button_label: str, field_label: str) -> str:
        return NumberImport(self.driver, self.sections[panel]).run(button_label, field_label)

    def _select_multiple(self, form, value: str, key: str = "") -> bool:
        control = form.find_element(By.CSS_SELECTOR, "p-multiselect")
        if control.get_attribute("ng-reflect-disabled") == "true":
            _logger.error("WebFlow multiselect is disabled; requested %r", value)
            return False
        control.find_element(By.CSS_SELECTOR, ".p-multiselect").click()
        try:
            panel = WebDriverWait(self.driver, Constants.BODY_TIMEOUT).until(
                lambda driver: next(
                    (el for el in driver.find_elements(By.CSS_SELECTOR, ".p-multiselect-panel") if el.is_displayed()),
                    False,
                )
            )
            items = panel.find_elements(By.CSS_SELECTOR, "li.p-multiselect-item")
            options = {(item.get_attribute("aria-label") or item.text): item for item in items}
            try:
                requested = resolve_option_values(key, value, options)
            except ValueError as error:
                _logger.error("%s", error)
                return False
            _logger.info("WebFlow %s: %r resolved to %s", key or "multiselect", value, sorted(requested))
            for name, item in options.items():
                selected = item.get_attribute("aria-selected") == "true"
                if selected != (name in requested):
                    item.click()
            return all((item.get_attribute("aria-selected") == "true") == (name in requested) for name, item in options.items())
        finally:
            control.find_element(By.CSS_SELECTOR, ".p-multiselect").click()
            wait_until_idle(self.driver)
