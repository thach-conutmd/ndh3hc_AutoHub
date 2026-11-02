import logging

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from . import Constants as Constants
from .components import (
    Section,
    TabLink,
    checkbox_icon_value,
    checkbox_is_disabled,
    pause,
    select_dropdown,
    wait_for,
)
from .dropdown import read_options

_logger = logging.getLogger(__name__)

# Each click moves the LCTVorb checkbox one step along this cycle.
_LCTVORB_CYCLE = (None, True, False)


class ECUTab:

    def __init__(self, driver: WebDriver):
        self.driver = driver
        self._tab = TabLink(driver, Constants.ECU_TAB_XPATH)
        self._fsw_cnt_parameters = Section(
            driver, Constants.ECU_FSW_CNT_SPECIFIC_PARAMS_TITLE_XPATH, Constants.ECU_FSW_CNT_SPECIFIC_PARAMS_BODY_CSS
        )
        self._ecu_parameters = Section(
            driver, Constants.ECU_SPECIFIC_PARAMS_TITLE_XPATH, Constants.ECU_SPECIFIC_PARAMS_BODY_CSS
        )

    def is_ecu_tab(self) -> bool:
        return self._tab.is_selected()

    def select_ecu_tab(self) -> bool:
        return self._tab.select()

    def is_fsw_cnt_specific_parameters_expanded(self) -> bool:
        return self._fsw_cnt_parameters.is_expanded()

    def is_fsw_cnt_specific_parameters_collapsed(self) -> bool:
        return self._fsw_cnt_parameters.is_collapsed()

    def expand_fsw_cnt_specific_parameters(self) -> bool:
        return self._fsw_cnt_parameters.expand()

    def collapse_fsw_cnt_specific_parameters(self) -> bool:
        return self._fsw_cnt_parameters.collapse()

    def fill_indi_spec(self, data: str) -> bool:
        return self._fsw_cnt_parameters.fill_input(Constants.ECU_INDI_SPEC_INPUT_CSS_SELECTOR, data)

    def fill_family_name(self, data: str) -> bool:
        return self._fsw_cnt_parameters.fill_input(Constants.ECU_FAM_NAME_INPUT_CSS_SELECTOR, data)

    def fill_project_version(self, data: str) -> bool:
        return self._fsw_cnt_parameters.fill_input(Constants.ECU_FSWID_PROJECT_VERSION_INPUT_CSS_SELECTOR, data)

    def fill_program_version(self, data: str) -> bool:
        return self._fsw_cnt_parameters.fill_input(Constants.ECU_FSWID_PROGRAM_VERSION_INPUT_CSS_SELECTOR, data)

    def is_ecu_specific_parameters_expanded(self) -> bool:
        return self._ecu_parameters.is_expanded()

    def is_ecu_specific_parameters_collapsed(self) -> bool:
        return self._ecu_parameters.is_collapsed()

    def expand_ecu_specific_parameters(self) -> bool:
        return self._ecu_parameters.expand()

    def collapse_ecu_specific_parameters(self) -> bool:
        return self._ecu_parameters.collapse()

    def get_options(self) -> dict | None:
        return read_options(self.driver, Constants.ECU_TAB_OPTIONS_CLASS, Constants.ECU_TAB_OPTIONS_MAX_ITEMS)

    def _select(self, title_xpath: str, value: str) -> bool:
        if not self.expand_ecu_specific_parameters():
            return False
        return select_dropdown(self.driver, title_xpath, Constants.ECU_TAB_BTN_CSS, value, self.get_options)

    def select_tp_level(self, tp_level: str = "---") -> bool:
        # The sheet uses TP3 / TP9; WebFlow's corresponding option labels are 3 / 9.
        value = tp_level[2:] if tp_level.upper().startswith("TP") else tp_level
        return self._select(Constants.ECU_TP_LEVEL_TITLE_XPATH, value)

    def select_diagnostic_protocol(self, diagnostic_protocol: str = "---") -> bool:
        return self._select(Constants.ECU_DIAGNOSTIC_PROTOCOL_TITLE_XPATH, diagnostic_protocol)

    def select_project_lctvorb(self, check: bool | None = None) -> bool:
        """Cycles the tri-state checkbox to ``check``; its state is read from the PrimeNG icons only."""
        self.expand_ecu_specific_parameters()
        try:
            title_element = wait_for(self.driver, By.XPATH, Constants.ECU_PROJECT_LCTVORB_TITLE_XPATH)
            checkbox_element = title_element.find_element(By.XPATH, "..").find_element(
                By.CSS_SELECTOR, Constants.ECU_PROJECT_LCTVORB_CHECKBOX_CSS
            )
            if checkbox_is_disabled(checkbox_element, checkbox_element):
                _logger.warning("WebFlow Project with LCTVorb checkbox is disabled; skipping")
                return True
            current = checkbox_icon_value(checkbox_element)
            target = None if check is None else bool(check)
            clicks = (_LCTVORB_CYCLE.index(target) - _LCTVORB_CYCLE.index(current)) % len(_LCTVORB_CYCLE)
            for _ in range(clicks):
                checkbox_element.click()
                pause()
            return True
        except Exception:
            _logger.warning("Could not set the Project with LCTVorb checkbox", exc_info=True)
            return False
