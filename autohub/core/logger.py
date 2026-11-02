"""Centralized logging setup for the app."""
import logging
from contextlib import ExitStack
from pathlib import Path

from autohub.config import LOG_DIR


LOGGING_ENABLED_KEY = "logging_enabled"
LOG_FILE_PATH = LOG_DIR / "autohub.log"


def clear_log_file() -> None:
    """Truncate the application log without replacing the file or its active handlers."""
    with ExitStack() as stack:
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == LOG_FILE_PATH.resolve():
                handler.acquire()
                stack.callback(handler.release)
                handler.flush()
        with LOG_FILE_PATH.open("r+", encoding="utf-8") as stream:
            stream.truncate(0)


def logging_enabled(settings: dict) -> bool:
    return bool(settings.get(LOGGING_ENABLED_KEY, True))


def set_logging_enabled(enabled: bool) -> None:
    """Switch every log record (file and console) on or off at runtime."""
    logging.disable(logging.NOTSET if enabled else logging.CRITICAL)


def setup_logging(level: int = logging.INFO) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
