"""Reusable WebFlow (PrimeNG) widgets shared by the page objects.

Every page object used to repeat the same Selenium code for a collapsible section, a drop-down,
a text input and a tab link. Each widget is written once here; the page objects only hold the
locators. Timeouts are read from ``Constants`` at call time so they can be changed (and patched
in tests) after the widgets are built.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import Constants

_logger = logging.getLogger(__name__)

OptionsReader = Callable[[], "dict | None"]


def wait_for(driver: Any, by: str, locator: str, timeout: float | None = None) -> Any:
    """The element once it is present; raises TimeoutException otherwise."""
    return WebDriverWait(driver, Constants.BODY_TIMEOUT if timeout is None else timeout).until(
        EC.presence_of_element_located((by, locator))
    )


def wait_until_idle(driver: Any, timeout: float | None = None) -> Any:
    """Waits until WebFlow's activity indicator is gone; returns the wait's result."""
    return WebDriverWait(driver, Constants.BODY_TIMEOUT if timeout is None else timeout).until(
        EC.invisibility_of_element_located((By.CLASS_NAME, Constants.WEBFLOW_ACTIVITY_INDICATOR_CLASS))
    )


def scroll_into_view_if_hidden(driver: Any, element: Any) -> None:
    if not element.is_displayed():
        driver.execute_script("arguments[0].scrollIntoView(true);", element)


def pause() -> None:
    """Gives WebFlow's CSS animation time to finish after a click."""
    time.sleep(Constants.WEBFLOW_TIMEOUT_CSS)


def select_dropdown(driver: Any, title_xpath: str, button_css: str, value: str, read_options: OptionsReader) -> bool:
    """Selects ``value`` in the drop-down next to the title; True if it is (or was already) chosen.

    Missing options or a value that does not stick are failures, never successful idle waits."""
    try:
        def button_element():
            title = wait_for(driver, By.XPATH, title_xpath)
            return title.find_element(By.XPATH, "..").find_element(By.CSS_SELECTOR, button_css)

        def xpath_literal(text: str) -> str:
            if "'" not in text:
                return "'" + text + "'"
            return 'concat(' + ', "\'", '.join("'" + part + "'" for part in text.split("'")) + ')'

        literal = xpath_literal(value)

        def selected(_driver):
            try:
                button_element().find_element(By.XPATH, f'.//span[text()={literal}]')
                return True
            except NoSuchElementException:
                if value != value.strip():
                    normalized_literal = xpath_literal(value.strip())
                    try:
                        button_element().find_element(
                            By.XPATH, f'.//span[normalize-space(text())={normalized_literal}]'
                        )
                        return True
                    except NoSuchElementException:
                        pass
                return False

        if selected(driver):
            return True
        button_element().click()
        if not wait_until_idle(driver):
            return False

        options = read_options()
        option = (options or {}).get(value)
        if option is None and options and value != value.strip():
            matches = [item for label, item in options.items() if label.strip() == value.strip()]
            if len(matches) == 1:
                option = matches[0]
        if option is None:
            _logger.error("Drop-down %s does not offer %r; available values: %s", title_xpath, value, list(options or {}))
            return False
        WebDriverWait(driver, Constants.BODY_TIMEOUT).until(
            lambda _driver: option if option.is_displayed() and option.is_enabled() else False
        )
        option.click()
        if not wait_until_idle(driver):
            return False
        WebDriverWait(driver, Constants.BODY_TIMEOUT).until(selected)
        return True
    except Exception:
        _logger.warning("Could not select %r in drop-down %s", value, title_xpath, exc_info=True)
        return False


def checkbox_icon_value(checkbox: Any) -> bool | None:
    """A PrimeNG tri-state checkbox's value read from its check / uncheck icon (None: neither)."""
    try:
        checkbox.find_element(By.CSS_SELECTOR, 'checkicon[data-pc-section="checkIcon"]')
        return True
    except Exception:
        try:
            checkbox.find_element(By.CSS_SELECTOR, 'timesicon[data-pc-section="uncheckIcon"]')
            return False
        except Exception:
            return None


def checkbox_value(checkbox: Any) -> bool | None:
    """PrimeNG reports aria-checked=false for both blank and X; the icon distinguishes them."""
    value = checkbox.get_attribute("aria-checked")
    if value == "true":
        return True
    if value == "false":
        return checkbox_icon_value(checkbox)
    if value == "mixed":
        return None
    return checkbox_icon_value(checkbox)


def checkbox_is_disabled(form_element: Any, checkbox_element: Any) -> bool:
    """Recognizes the disabled states exposed by WebFlow's PrimeNG checkbox markup."""
    try:
        host = form_element.find_element(By.CSS_SELECTOR, "p-tristatecheckbox")
    except Exception:
        host = None

    for element in (host, checkbox_element):
        if element is None:
            continue
        if element.get_attribute("aria-disabled") == "true":
            return True
        if any(
            element.get_attribute(attribute) == "true"
            for attribute in ("ng-reflect-disabled", "ng-reflect-is-disabled")
        ):
            return True
        classes = element.get_attribute("class") or ""
        if any(name in classes.split() for name in ("bg-disabled", "p-checkbox-disabled", "p-disabled")):
            return True

    return False


def click_count(current: bool | None, target: bool | None) -> int:
    """Clicks a tri-state checkbox needs to go from ``current`` to ``target`` (None -> True -> False -> None)."""
    if current is target:
        return 0
    if target is None:
        return 2 if current is True else 1
    if current is None:
        return 1 if target else 2
    return 1


class Section:
    """A collapsible WebFlow panel: a title whose parent is the toggle and a ``display:`` styled body.

    ``scroll`` scrolls a hidden body into view while its state is read."""

    def __init__(self, driver: Any, title_xpath: str, body_css: str, scroll: bool = True):
        self.driver = driver
        self.title_xpath = title_xpath
        self.body_css = body_css
        self.scroll = scroll

    def _title(self) -> Any:
        return wait_for(self.driver, By.XPATH, self.title_xpath)

    def body(self) -> Any:
        return self._title().find_element(By.XPATH, "../..").find_element(By.CSS_SELECTOR, self.body_css)

    def _body_is_open(self) -> bool:
        body = self.body()
        if self.scroll:
            scroll_into_view_if_hidden(self.driver, body)
        return "block" in body.get_attribute("style")

    def is_expanded(self) -> bool:
        try:
            return self._body_is_open()
        except Exception:
            _logger.debug("Could not read section %s", self.title_xpath, exc_info=True)
            return False

    def is_collapsed(self) -> bool:
        try:
            return not self._body_is_open()
        except Exception:
            _logger.debug("Could not read section %s", self.title_xpath, exc_info=True)
            return False

    def toggle(self) -> None:
        """Clicks the section header; raises if it cannot be found."""
        self._title().find_element(By.XPATH, "..").click()
        pause()

    def expand(self) -> bool:
        return self.is_expanded() or self._safe_toggle()

    def collapse(self) -> bool:
        return self.is_collapsed() or self._safe_toggle()

    def _safe_toggle(self) -> bool:
        try:
            self.toggle()
            return True
        except Exception:
            _logger.warning("Could not toggle section %s", self.title_xpath, exc_info=True)
            return False

    def fill_input(self, input_css: str, value: str) -> bool:
        """Expands the section and types ``value`` into its ``input_css`` field."""
        if not self.expand():
            return False
        try:
            field = self.body().find_element(By.CSS_SELECTOR, input_css)
            scroll_into_view_if_hidden(self.driver, field)
            if not field.is_enabled() or field.get_attribute("readonly") is not None:
                _logger.error("WebFlow input %s is read-only; requested %r", input_css, value)
                return False
            field.clear()
            field.send_keys(value)
            pause()
            if field.get_attribute("value") != value:
                _logger.error("WebFlow input %s did not retain requested value %r", input_css, value)
                return False
            return True
        except Exception:
            _logger.warning("Could not fill %s", input_css, exc_info=True)
            return False


class TabLink:
    """A WebFlow tab header found by XPath."""

    def __init__(self, driver: Any, xpath: str):
        self.driver = driver
        self.xpath = xpath

    def is_selected(self) -> bool:
        try:
            tab = wait_for(self.driver, By.XPATH, self.xpath)
            scroll_into_view_if_hidden(self.driver, tab)
            return bool(tab.is_selected())
        except Exception:
            _logger.debug("Could not read tab %s", self.xpath, exc_info=True)
            return False

    def select(self) -> bool:
        if self.is_selected():
            return True
        try:
            tab = wait_for(self.driver, By.XPATH, self.xpath)
            if not tab.is_selected():
                tab.click()
                pause()
            return True
        except Exception:
            _logger.warning("Could not select tab %s", self.xpath, exc_info=True)
            return False
