"""Retrying and resuming WebFlow batches without repeating server-side effects."""
import logging
from dataclasses import asdict, replace
from unittest.mock import Mock

import pytest

from autohub.core.batch_journal import JsonBatchJournal, NonRetryableError
from autohub.modules.creation.service import MAX_ATTEMPTS, WebFlowConfig, WebFlowJobService
from autohub.modules.creation.ui import CreationWidget
from autohub.services.WebFlow.job_batch import JobBatch
from autohub.services.WebFlow.job_filler import JobFiller
from tests.fakes import FakeDialogs, MemorySettings


class MemoryJournal:
    def __init__(self, state=None):
        self.state = state
        self.saves = []

    def load(self):
        return self.state

    def save(self, state):
        self.saves.append(repr(state))
        self.state = state

    def clear(self):
        self.state = None


def batch(created=True, before_submit_runs=True):
    calls = []
    creation = Mock()

    def jobs_creation(before_submit=None, **_kwargs):
        if before_submit_runs:
            before_submit()
        calls.append("create")
        return created

    creation.jobs_creation.side_effect = jobs_creation
    creation.get_new_jobs_ids.return_value = ["1", "2"]
    fill = Mock(side_effect=lambda variant: calls.append(f"fill {variant['part_number']}") or [])
    workflow = JobBatch(
        creation, lambda: True, lambda: True,
        lambda job: calls.append(f"open {job}") or True, fill,
        lambda job: f"u/{job}", lambda: calls.append("close"), logging.getLogger(__name__),
    )
    variants = [
        {"part_number": part, "ecu_generation": "MG1", "brand": "Honda", "ecu_type": "E"} for part in ("P1", "P2")
    ]
    return workflow, variants, calls, fill


def test_batch_records_progress_before_each_side_effect():
    workflow, variants, calls, _ = batch()
    state, snapshots = {}, []
    workflow.run(variants, "t", "r", state=state, checkpoint=lambda: snapshots.append(dict(state, results=list(state["results"]))))
    assert snapshots[0]["creation_submitted"] and not snapshots[0]["job_ids"]  # saved before Confirm
    assert snapshots[1]["job_ids"] == ["1", "2"]
    assert [len(s["results"]) for s in snapshots[2:]] == [1, 2]


def test_batch_resume_skips_creation_and_completed_jobs():
    workflow, variants, calls, _ = batch()
    state = {"creation_submitted": True, "job_ids": ["1", "2"], "results": [{"PartNumber": "P1", "JobId": "1", "Url": "u/1"}]}
    results = workflow.run(variants, "t", "r", state=state)
    assert calls == ["open 2", "fill P2", "close"]
    assert [r["JobId"] for r in results] == ["1", "2"]


def test_batch_never_resubmits_creation_with_unknown_job_ids():
    workflow, variants, calls, _ = batch()
    with pytest.raises(NonRetryableError):
        workflow.run(variants, "t", "r", state={"creation_submitted": True})
    assert calls == []


def test_batch_failure_after_submission_is_not_retryable_but_before_is():
    workflow, variants, _, _ = batch(created=False)
    with pytest.raises(NonRetryableError):
        workflow.run(variants, "t", "r", state={})
    workflow, variants, _, _ = batch(created=False, before_submit_runs=False)
    state = {}
    with pytest.raises(RuntimeError) as error:
        workflow.run(variants, "t", "r", state=state)
    assert not isinstance(error.value, NonRetryableError) and not state["creation_submitted"]


class Pages:
    imported_software_part_number = ""
    imported_ecr_number = ""

    def __init__(self, clicks, ok=True):
        self.clicks, self.ok, self.skipped_fields = clicks, ok, []

    def select_general_tab(self):
        return True

    def import_ecr(self):
        self.clicks.append("import")
        self.imported_ecr_number = "ECR1" if self.ok else ""
        return self.ok


class Plan:
    def __init__(self, pages):
        self.pages = pages

    def steps(self, variant):
        return [("General: ECR Import", self.pages.import_ecr), ("Save the job", lambda: True)]


def filler(clicks, ok=True):
    pages = Pages(clicks, ok)
    body = Mock()
    body.tab.generaltab = pages
    return JobFiller(Mock(), body, Plan(pages))


def test_number_import_is_clicked_once_across_retries():
    clicks, saves = [], []
    variant = {"part_number": "P1", "ecr": {"x": "y"}}
    first = filler(clicks, ok=False)
    first.checkpoint = lambda: saves.append(list(variant["attempted_imports"]))
    with pytest.raises(RuntimeError):
        first.fill(variant)
    assert saves[0] == ["General: ECR Import"]  # recorded before clicking

    warnings = filler(clicks).fill(variant)
    assert clicks == ["import"]
    assert "check the job in WebFlow" in warnings[0]


def test_number_import_value_is_kept_for_a_retry():
    clicks = []
    variant = {"part_number": "P1", "ecr": {"x": "y"}}
    filler(clicks).fill(variant)
    assert variant["imported_ecr_number"] == "ECR1"
    assert filler(clicks).fill(variant) == [] and clicks == ["import"]
    assert variant["imported_ecr_number"] == "ECR1"


class FlakyWebFlow:
    failures = 0
    instances: list = []

    def __init__(self, **_kwargs):
        self.quit_calls = 0
        FlakyWebFlow.instances.append(self)

    def create_and_fill_jobs(self, variants, tool_version, routing, progress=None, state=None, checkpoint=None):
        if len(FlakyWebFlow.instances) <= FlakyWebFlow.failures:
            raise RuntimeError("browser crashed")
        return [{"PartNumber": v["part_number"], "JobId": "1"} for v in variants]

    def quit(self):
        self.quit_calls += 1


def flaky_service(failures, journal=None):
    FlakyWebFlow.failures = failures
    FlakyWebFlow.instances = []
    sleeps = []
    return WebFlowJobService(FlakyWebFlow, journal=journal, sleep=sleeps.append), sleeps


CONFIG = WebFlowConfig("", "url", "v", "r")


def test_service_retries_until_success_and_clears_progress():
    journal = MemoryJournal()
    service, sleeps = flaky_service(MAX_ATTEMPTS - 1, journal)
    progress = Mock()
    assert service.create_jobs([{"part_number": "P1"}], CONFIG, progress) == [{"PartNumber": "P1", "JobId": "1"}]
    assert len(FlakyWebFlow.instances) == MAX_ATTEMPTS == 5 and len(sleeps) == 4
    assert all(browser.quit_calls == 1 for browser in FlakyWebFlow.instances)
    assert any("Attempt 5 of 5" in str(call) for call in progress.call_args_list)
    assert journal.state is None


def test_service_gives_up_after_five_attempts_and_keeps_progress():
    journal = MemoryJournal()
    service, _ = flaky_service(99, journal)
    with pytest.raises(RuntimeError, match="after 5 attempts"):
        service.create_jobs([{"part_number": "P1"}], CONFIG)
    assert len(FlakyWebFlow.instances) == 5
    assert service.pending_batch()["variants"] == [{"part_number": "P1"}]


@pytest.mark.parametrize("attempts", [1, 2, 7])
def test_service_respects_configured_attempt_limit_and_retains_recovery(attempts):
    journal = MemoryJournal()
    service, sleeps = flaky_service(99, journal)
    config = replace(CONFIG, max_attempts=attempts)
    with pytest.raises(RuntimeError, match=f"after {attempts} attempts"):
        service.create_jobs([{"part_number": "P1"}], config)
    assert len(FlakyWebFlow.instances) == attempts
    assert sleeps == [5.0] * (attempts - 1)
    assert service.pending_batch()["config"]["max_attempts"] == attempts


def test_resume_uses_saved_attempt_limit():
    state = {
        "config": asdict(replace(CONFIG, max_attempts=2)),
        "variants": [{"part_number": "P1"}], "attempt": 2,
    }
    service, sleeps = flaky_service(99, MemoryJournal(state))
    with pytest.raises(RuntimeError, match="after 2 attempts"):
        service.resume_jobs()
    assert len(FlakyWebFlow.instances) == 2
    assert sleeps == [5.0]


@pytest.mark.parametrize("attempts", [0, -1, 101, True, "5", 1.5, None])
def test_invalid_attempt_limit_is_rejected(attempts):
    with pytest.raises(ValueError, match="Maximum WebFlow attempts"):
        replace(CONFIG, max_attempts=attempts)


def test_loaded_settings_supply_attempt_limit():
    from autohub.modules.creation.config_form import load_config

    assert load_config(MemorySettings()).max_attempts == 5
    assert load_config(MemorySettings({"webflow_max_attempts": 1})).max_attempts == 1


def test_service_does_not_retry_errors_that_could_duplicate_jobs():
    journal = MemoryJournal()
    factory = Mock()
    factory.return_value.create_and_fill_jobs.side_effect = NonRetryableError("ids unknown")
    service = WebFlowJobService(factory, journal=journal, sleep=lambda _s: None)
    with pytest.raises(NonRetryableError):
        service.create_jobs([{"part_number": "P1"}], CONFIG)
    assert factory.call_count == 1 and journal.state is None


def test_service_resumes_saved_batch_with_its_config():
    state = {
        "config": {"driver_path": "", "base_url": "saved", "tool_version": "v", "routing": "r"},
        "master_sheet_path": "", "variants": [{"part_number": "P1"}],
        "creation_submitted": True, "job_ids": ["7"], "results": [],
    }
    journal = MemoryJournal(state)
    factory = Mock()
    factory.return_value.create_and_fill_jobs.return_value = [{"PartNumber": "P1", "JobId": "7"}]
    service = WebFlowJobService(factory, journal=journal)
    assert service.resume_jobs() == [{"PartNumber": "P1", "JobId": "7"}]
    assert factory.call_args.kwargs["base_url"] == "saved"
    assert factory.return_value.create_and_fill_jobs.call_args.kwargs["state"]["job_ids"] == ["7"]
    assert journal.state is None


def test_json_journal_roundtrip(tmp_path):
    journal = JsonBatchJournal(tmp_path / "batch.json")
    assert journal.load() is None
    journal.save({"variants": [{"part_number": "P1"}]})
    assert journal.load() == {"variants": [{"part_number": "P1"}]}
    journal.clear()
    journal.clear()
    assert journal.load() is None


@pytest.mark.parametrize("answer", [True, False])
def test_creation_page_asks_to_continue_unfinished_work_on_startup(qapp, answer):
    service = Mock(last_elapsed_seconds=0.0)
    service.pending_batch.return_value = {"variants": [{"part_number": "P1"}, {"part_number": "P2"}], "results": [{}]}
    dialogs = FakeDialogs(confirm_answer=answer)
    page = CreationWidget(service, MemorySettings(), dialogs)
    page._start_task = Mock()
    page.on_startup()
    assert "P1, P2" in dialogs.confirmed[0][1] and "1 of 2" in dialogs.confirmed[0][1]
    if answer:
        page._start_task.assert_called_once_with(service.resume_jobs)
        service.discard_pending_batch.assert_not_called()
    else:
        page._start_task.assert_not_called()
        service.discard_pending_batch.assert_called_once()


def test_creation_page_stays_quiet_without_unfinished_work(qapp):
    service = Mock(last_elapsed_seconds=0.0)
    service.pending_batch.return_value = None
    dialogs = FakeDialogs()
    CreationWidget(service, MemorySettings(), dialogs).on_startup()
    assert dialogs.confirmed == []


def grouped_batch(count):
    calls, next_id = [], [100]
    creation = Mock()

    def jobs_creation(number_of_jobs, before_submit=None, **_kwargs):
        before_submit()
        calls.append(f"create {number_of_jobs}")
        creation.get_new_jobs_ids.return_value = [str(next_id[0] + i) for i in range(number_of_jobs)]
        next_id[0] += number_of_jobs
        return True

    creation.jobs_creation.side_effect = jobs_creation
    workflow = JobBatch(
        creation, lambda: calls.append("dashboard") or True, lambda: True,
        lambda job: True, lambda variant: calls.append(f"fill {variant['part_number']}") or [],
        lambda job: f"u/{job}", lambda: calls.append("close"), logging.getLogger(__name__),
        max_jobs_per_creation=10,
    )
    variants = [
        {"part_number": f"P{i}", "ecu_generation": "MG1", "brand": "Honda", "ecu_type": "E"} for i in range(1, count + 1)
    ]
    return workflow, variants, calls


def test_more_than_ten_jobs_are_created_in_groups_of_ten():
    workflow, variants, calls = grouped_batch(24)
    results = workflow.run(variants, "t", "r")
    assert [c for c in calls if c.startswith("create")] == ["create 10", "create 10", "create 4"]
    # each group is filled before the next one is created
    assert calls.index("fill P10") < calls.index("create 10", calls.index("create 10") + 1)
    assert [r["PartNumber"] for r in results] == [f"P{i}" for i in range(1, 25)]
    assert [r["JobId"] for r in results] == [str(100 + i) for i in range(24)]
    assert calls[-1] == "close"


def test_ten_or_fewer_jobs_use_one_creation():
    workflow, variants, calls = grouped_batch(10)
    workflow.run(variants, "t", "r")
    assert [c for c in calls if c.startswith("create")] == ["create 10"]


def test_resume_continues_with_the_next_group_without_recreating_the_first():
    workflow, variants, calls = grouped_batch(12)
    state = {
        "creation_submitted": False,
        "job_ids": [str(i) for i in range(1, 11)],
        "results": [{"PartNumber": f"P{i}", "JobId": str(i), "Url": f"u/{i}"} for i in range(1, 11)],
    }
    results = workflow.run(variants, "t", "r", state=state)
    assert [c for c in calls if c.startswith(("create", "fill"))] == ["create 2", "fill P11", "fill P12"]
    assert len(results) == 12 and len(state["job_ids"]) == 12


def test_unknown_ids_of_a_later_group_are_not_resubmitted():
    workflow, variants, calls = grouped_batch(12)
    state = {"creation_submitted": True, "job_ids": [str(i) for i in range(1, 11)],
             "results": [{"PartNumber": f"P{i}", "JobId": str(i)} for i in range(1, 11)]}
    with pytest.raises(NonRetryableError):
        workflow.run(variants, "t", "r", state=state)
    assert not any(c.startswith("create") for c in calls)
