"""Centralized logging setup for the app."""
import logging
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryFile

from autohub.config import LOG_DIR


LOGGING_ENABLED_KEY = "logging_enabled"
LOG_LOCATION_KEY = "log_location"
LOG_FILE_PATH = LOG_DIR / "autohub.log"
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def log_location(settings: dict) -> Path:
    return Path(settings.get(LOG_LOCATION_KEY) or LOG_DIR).expanduser().resolve()


def log_file_path() -> Path:
    return LOG_FILE_PATH


def set_log_location(location: str | Path) -> Path:
    """Validate the folder and switch the application file handler without losing other handlers."""
    global LOG_FILE_PATH
    if not str(location).strip():
        raise ValueError("Select a log folder.")
    folder = Path(location).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    with TemporaryFile(dir=folder) as probe:
        probe.write(b"AutoHub log folder check")
        probe.flush()
    path = folder / "autohub.log"
    replacement = logging.FileHandler(path, encoding="utf-8")
    replacement.setFormatter(logging.Formatter(_LOG_FORMAT))
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == LOG_FILE_PATH.resolve():
            replacement.setLevel(handler.level)
            replacement.setFormatter(handler.formatter or logging.Formatter(_LOG_FORMAT))
            root.removeHandler(handler)
            handler.close()
    root.addHandler(replacement)
    LOG_FILE_PATH = path
    return folder


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


def setup_logging(level: int = logging.INFO, location: str | Path = LOG_DIR) -> None:
    set_log_location(location)
    root = logging.getLogger()
    root.setLevel(level)
    if not any(handler.name == "autohub.console" for handler in root.handlers):
        console = logging.StreamHandler()
        console.set_name("autohub.console")
        console.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(console)
