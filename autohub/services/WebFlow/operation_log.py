"""Logs each WebFlow operation once: name, context, duration, result and error details.

Only the values a context function explicitly returns are logged, so credentials, cookies and
page data never reach the log. Exceptions are logged and re-raised unchanged.
"""
from __future__ import annotations

import functools
import inspect
import logging
import time
from typing import Any, Callable
from urllib.parse import urlsplit

SUCCESS = "Success"
FAILED = "Failed"
CANCELLED = "Cancelled"

ContextFn = Callable[[dict[str, Any]], str]
OutcomeFn = Callable[[Any], str]


def job_id_from_link(link: str) -> str:
    return urlsplit(link).path.rstrip("/").rsplit("/", 1)[-1]


def _success_or_failed(result: Any) -> str:
    return FAILED if result is False else SUCCESS


def logged_operation(
    logger: logging.Logger,
    name: str,
    context: ContextFn | None = None,
    outcome: OutcomeFn = _success_or_failed,
):
    """Wrap a WebFlow method so it logs start, result and errors via ``logger``.

    ``context`` receives the bound arguments (without ``self``) and returns a short description.
    ``outcome`` maps the return value to Success, Failed or Cancelled.
    """

    def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            arguments = {key: value for key, value in bound.arguments.items() if key != "self"}
            details = context(arguments) if context else ""
            suffix = f" | {details}" if details else ""
            logger.info("WebFlow operation %s started%s", name, suffix)
            started = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            except Exception as error:
                elapsed = time.perf_counter() - started
                logger.error(
                    "WebFlow operation %s%s | Result: %s (%.1fs) | error: %s: %s",
                    name, suffix, FAILED, elapsed, type(error).__name__, error, exc_info=True,
                )
                raise
            elapsed = time.perf_counter() - started
            label = outcome(result)
            log = logger.warning if label == FAILED else logger.info
            log("WebFlow operation %s%s | Result: %s (%.1fs)", name, suffix, label, elapsed)
            return result

        return wrapper

    return decorate
