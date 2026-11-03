"""WebFlow job creation with ownership of the browser session (no Qt)."""
from __future__ import annotations

import copy
import logging
import time
from dataclasses import asdict, dataclass, fields
from contextlib import AbstractContextManager, nullcontext
from typing import Callable, Protocol

from autohub.core.batch_journal import BatchJournal, NonRetryableError
from autohub.core.ports import SheetSession, WebFlowLinkWriter, WebFlowNumberWriter
from autohub.core.webflow_numbers import number_updates
from autohub.core.progress import ProgressCallback, no_progress
from autohub.core.settings_keys import DEFAULT_WEBFLOW_MAX_ATTEMPTS, WEBFLOW_ATTEMPTS_LIMIT

_logger = logging.getLogger(__name__)

MAX_ATTEMPTS = DEFAULT_WEBFLOW_MAX_ATTEMPTS
CANCEL_REASON = "Test version no longer required."


def ecr_notes(project: str, event_name: str) -> str:
    """ECR notes written to every job; generated from the variant's Project Purpose."""
    return f"This container is for {project} {event_name} event."


@dataclass(frozen=True)
class WebFlowConfig:
    driver_path: str
    base_url: str
    tool_version: str
    routing: str
    trace_dir: str = ""  #: when set, the page of every step is recorded there
    change_engineer: str = ""
    cost_allocation: str = ""
    change_reason: str = ""
    max_attempts: int = DEFAULT_WEBFLOW_MAX_ATTEMPTS
    retry_enabled: bool = True

    def __post_init__(self) -> None:
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= WEBFLOW_ATTEMPTS_LIMIT:
            raise ValueError(f"Maximum WebFlow attempts must be an integer from 1 to {WEBFLOW_ATTEMPTS_LIMIT}.")
        if type(self.retry_enabled) is not bool:
            raise ValueError("WebFlow automatic retries must be enabled or disabled.")


class WebFlowSession(Protocol):
    """The part of the WebFlow browser automation this service uses."""

    def create_and_fill_jobs(
        self, variants: list, tool_version: str, routing: str, progress: ProgressCallback = no_progress,
        state: dict | None = None, checkpoint: Callable[[], None] | None = None,
    ) -> list: ...

    def cancel_job(self, job_id: str, reason: str) -> bool: ...

    def quit(self) -> None: ...


class WebFlowJobService:
    def __init__(
        self,
        webflow_factory: Callable[..., WebFlowSession],
        master_sheet_factory: Callable[[str], SheetSession] | None = None,
        session_factory: Callable[[], AbstractContextManager] = nullcontext,
        journal: BatchJournal | None = None,
        retry_delay_seconds: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._journal = journal
        self._retry_delay = retry_delay_seconds
        self._sleep = sleep
        self._webflow_factory = webflow_factory
        self._master_sheet_factory = master_sheet_factory
        self._session = session_factory
        self._webflow: WebFlowSession | None = None
        self.last_elapsed_seconds = 0.0
        self.last_general_options: dict[str, list[str]] = {}

    def create_jobs(
        self,
        variants: list[dict],
        config: WebFlowConfig,
        progress: ProgressCallback = no_progress,
        master_sheet_path: str = "",
    ) -> list[dict]:
        state = {
            "config": asdict(config),
            "master_sheet_path": master_sheet_path,
            "variants": copy.deepcopy(variants),
        }
        return self._run(state, variants, progress)

    def pending_batch(self) -> dict | None:
        """The progress of a batch that did not finish (e.g. the app crashed), if any."""
        state = self._journal.load() if self._journal else None
        return state if state and state.get("variants") else None

    def discard_pending_batch(self) -> None:
        if self._journal:
            _logger.info("Discarding the unfinished WebFlow batch")
            self._journal.clear()

    def cancel_pending_batch(self, progress: ProgressCallback = no_progress) -> None:
        """Cancels every WebFlow job of the unfinished batch, then drops the retry record.

        The record is kept when a cancellation fails, so the user can try again; jobs already
        cancelled are remembered and skipped on the next attempt."""
        state = self.pending_batch()
        if state is None:
            return
        job_ids = list(state.get("job_ids", []))
        cancelled = state.setdefault("cancelled_job_ids", [])
        remaining = [job_id for job_id in job_ids if job_id not in cancelled]
        if remaining:
            known = {f.name for f in fields(WebFlowConfig)}
            config = WebFlowConfig(**{k: v for k, v in state["config"].items() if k in known})
            self.shutdown()
            try:
                self._webflow = self._webflow_factory(
                    driver_path=config.driver_path, base_url=config.base_url, trace_dir=config.trace_dir
                )
                for job_id in remaining:
                    progress(f"Cancelling WebFlow job {job_id}...")
                    if not self._webflow.cancel_job(job_id, CANCEL_REASON):
                        raise RuntimeError(
                            f"WebFlow job {job_id} could not be cancelled. The retry was kept; try Discard again."
                        )
                    cancelled.append(job_id)
                    if self._journal:
                        self._journal.save(state)
            finally:
                self.shutdown()
        self.discard_pending_batch()

    def resume_jobs(self, progress: ProgressCallback = no_progress) -> list[dict]:
        """Continues the unfinished batch, skipping jobs already created and completed."""
        state = self.pending_batch()
        if state is None:
            raise RuntimeError("There is no unfinished WebFlow job creation to continue.")
        _logger.info("Resuming the unfinished WebFlow batch: %d job(s) done", len(state.get("results", [])))
        return self._run(state, [], progress)

    def _run(self, state: dict, variants: list[dict], progress: ProgressCallback) -> list[dict]:
        started = time.perf_counter()
        self.last_elapsed_seconds = 0.0
        self.last_general_options = {}
        completed = False
        try:
            results = self._create_jobs(state, variants, progress)
            completed = True
            return results
        finally:
            self.last_elapsed_seconds = time.perf_counter() - started
            _logger.info(
                "WebFlow jobs %s: %d requested; total time %.1f seconds (browser, filling, saving and link writing)",
                "completed" if completed else "failed", len(state["variants"]), self.last_elapsed_seconds,
            )

    def _create_jobs(self, state: dict, variants: list[dict], progress: ProgressCallback) -> list[dict]:
        """Creates the jobs, then writes each job link into the Master Sheet (when a path is given).

        A failure to write the links is returned as "LinkError" on the results; the jobs exist either way."""
        known = {f.name for f in fields(WebFlowConfig)}
        config = WebFlowConfig(**{k: v for k, v in state["config"].items() if k in known})
        master_sheet_path = state.get("master_sheet_path", "")
        _logger.info("Creating WebFlow jobs for %s", [v["part_number"] for v in state["variants"]])
        results = self._create(state, variants, config, progress)
        for item in results:
            _logger.info("Job %s created for %s: %s", item.get("JobId"), item.get("PartNumber"), item.get("Url"))
        if master_sheet_path:
            error = self._write_links(master_sheet_path, results, progress)
            if error:
                _logger.error("Writing the WebFlow links to the Master Sheet failed: %s", error)
                for item in results:
                    item["LinkError"] = error
            else:
                _logger.info("Wrote %d WebFlow link(s) to the Master Sheet", len(results))
        else:
            _logger.info("No Master Sheet path is set, so the links were not written")
        numbers = number_updates(results)
        if numbers:
            error = self._write_numbers(master_sheet_path, numbers, progress)
            if error:
                _logger.error("Writing WebFlow numbers failed: %s", error)
                for item in results:
                    item["NumberError"] = error
        self.discard_pending_batch()
        return results

    def _write_numbers(self, path: str, numbers: dict[str, dict[str, str]], progress: ProgressCallback) -> str:
        if not path or self._master_sheet_factory is None:
            return "No Master Sheet path or writer is configured."
        try:
            with self._session():
                progress("Writing SW Part Number and ECR Number to the Master Sheet...")
                sheet = self._master_sheet_factory(path)
                try:
                    sheet.open()
                    if not isinstance(sheet, WebFlowNumberWriter):
                        return "This Master Sheet layout cannot write WebFlow numbers."
                    written = sheet.write_webflow_numbers(numbers)
                    if written != len(numbers):
                        return f"Only {written} of {len(numbers)} variants had their numbers written."
                finally:
                    sheet.close()
        except Exception as error:
            return str(error)
        return ""

    def _write_links(self, path: str, results: list[dict], progress: ProgressCallback) -> str:
        if self._master_sheet_factory is None:
            return ""
        links = {item["PartNumber"]: item["Url"] for item in results if item.get("Url")}
        try:
            with self._session():
                progress("Writing the WebFlow links to the Master Sheet...")
                sheet = self._master_sheet_factory(path)
                try:
                    sheet.open()
                    if not isinstance(sheet, WebFlowLinkWriter):
                        return "This Master Sheet layout has no WebFlow link column."
                    sheet.write_webflow_links(links)
                finally:
                    sheet.close()
        except Exception as error:
            return str(error)
        return ""

    def _create(self, state: dict, variants: list[dict], config: WebFlowConfig, progress: ProgressCallback) -> list[dict]:
        ecr = {
            "change_engineer": config.change_engineer,
            "cost_allocation": config.cost_allocation,
            "change_reason": config.change_reason,
        }
        if any(ecr.values()):
            missing = [key for key, value in ecr.items() if not value.strip()]
            if missing:
                raise ValueError(f"Complete ECR settings before creating jobs: {', '.join(missing)}.")
            pending = [job_variant for job_variant in state["variants"] if "ecr" not in job_variant]
            unknown = [v.get("part_number", "?") for v in pending if not (v.get("project") and v.get("event_name"))]
            if unknown:
                raise ValueError(
                    "Cannot write ECR notes: Project Purpose has no project and event for "
                    f"{', '.join(unknown)}. Use '<Project> - <Event>_<MP>' and reload the variants."
                )
            for job_variant in pending:
                job_variant["ecr"] = {**ecr, "ecr_notes": ecr_notes(job_variant["project"], job_variant["event_name"])}
        for variant in variants:
            variant.pop("imported_ecr_number", None)
        try:
            return self._attempts(state, config, progress)
        finally:
            # Keep allocated numbers even if a later tab or job fails.
            for variant, job_variant in zip(variants, state["variants"]):
                if job_variant.get("imported_ecr_number"):
                    variant["imported_ecr_number"] = job_variant["imported_ecr_number"]

    def _attempts(self, state: dict, config: WebFlowConfig, progress: ProgressCallback) -> list[dict]:
        """Runs the configured number of attempts, resuming from saved progress each time."""
        job_variants = state["variants"]
        max_attempts = config.max_attempts if config.retry_enabled else 1

        def checkpoint() -> None:
            if self._journal:
                self._journal.save(state)

        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            state["attempt"] = attempt
            checkpoint()
            if attempt > 1:
                _logger.warning("Retrying WebFlow job creation (attempt %d of %d) after: %s", attempt, max_attempts, last_error)
                progress(f"Attempt {attempt} of {max_attempts} after error: {last_error}")
                self._sleep(self._retry_delay)
            self.shutdown()
            try:
                _logger.info("Starting the browser (base URL %s, tool version %s, routing %s)", config.base_url, config.tool_version, config.routing)
                progress("Starting the browser...")
                self._webflow = self._webflow_factory(
                    driver_path=config.driver_path, base_url=config.base_url, trace_dir=config.trace_dir
                )
                results = self._webflow.create_and_fill_jobs(
                    job_variants, tool_version=config.tool_version, routing=config.routing, progress=progress,
                    state=state, checkpoint=checkpoint,
                )
                observed_options = getattr(self._webflow, "general_options", {})
                if isinstance(observed_options, dict):
                    self.last_general_options = {
                        key: list(values)
                        for key, values in observed_options.items()
                        if isinstance(values, (list, tuple)) and values
                    }
                return results
            except (ValueError, NonRetryableError):
                self.discard_pending_batch()
                raise
            except Exception as error:
                _logger.exception("WebFlow job creation attempt %d of %d failed", attempt, max_attempts)
                last_error = error
            finally:
                self.shutdown()
        message = f"{last_error}\n\nWebFlow job creation failed after {max_attempts} attempts."
        if self._journal:
            message += " The progress is saved; AutoHub offers to continue the next time it opens."
        raise RuntimeError(message)

    def shutdown(self) -> None:
        if self._webflow is None:
            return
        try:
            self._webflow.quit()
        except Exception:
            _logger.debug("The browser was already closed")
        self._webflow = None
