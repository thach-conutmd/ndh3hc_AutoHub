"""Execute a job-fill plan, enforcing existing failure and allocation policies."""
from __future__ import annotations

import logging
from typing import Any, Callable
from .job_plan import JobPlan, StepPlan, describe_values
from .job_plan import ECU_FIELDS as ECU_FIELDS, CUSTOMER_FIELDS as CUSTOMER_FIELDS, GENERAL_FIELDS as GENERAL_FIELDS
from .job_plan import display_value as display_value
from .step_log import Step, run_step, run_steps

_logger = logging.getLogger(__name__)

#: Number imports that allocate on the server: step name -> variant key / page attribute.
NUMBER_IMPORTS = {
    "General: Import software part number from pool": "imported_software_part_number",
    "General: ECR Import": "imported_ecr_number",
}


class JobFiller:
    """Depends only on the page objects it is given (``side_menu_bar`` and ``body``)."""

    def __init__(self, side_menu_bar: Any, body: Any, plan: StepPlan | None = None):
        self.side_menu_bar = side_menu_bar
        self.body = body
        self.plan = plan if plan is not None else JobPlan(side_menu_bar, body)
        #: Persists retry progress; called before and after every number import.
        self.checkpoint: Callable[[], None] = lambda: None

    def steps(self, variant: dict) -> list[Step]:
        """The steps that fill the General, ECU and Customer tabs of the open job and save it."""
        return self.plan.steps(variant)

    def fill(self, variant: dict) -> list[str]:
        """Fills and saves the open job; returns warnings for requested values not applied.

        Raises RuntimeError naming every failed step."""
        part_number = variant["part_number"]
        attempted = variant.setdefault("attempted_imports", [])
        for name, key in NUMBER_IMPORTS.items():
            if name not in attempted:
                variant.pop(key, None)
        general = self.body.tab.generaltab
        general.skipped_fields.clear()
        _logger.info("[%s] Values to fill: %s", part_number, describe_values(variant))
        if not run_step(_logger, f"[{part_number}] Select the General tab", general.select_general_tab):
            raise RuntimeError("Could not select the General tab.")

        notes: list[str] = []
        steps = self._guard_imports(self.steps(variant), variant, general, notes)
        if variant.get("ecr"):
            for step in steps:
                if not run_step(_logger, f"[{part_number}] {step[0]}", step[1], *step[2:]):
                    raise RuntimeError(f"Could not fill {part_number}: {step[0]}.")
                if step[0] == "General: ECR Import":
                    variant["imported_ecr_number"] = general.imported_ecr_number
                if step[0] == "General: Import software part number from pool":
                    variant["imported_software_part_number"] = general.imported_software_part_number
            return list(general.skipped_fields) + notes
        picker_index = next(
            (index for index, step in enumerate(steps) if step[0].startswith("General: Pick PST_Lib")),
            None,
        )
        if picker_index is None:
            failed = run_steps(
                _logger, [(f"[{part_number}] {step[0]}", *step[1:]) for step in steps]
            )
        else:
            failed = run_steps(
                _logger,
                [(f"[{part_number}] {step[0]}", *step[1:]) for step in steps[:picker_index]],
            )
            picker = steps[picker_index]
            if not run_step(_logger, f"[{part_number}] {picker[0]}", picker[1], *picker[2:]):
                raise RuntimeError(
                    f"Could not select a PST_Lib entry matching PVER {picker[2]!r} for {part_number}."
                )
            failed += run_steps(
                _logger,
                [(f"[{part_number}] {step[0]}", *step[1:]) for step in steps[picker_index + 1:]],
            )
        if (
            variant.get("hardware", {}).get("lead_plant")
            and not variant.get("imported_software_part_number")
            and general.imported_software_part_number
        ):
            variant["imported_software_part_number"] = general.imported_software_part_number
        if failed:
            raise RuntimeError(f"Could not fill all values for {part_number}. Failed: {'; '.join(failed)}")
        return list(general.skipped_fields) + notes

    def _guard_imports(self, steps: list[Step], variant: dict, general: Any, notes: list[str]) -> list[Step]:
        """Number imports run at most once per variant, across retries and app restarts."""
        attempted = variant["attempted_imports"]
        guarded = []
        for step in steps:
            key = NUMBER_IMPORTS.get(step[0])
            if key is None:
                guarded.append(step)
            elif step[0] in attempted:
                _logger.info("[%s] %s was already clicked in an earlier attempt; not clicking again", variant["part_number"], step[0])
                if not variant.get(key):
                    notes.append(f"{step[0]} was clicked in an earlier attempt but its number was not read; check the job in WebFlow.")
                elif key == "imported_software_part_number":
                    guarded.append((
                        "General: Copy allocated Software part number",
                        general.copy_software_part_number, variant[key],
                    ))
            else:
                guarded.append((step[0], self._recorded_import(step, key, variant, general), *step[2:]))
        return guarded

    def _recorded_import(self, step: Step, key: str, variant: dict, general: Any) -> Callable[..., bool]:
        def run(*args) -> bool:
            variant["attempted_imports"].append(step[0])
            self.checkpoint()
            ok = step[1](*args)
            number = getattr(general, key, "")
            if number and (ok or key == "imported_software_part_number"):
                variant[key] = number
                self.checkpoint()
            return ok
        return run
