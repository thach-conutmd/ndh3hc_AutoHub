"""Runs browser-automation steps and logs each one: start, outcome, duration (pure; no Selenium)."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Protocol, Sequence

#: (description, action, *arguments) - the action returns True on success.
Step = tuple


class StepObserver(Protocol):
    # an observer may also define on_step_start(name), called before the step runs
    def on_step(self, name: str, ok: bool, seconds: float, error: str = "") -> None: ...


_observer: StepObserver | None = None


def set_step_observer(observer: StepObserver | None) -> None:
    """Every finished step is reported to the observer (e.g. a page recorder); None switches it off."""
    if observer is not None and not callable(getattr(observer, "on_step", None)):
        raise TypeError("a step observer needs an on_step(name, ok, seconds, error) method")
    global _observer
    _observer = observer


def _begin(name: str) -> None:
    start = getattr(_observer, "on_step_start", None)
    if start is not None:
        start(name)


def _report(name: str, ok: bool, seconds: float, error: str = "") -> None:
    if _observer is not None:
        _observer.on_step(name, ok, seconds, error)


def record_checkpoint(name: str, ok: bool, seconds: float = 0.0, error: str = "") -> None:
    """Reports a point inside a running step (e.g. after a wait) to the observer, without running an action."""
    _report(name, ok, seconds, error)


def run_step(logger: logging.Logger, name: str, action: Callable[..., Any], *args: Any) -> bool:
    logger.info("Step: %s", name)
    _begin(name)
    started = time.perf_counter()
    try:
        ok = bool(action(*args))
    except Exception:
        elapsed = time.perf_counter() - started
        logger.exception("Step raised: %s (after %.1fs)", name, elapsed)
        _report(name, False, elapsed, "raised an exception")
        raise
    elapsed = time.perf_counter() - started
    if ok:
        logger.info("Step OK: %s (%.1fs)", name, elapsed)
    else:
        logger.warning("Step FAILED: %s (%.1fs)", name, elapsed)
    _report(name, ok, elapsed)
    return ok


def run_steps(logger: logging.Logger, steps: Sequence[Step]) -> list[str]:
    """Runs every step, even after a failure, and returns the names of the failed ones."""
    return [step[0] for step in steps if not run_step(logger, step[0], step[1], *step[2:])]
