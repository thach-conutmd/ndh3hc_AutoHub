"""Batch comparisons isolate per-job failures and reuse one authenticated export session."""
from unittest.mock import Mock, call
from threading import Event

import pytest

from autohub.modules.comparison.comparison import Status
from autohub.modules.comparison.service import ComparisonService
from tests.test_comparison import export_xml, target_parameters, variant


def session_factory(exports):
    session = Mock()
    session.open_dashboard_page.return_value = True
    session.export_job_xml.side_effect = exports
    return session, Mock(return_value=session)


def test_sequential_batch_uses_one_browser_and_exact_job_links():
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    session, factory = session_factory([
        export_xml(target_parameters()), export_xml(target_parameters("P2", "0011"), job_id="13"),
    ])
    progress = Mock()
    results = ComparisonService(factory).run(
        variants, variants, connection={"driver_path": "edge.exe", "base_url": "https://webflow/app/dashboard"},
        progress=progress,
    )
    factory.assert_called_once_with(driver_path="edge.exe", base_url="https://webflow/app/dashboard")
    session.open_dashboard_page.assert_called_once()
    assert session.export_job_xml.call_args_list == [call(v["webflow_link"]) for v in variants]
    session.quit.assert_called_once()
    assert len(results) == 2 and all(result.rows and not result.error for result in results)
    for index in range(2):
        assert [args[1] for args, _ in progress.call_args_list if args[0] == index] == [
            "Pending", "Exporting Target XML", "Comparing", "Completed",
        ]


@pytest.mark.parametrize("failure", [
    "export", "timeout", "invalid_xml", "invalid_link", "wrong_variant", "wrong_sw",
    "wrong_job", "master_missing", "missing_sw",
])
def test_failure_for_one_variant_does_not_stop_later_variants(failure):
    first, second = variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")
    bad = export_xml(target_parameters())
    masters = [first, second]
    if failure == "export":
        bad = RuntimeError("Export XML action disabled")
    elif failure == "timeout":
        bad = RuntimeError("download timed out")
    elif failure == "invalid_xml":
        bad = b"<broken"
    elif failure == "wrong_variant":
        bad = export_xml(target_parameters("P3"))
    elif failure == "wrong_sw":
        bad = export_xml(target_parameters(software="9999"))
    elif failure == "wrong_job":
        bad = export_xml(target_parameters(), job_id="99")
    elif failure == "master_missing":
        masters = [second]
    elif failure == "missing_sw":
        bad = export_xml({"General/CustomerOrderNumber": "P1"})
    elif failure == "invalid_link":
        first["webflow_link"] = "invalid"
    exports = [bad, export_xml(target_parameters("P2", "0011"), job_id="13")]
    if failure == "invalid_link":
        exports.pop(0)
    session, factory = session_factory(exports)
    progress = Mock()
    results = ComparisonService(factory).run([first, second], masters, progress=progress)
    assert results[0].error and results[0].rows == []
    assert not results[1].error and results[1].rows
    assert call(0, "Failed", results[0].error) in progress.call_args_list
    assert call(1, "Completed", "") in progress.call_args_list
    assert session.quit.called


def test_wrong_selected_pair_is_rejected_even_if_export_matches_another_master_entry():
    selected, other = variant(), variant("P2")
    session, factory = session_factory([export_xml(target_parameters("P2"))])
    result = ComparisonService(factory).run([selected], [selected, other])[0]
    assert "selected Variant + SW Part Number" in result.error
    session.quit.assert_called_once()


@pytest.mark.parametrize("second_base_id", ["99", "100"])
def test_each_variant_exports_its_own_base_after_its_target(second_base_id):
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    variants[0]["base_webflow_link"] = "https://webflow/app/ShowJob/99"
    variants[1]["base_webflow_link"] = f"https://webflow/app/ShowJob/{second_base_id}"
    session, factory = session_factory([
        export_xml(target_parameters()),
        export_xml(target_parameters(), job_id="99"),
        export_xml(target_parameters("P2", "0011"), job_id="13"),
        export_xml({**target_parameters(), "General/Power": "94"}, job_id=second_base_id),
    ])
    progress = Mock()
    results = ComparisonService(factory).run(variants, variants, progress=progress)
    assert session.export_job_xml.call_args_list == [
        call(variants[0]["webflow_link"]), call(variants[0]["base_webflow_link"]),
        call(variants[1]["webflow_link"]), call(variants[1]["base_webflow_link"]),
    ]
    assert all(not result.error for result in results)
    power_rows = [next(row for row in result.rows if row.parameter == "General/Power") for result in results]
    assert [row.status for row in power_rows] == [Status.MATCHES_BOTH, Status.MATCHES_MASTER]
    for index in range(2):
        assert [args[1] for args, _ in progress.call_args_list if args[0] == index] == [
            "Pending", "Exporting Target XML", "Exporting Base XML", "Comparing", "Completed",
        ]


@pytest.mark.parametrize("base_link,exported", [
    ("invalid", None),
    ("https://webflow/app/ShowJob/99", b"<bad>"),
    ("https://webflow/app/ShowJob/99", export_xml(target_parameters(), job_id="77")),
    ("https://webflow/app/ShowJob/99", RuntimeError("download timed out")),
])
def test_base_failure_only_fails_its_own_variant(base_link, exported):
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    variants[0]["base_webflow_link"] = base_link
    exports = [export_xml(target_parameters())]
    if exported is not None:
        exports.append(exported)
    exports.append(export_xml(target_parameters("P2", "0011"), job_id="13"))
    session, factory = session_factory(exports)
    results = ComparisonService(factory).run(variants, variants)
    assert "Base XML:" in results[0].error and results[0].rows == []
    assert not results[1].error and results[1].rows
    assert all(row.status in (
        Status.MATCH, Status.VALUE_MISMATCH, Status.MISSING_IN_MASTER, Status.MISSING_IN_WEBFLOW,
    ) for row in results[1].rows)


def test_browser_start_failure_is_isolated_and_next_variant_can_start_a_session():
    session, _ = session_factory([export_xml(target_parameters("P2", "0011"), job_id="13")])
    factory = Mock(side_effect=[RuntimeError("Edge unavailable"), session])
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    results = ComparisonService(factory).run(variants, variants)
    assert "Edge unavailable" in results[0].error and not results[1].error
    session.quit.assert_called_once()


def test_empty_batch_does_not_start_browser():
    factory = Mock()
    assert ComparisonService(factory).run([], []) == []
    factory.assert_not_called()


def test_failed_export_session_is_closed_and_replaced_before_next_variant():
    failed, _ = session_factory([RuntimeError("download failed")])
    replacement, _ = session_factory([export_xml(target_parameters("P2", "0011"), job_id="13")])

    def open_replacement():
        failed.quit.assert_called_once()
        return True

    replacement.open_dashboard_page.side_effect = open_replacement
    factory = Mock(side_effect=[failed, replacement])
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    results = ComparisonService(factory).run(variants, variants)
    assert results[0].error == "download failed"
    assert results[1].rows and not results[1].error
    replacement.open_dashboard_page.assert_called_once()
    replacement.quit.assert_called_once()


def test_cancel_before_start_skips_all_exports():
    variants = [variant(), variant("P2")]
    factory, progress = Mock(), Mock()
    results = ComparisonService(factory).run(variants, variants, progress=progress, cancelled=lambda: True)
    factory.assert_not_called()
    assert all(result.cancelled and not result.rows and not result.error for result in results)
    assert call(0, "Cancelled", "") in progress.call_args_list
    assert call(1, "Cancelled", "") in progress.call_args_list


def test_cancel_during_target_finishes_its_base_and_keeps_results():
    variants = [variant(), variant("P2")]
    variants[0]["base_webflow_link"] = "https://webflow/app/ShowJob/99"
    cancel = Event()
    session, factory = session_factory([])

    def export(link):
        cancel.set()
        return export_xml(target_parameters(), job_id="99" if link.endswith("/99") else "12")

    session.export_job_xml.side_effect = export
    results = ComparisonService(factory).run(variants, variants, cancelled=cancel.is_set)
    assert results[0].rows and not results[0].cancelled
    assert results[1].cancelled and not results[1].rows
    assert session.export_job_xml.call_args_list == [
        call(variants[0]["webflow_link"]), call(variants[0]["base_webflow_link"]),
    ]
    session.quit.assert_called_once()
