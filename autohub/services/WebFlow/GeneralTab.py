import logging
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import Constants as Constants
from .Actions import Actions, save_before_action
from .components import (
    Section,
    TabLink,
    checkbox_is_disabled,
    checkbox_value,
    click_count,
    select_dropdown,
)
from .dropdown import read_options
from .HardwareFields import HardwareFields
from .step_log import run_step

_logger = logging.getLogger(__name__)


# Kept under their historical names; the tri-state helpers are shared with the ECU tab.
_checkbox_value = checkbox_value
_checkbox_is_disabled = checkbox_is_disabled
_click_count = click_count


class GeneralTab:

    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.skipped_fields: list[str] = []
        self._hardware = HardwareFields(driver)
        self._tab = TabLink(driver, Constants.GENERAL_TAB_XPATH)
        self._configurator_items = Section(
            driver, Constants.GENERAL_CONFIGURATOR_ITEMS_TITLE_XPATH, Constants.GENERAL_CONFIGURATOR_ITEMS_BODY_CSS
        )

    def is_general_tab(self) -> bool:
        return self._tab.is_selected()

    def fill_hardware_field(self, key: str, value: str) -> bool:
        if not self._hardware.fill(key, value):
            return False
        if key == "hardware_part_number":
            run_step(
                _logger, "Save the job before Import from Race",
                save_before_action, Actions(self.driver).save, "Import from Race",
            )
            return self._hardware.import_from_race()
        return True

    def import_software_part_number(self) -> bool:
        return self._hardware.import_software_part_number()

    def import_ecr(self) -> bool:
        return self._hardware.import_ecr()

    @property
    def imported_ecr_number(self) -> str:
        return self._hardware.imported_ecr_number

    def pick_pst_lib(self, project_version: str) -> bool:
        return self._hardware.pick_pst_lib(project_version)

    @property
    def imported_software_part_number(self) -> str:
        return self._hardware.imported_software_part_number

    def prepare_classification(self) -> bool:
        return self._hardware.prepare_classification()

    def select_general_tab(self) -> bool:
        return self._tab.select()

    def get_options(self) -> dict | None:
        return read_options(self.driver, Constants.GENERAL_TAB_OPTIONS_CLASS, Constants.GENERAL_TAB_OPTIONS_MAX_ITEMS)

    def is_configurator_items_expanded(self) -> bool:
        return self._configurator_items.is_expanded()

    def is_configurator_items_collapsed(self) -> bool:
        return self._configurator_items.is_collapsed()

    def expand_configurator_items(self) -> bool:
        return self._configurator_items.expand()

    def collapse_configurator_items(self) -> bool:
        return self._configurator_items.collapse()

    def _select(self, title_xpath: str, value: str) -> bool:
        if not self.expand_configurator_items():
            return False
        return select_dropdown(self.driver, title_xpath, Constants.GENERAL_TAB_BTN_CSS, value, self.get_options)

    def select_delivery_type(self, delivery_type: str = "") -> bool:
        return self._select(Constants.GENERAL_DELIVERY_TYPE_TITLE_XPATH, delivery_type)

    def select_release_class(self, release_class: str = "") -> bool:
        return self._select(Constants.GENERAL_RELEASE_CLASS_TITLE_XPATH, release_class)

    def select_release_scope(self, release_scope: str = "") -> bool:
        return self._select(Constants.GENERAL_RELEASE_SCOPE_TITLE_XPATH, release_scope)

    def select_limitations(self, limitations: str = "") -> bool:
        return self._select(Constants.GENERAL_LIMITATIONS_TITLE_XPATH, limitations)

    def _select_tristate_checkbox(self, title_xpath: str, checkbox_css: str, check: bool | None, label: str) -> bool:
        if check is None:
            check = False
        if not self.expand_configurator_items():
            return False
        try:
            title_element = WebDriverWait(self.driver, Constants.BODY_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, title_xpath))
            )
            form_element = title_element.find_element(By.XPATH, "..")
            checkbox_element = form_element.find_element(By.CSS_SELECTOR, checkbox_css)
            current = _checkbox_value(checkbox_element)
            if current is check:
                return True

            if _checkbox_is_disabled(form_element, checkbox_element):
                if current is None:
                    _logger.error("%s: WebFlow disabled the checkbox while it is blank", label)
                    return False
                warning = (
                    f"{label}: WebFlow disabled the control (current value {current!r}, "
                    f"requested {check!r}); the value was not changed."
                )
                self.skipped_fields.append(warning)
                _logger.warning(warning)
                return True

            for _ in range(3):
                checkbox_element.click()
                time.sleep(Constants.WEBFLOW_TIMEOUT_CSS)
                checkbox_element = form_element.find_element(By.CSS_SELECTOR, checkbox_css)
                current = _checkbox_value(checkbox_element)
                if current is check:
                    return True

            _logger.error("WebFlow checkbox %s did not reach %s (current value %r)", label, check, current)
            return False
        except Exception:
            _logger.exception("Could not set WebFlow checkbox %s", label)
            return False

    def select_safety_monitoring_sw(self, check: bool | None = None) -> bool:
        return self._select_tristate_checkbox(
            Constants.GENERAL_SAFETY_MONITORING_SW_BY_RB_TITLE_XPATH,
            Constants.GENERAL_SAFETY_MONITORING_SW_BY_RB_CHECKBOX_CSS,
            check,
            "Safety Monitoring SW by RB",
        )

    def select_safety_calibration_response(self, check: bool | None = None) -> bool:
        return self._select_tristate_checkbox(
            Constants.GENERAL_SAFETY_CALIBRATION_RESPONSIBILITY_TITLE_XPATH,
            Constants.GENERAL_SAFETY_CALIBRATION_RESPONSIBILITY_CHECKBOX_CSS,
            check,
            "Safety Calibration responsibility",
        )

    def select_bosch_cal_data_response(self, check: bool | None = None) -> bool:
        return self._select_tristate_checkbox(
            Constants.GENERAL_BOSCH_CAL_DATA_RESPONSIBILITY_TITLE_XPATH,
            Constants.GENERAL_BOSCH_CAL_DATA_RESPONSIBILITY_CHECKBOX_CSS,
            check,
            "Bosch calibration data responsibility",
        )

    def select_data_integration_response(self, check: bool | None = None) -> bool:
        return self._select_tristate_checkbox(
            Constants.GENERAL_DATA_INTEGRATION_RESPONSIBILITY_TITLE_XPATH,
            Constants.GENERAL_DATA_INTEGRATION_RESPONSIBILITY_CHECKBOX_CSS,
            check,
            "Data integration responsibility",
        )
