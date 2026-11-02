import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from autohub.services.WebFlow.job_batch import JobBatch
from autohub.services.WebFlow.job_filler import JobFiller


def batch():
    calls = []
    creation = Mock()
    creation.jobs_creation.side_effect = lambda **_kwargs: calls.append("create") or True
    creation.get_new_jobs_ids.return_value = ["1", "2"]
    workflow = JobBatch(
        creation,
        lambda: calls.append("dashboard") or True,
        lambda: calls.append("new job") or True,
        lambda job: calls.append(f"open {job}") or True,
        lambda variant: calls.append(f"fill {variant['part_number']}") or [],
        lambda job: f"https://example.com/app/ShowJob/{job}",
        lambda: calls.append("close"),
        logging.getLogger(__name__),
    )
    variants = [
        {
            "part_number": part, "ecu_generation": "MG1", "brand": "Honda", "ecu_type": "MG1CS022",
            "general": {
                "delivery_type": "Plant Introduction", "release_class": "Production",
                "release_scope": "Program and Data", "limitations": "NO",
                "safety_monitoring": True, "safety_calibration": False,
                "calibration": True, "data_integration": True,
            },
        }
        for part in ("P1", "P2")
    ]
    return workflow, variants, calls


def test_batch_workflow_is_injected_and_closes_only_after_all_jobs():
    workflow, variants, calls = batch()
    progress = Mock()
    results = workflow.run(variants, "tool", "routing", progress=progress)
    assert calls == ["dashboard", "new job", "create", "open 1", "fill P1", "open 2", "fill P2", "close"]
    assert results == [
        {"PartNumber": "P1", "JobId": "1", "Url": "https://example.com/app/ShowJob/1"},
        {"PartNumber": "P2", "JobId": "2", "Url": "https://example.com/app/ShowJob/2"},
    ]
    assert progress.call_count == 5


@pytest.mark.parametrize("failure,message", [
    ("open_dashboard", "dashboard"), ("open_creation", "job creation"),
    ("creation", "creation failed"), ("ids", "unexpected number"), ("open_job", "job 1"),
])
def test_batch_failure_stops_without_repeating_side_effects(failure, message):
    workflow, variants, calls = batch()
    if failure == "creation":
        workflow.creation.jobs_creation.side_effect = lambda **_kwargs: calls.append("create") or False
    elif failure == "ids":
        workflow.creation.get_new_jobs_ids.return_value = ["1"]
    elif failure == "open_job":
        workflow.open_job = Mock(return_value=False)
    else:
        setattr(workflow, failure, Mock(return_value=False))
    with pytest.raises(RuntimeError, match=message):
        workflow.run(variants, "tool", "routing")
    assert not any(call.startswith("fill") for call in calls)
    assert "close" not in calls
    assert workflow.creation.jobs_creation.call_count <= 1


def test_empty_batch_does_not_touch_browser():
    workflow, _variants, calls = batch()
    assert workflow.run([], "tool", "routing") == []
    assert calls == []


def test_fill_failure_leaves_cleanup_to_session_owner():
    workflow, variants, calls = batch()
    workflow.fill_job = Mock(side_effect=RuntimeError("fill failed"))
    with pytest.raises(RuntimeError, match="fill failed"):
        workflow.run(variants, "tool", "routing")
    workflow.fill_job.assert_called_once()
    assert "open 2" not in calls and "close" not in calls


def test_job_filler_accepts_plan_without_executing_during_planning():
    action = Mock(return_value=True)
    plan = Mock()
    plan.steps.return_value = [("Custom step", action)]
    general = SimpleNamespace(select_general_tab=Mock(return_value=True), skipped_fields=[])
    body = SimpleNamespace(tab=SimpleNamespace(generaltab=general))
    filler = JobFiller(None, body, plan=plan)
    variant = {"part_number": "P"}
    assert filler.steps(variant) == [("Custom step", action)]
    action.assert_not_called()
    assert filler.fill(variant) == []
    action.assert_called_once()
