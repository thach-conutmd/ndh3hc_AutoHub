"""Standalone WebFlow test actions. Qt-free; delegates all WebFlow automation to the reusable session."""
from __future__ import annotations

import logging
from typing import Callable, Protocol

_logger = logging.getLogger(__name__)


class WebFlowTestSession(Protocol):
    def open_dashboard_page(self) -> bool: ...

    def add_instance_member(self, job_id: str, name: str) -> bool: ...

    def quit(self) -> None: ...


def validate_job_number(text: str) -> str:
    job = text.strip()
    if not job:
        raise ValueError("WebFlow Job: enter a job number.")
    if not job.isdigit():
        raise ValueError("WebFlow Job: the job number must contain digits only.")
    return job


class InstanceMemberTestService:
    """Adds a user to a job's Instance Members with the same session the normal WebFlow flow uses."""

    def __init__(
        self,
        session_factory: Callable[[], WebFlowTestSession],
        default_user: Callable[[], str],
    ) -> None:
        self._session_factory = session_factory
        self._default_user = default_user

    def add_user(self, job_text: str, user: str = "") -> str:
        """Return the user name that was added; raise ValueError for invalid input, RuntimeError for WebFlow failures."""
        job = validate_job_number(job_text)
        name = user.strip() or self._default_user().strip()
        if not name:
            raise ValueError("User: enter a user, or set Change Engineer in Settings.")
        session = self._session_factory()
        try:
            if not session.open_dashboard_page():
                raise RuntimeError("Could not open the WebFlow dashboard. Check the WebFlow login and Settings.")
            if not session.add_instance_member(job, name):
                raise RuntimeError(f"Could not add {name} to Instance Members of job {job}.")
            return name
        finally:
            try:
                session.quit()
            except Exception:
                _logger.warning("Failed to close the WebFlow test session.", exc_info=True)
