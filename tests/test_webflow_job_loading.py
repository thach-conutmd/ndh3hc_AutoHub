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
        title=title, get=Mock(), find_element=find_element,
        job_url=Mock(return_value="https://example.com/app/ShowJob/16468"),
    )
    return driver, idle


def test_job_form_ready_after_navigation(monkeypatch):
    driver, idle = session(monkeypatch)
    assert WebFlow.open_job(driver, "16468") is True
    driver.get.assert_called_once_with("https://example.com/app/ShowJob/16468")
    idle.assert_called_once_with(driver)


def test_recorded_browser_error_page_is_not_success(monkeypatch):
    path = Path(__file__).resolve().parents[1] / (
        "logs/webflow_trace/20261101_134207/001_Open_job_16468_OK.html"
    )
    parser = TitleParser()
    html = path.read_text(encoding="utf-8")
    parser.feed(html)
    assert "ERR_UNEXPECTED" in html
    assert parser.title != Constants.WEBFLOW_TITLE
    driver, idle = session(monkeypatch, title=parser.title)
    assert WebFlow.open_job(driver, "16468") is False
    idle.assert_not_called()


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
