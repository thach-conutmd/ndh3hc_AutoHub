"""Job loading must reject browser error pages even when no activity spinner exists."""
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By

from autohub.services.WebFlow import Constants
from autohub.services.WebFlow import WebFlow as webflow_module
from autohub.services.WebFlow.WebFlow import WebFlow


class TitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title = ""

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def session(monkeypatch, title=Constants.WEBFLOW_TITLE, general_visible=True):
    monkeypatch.setattr(Constants, "WEBFLOW_TIMEOUT", 0)
    idle = Mock(return_value=True)
    monkeypatch.setattr(webflow_module, "wait_until_idle", idle)
    general = Mock()
    general.is_displayed.return_value = general_visible

    def find_element(by, locator):
        if by == By.XPATH and locator == Constants.GENERAL_TAB_XPATH:
            return general
        raise NoSuchElementException(locator)

    driver = SimpleNamespace(
        title=title, page_source="", get=Mock(), refresh=Mock(), quit=Mock(), find_element=find_element,
        job_url=Mock(return_value="https://example.com/app/ShowJob/16468"),
    )
    return driver, idle


def test_job_form_ready_after_navigation(monkeypatch):
    driver, idle = session(monkeypatch)
    assert WebFlow.open_job(driver, "16468") is True
    driver.get.assert_called_once_with("https://example.com/app/ShowJob/16468")
    idle.assert_called_once_with(driver)


def test_recorded_browser_error_page_is_not_success(monkeypatch):
    monkeypatch.setattr(Constants, "WEBFLOW_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(Constants, "WEBFLOW_REFRESH_INTERVAL", 0)
    path = Path(__file__).resolve().parents[1] / (
        "logs/webflow_trace/20261101_134207/001_Open_job_16468_OK.html"
    )
    parser = TitleParser()
    html = path.read_text(encoding="utf-8")
    parser.feed(html)
    assert "ERR_UNEXPECTED" in html
    assert parser.title != Constants.WEBFLOW_TITLE
    driver, idle = session(monkeypatch, title=parser.title)
    driver.page_source = html
    assert WebFlow.open_job(driver, "16468") is False
    driver.refresh.assert_called_once()
    driver.quit.assert_called_once()
    idle.assert_not_called()


def test_job_open_refreshes_edge_error_page_and_continues(monkeypatch):
    monkeypatch.setattr(Constants, "WEBFLOW_REFRESH_INTERVAL", 0)
    driver, idle = session(monkeypatch)
    driver.page_source = "ERR_UNEXPECTED"

    def refresh():
        driver.page_source = ""

    driver.refresh.side_effect = refresh
    assert WebFlow.open_job(driver, "16468") is True
    driver.refresh.assert_called_once()
    driver.quit.assert_not_called()
    idle.assert_called_once_with(driver)


@pytest.mark.parametrize("attempts", [1, 2, 5])
def test_persistent_error_closes_browser_at_refresh_limit(monkeypatch, attempts):
    monkeypatch.setattr(Constants, "WEBFLOW_MAX_ATTEMPTS", attempts)
    monkeypatch.setattr(Constants, "WEBFLOW_REFRESH_INTERVAL", 0)
    driver, idle = session(monkeypatch)
    driver.page_source = "ERR_UNEXPECTED"

    assert WebFlow.open_job(driver, "16468") is False
    assert driver.refresh.call_count == attempts
    driver.quit.assert_called_once()
    idle.assert_not_called()


@pytest.mark.parametrize("recovers", [False, True])
def test_dashboard_closes_only_if_final_refresh_fails(monkeypatch, recovers):
    monkeypatch.setattr(Constants, "WEBFLOW_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(Constants, "WEBFLOW_REFRESH_INTERVAL", 0)
    driver, _ = session(monkeypatch, title="browser error")
    driver.base_url = "https://example.com/app/dashboard"

    def refresh():
        if recovers:
            driver.title = Constants.WEBFLOW_TITLE

    driver.refresh.side_effect = refresh
    assert WebFlow.open_dashboard_page(driver) is recovers
    driver.refresh.assert_called_once()
    assert driver.quit.call_count == (0 if recovers else 1)


def test_webflow_shell_without_visible_job_form_is_not_success(monkeypatch):
    driver, _ = session(monkeypatch, general_visible=False)
    assert WebFlow.open_job(driver, "16468") is False


def test_navigation_exception_is_reported_as_failure(monkeypatch):
    driver, _ = session(monkeypatch)
    driver.get.side_effect = WebDriverException("connection failed")
    assert WebFlow.open_job(driver, "16468") is False


def test_initial_loading_overlay_must_disappear(monkeypatch):
    driver, idle = session(monkeypatch)
    overlay = Mock()
    overlay.is_displayed.return_value = True
    original = driver.find_element
    driver.find_element = lambda by, locator: (
        overlay if locator == Constants.WEBFLOW_LOADING_SCREEN_CLASS else original(by, locator)
    )
    assert WebFlow.open_job(driver, "16468") is False
    idle.assert_not_called()


def test_busy_job_is_not_success(monkeypatch):
    driver, idle = session(monkeypatch)
    idle.return_value = False
    assert WebFlow.open_job(driver, "16468") is False
