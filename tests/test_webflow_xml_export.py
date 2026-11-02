"""Export action and completed download capture without an external WebFlow server."""
from pathlib import Path
from unittest.mock import Mock

import pytest
from selenium.common.exceptions import TimeoutException

from autohub.services.WebFlow import xml_export
from autohub.services.WebFlow import WebFlow as webflow_module
from autohub.services.WebFlow.WebFlow import WebFlow


class FastWait:
    def __init__(self, driver, *_args, **_kwargs):
        self.driver = driver

    def until(self, condition):
        for _ in range(5):
            result = condition(self.driver)
            if result:
                return result
        raise TimeoutException()


def setup_export(monkeypatch, download):
    driver, ribbon, button = Mock(), Mock(), Mock()
    button.is_displayed.return_value = True
    button.is_enabled.return_value = True
    button.get_attribute.return_value = None
    ribbon.find_element.return_value = button
    monkeypatch.setattr(xml_export, "wait_for", Mock(return_value=ribbon))
    monkeypatch.setattr(xml_export, "wait_until_idle", Mock(return_value=True))
    monkeypatch.setattr(xml_export, "WebDriverWait", FastWait)
    directories = []

    def configure(_command, parameters):
        directories.append(Path(parameters["downloadPath"]))

    driver.execute_cdp_cmd.side_effect = configure
    button.click.side_effect = lambda: download(directories[-1])
    return driver, ribbon, button, directories


def test_export_clicks_exact_action_once_captures_download_and_cleans_up(monkeypatch):
    data = b"<Job><Fields/></Job>"
    driver, ribbon, button, directories = setup_export(
        monkeypatch, lambda path: (path / "WF12_export.xml").write_bytes(data),
    )
    assert xml_export.export_xml(driver) == data
    button.click.assert_called_once()
    assert 'normalize-space(.)="Export XML"' in ribbon.find_element.call_args.args[1]
    assert driver.execute_cdp_cmd.call_args.args[0] == "Browser.setDownloadBehavior"
    assert not directories[0].exists()


@pytest.mark.parametrize("filename", ["WF12.xml.crdownload", "WF12.xml.tmp", "WF12.xml.partial", ""])
def test_partial_or_missing_download_times_out_without_returning_data(monkeypatch, filename):
    def download(path):
        if filename:
            (path / filename).write_bytes(b"partial")
    driver, _, button, directories = setup_export(monkeypatch, download)
    with pytest.raises(RuntimeError, match="timed out"):
        xml_export.export_xml(driver)
    button.click.assert_called_once()
    driver.quit.assert_called_once()
    assert not directories[0].exists()


def test_disabled_export_action_is_not_clicked(monkeypatch):
    driver, _, button, _ = setup_export(monkeypatch, lambda _: None)
    button.is_enabled.return_value = False
    with pytest.raises(RuntimeError, match="missing or disabled"):
        xml_export.export_xml(driver)
    button.click.assert_not_called()


@pytest.mark.parametrize("failure", ["configure", "click"])
def test_browser_errors_are_propagated_and_session_closed(monkeypatch, failure):
    driver, _, button, _ = setup_export(monkeypatch, lambda _: None)
    if failure == "configure":
        driver.execute_cdp_cmd.side_effect = RuntimeError("configuration failed")
    else:
        button.click.side_effect = RuntimeError("click failed")
    with pytest.raises(RuntimeError, match="failed"):
        xml_export.export_xml(driver)
    driver.quit.assert_called_once()


def test_cleanup_failure_does_not_mask_download_error(monkeypatch, caplog):
    driver, _, _, _ = setup_export(monkeypatch, lambda _: None)
    driver.quit.side_effect = RuntimeError("browser already closed")
    with pytest.raises(RuntimeError, match="timed out"):
        xml_export.export_xml(driver)
    assert "Could not stop the failed WebFlow XML downloader" in caplog.text


def test_download_failures_do_not_reuse_previous_file(monkeypatch):
    driver, _, button, directories = setup_export(
        monkeypatch, lambda path: (path / "export.xml").write_bytes(b"first job"),
    )
    assert xml_export.export_xml(driver) == b"first job"
    button.click.side_effect = lambda: None
    with pytest.raises(RuntimeError, match="timed out"):
        xml_export.export_xml(driver)
    assert directories[0] != directories[1]


def test_oversized_download_and_multiple_files_fail_explicitly(monkeypatch):
    monkeypatch.setattr(xml_export, "MAX_EXPORT_BYTES", 3)
    driver, _, _, _ = setup_export(monkeypatch, lambda path: (path / "export.xml").write_bytes(b"long"))
    with pytest.raises(RuntimeError, match="10 MiB"):
        xml_export.export_xml(driver)
    monkeypatch.setattr(xml_export, "MAX_EXPORT_BYTES", 100)

    def multiple(path):
        (path / "a.xml").write_bytes(b"a")
        (path / "b.xml").write_bytes(b"b")
    driver, _, _, _ = setup_export(monkeypatch, multiple)
    with pytest.raises(RuntimeError, match="multiple files"):
        xml_export.export_xml(driver)


def test_session_exports_using_existing_job_readiness_and_exact_link(monkeypatch):
    session = Mock()
    session.open_job.return_value = True
    exported = Mock(return_value=b"xml")
    monkeypatch.setattr(webflow_module, "export_xml", exported)
    assert WebFlow.export_job_xml(session, "https://other-host/app/ShowJob/99") == b"xml"
    session.open_job.assert_called_once_with("99", url="https://other-host/app/ShowJob/99")
    exported.assert_called_once_with(session)
    session.open_job.return_value = False
    exported.reset_mock()
    with pytest.raises(RuntimeError, match="Could not open"):
        WebFlow.export_job_xml(session, "https://other-host/app/ShowJob/99")
    exported.assert_not_called()
