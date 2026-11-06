import logging

import pytest

from autohub.services.WebFlow.operation_log import CANCELLED, FAILED, SUCCESS, job_id_from_link, logged_operation
from autohub.services.WebFlow.WebFlow import _cancel_outcome, _link_context, _variants_context

_log = logging.getLogger("tests.webflow_operation")


def _job_context(arguments):
    return f"job {arguments['job_id']}"


def test_success_logs_operation_context_and_result(caplog):
    @logged_operation(_log, "Open job", _job_context)
    def open_job(job_id):
        return True

    with caplog.at_level(logging.INFO, logger=_log.name):
        assert open_job("123") is True
    assert "WebFlow operation Open job started | job 123" in caplog.text
    assert "WebFlow operation Open job | job 123 | Result: Success" in caplog.text


def test_false_return_is_logged_as_failed_without_changing_result(caplog):
    @logged_operation(_log, "Open job", _job_context)
    def open_job(job_id):
        return False

    with caplog.at_level(logging.INFO, logger=_log.name):
        assert open_job("123") is False
    assert "Result: Failed" in caplog.text
    assert [r.levelno for r in caplog.records if "Result" in r.getMessage()] == [logging.WARNING]


def test_exception_is_logged_with_details_and_reraised_unchanged(caplog):
    error = RuntimeError("boom")

    @logged_operation(_log, "Create and fill jobs")
    def create():
        raise error

    with caplog.at_level(logging.INFO, logger=_log.name):
        with pytest.raises(RuntimeError) as raised:
            create()
    assert raised.value is error
    assert "Result: Failed" in caplog.text and "RuntimeError: boom" in caplog.text
    failure = [r for r in caplog.records if "Result: Failed" in r.getMessage()][0]
    assert failure.levelno == logging.ERROR and failure.exc_info


def test_cancel_outcome_reports_cancelled(caplog):
    @logged_operation(_log, "Cancel job", _job_context, _cancel_outcome)
    def cancel_job(job_id, reason):
        return True

    with caplog.at_level(logging.INFO, logger=_log.name):
        cancel_job("7", "wrong variant")
    assert "Result: Cancelled" in caplog.text
    assert "wrong variant" not in caplog.text


def test_context_only_contains_what_the_context_function_returns(caplog):
    @logged_operation(_log, "Add user", lambda a: f"job {a['job_id']}")
    def add(job_id, name, token):
        return True

    with caplog.at_level(logging.INFO, logger=_log.name):
        add("9", "Jane", token="secret-token-value")
    assert "secret-token-value" not in caplog.text
    assert "Jane" not in caplog.text


def test_job_id_comes_from_link_path_without_query():
    assert job_id_from_link("https://wf.example/app/ShowJob/555/?token=abc") == "555"
    assert _link_context({"link": "https://wf.example/app/ShowJob/555/?token=abc"}) == "job 555"


def test_variant_context_lists_part_numbers_only():
    context = _variants_context({"variants": [{"part_number": "P1", "password": "x"}, {"part_number": "P2"}]})
    assert context == "2 variant(s): P1, P2"
    assert "password" not in context and "x" not in context


def test_labels_are_the_documented_values():
    assert (SUCCESS, FAILED, CANCELLED) == ("Success", "Failed", "Cancelled")
