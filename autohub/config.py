"""App-wide constants and paths."""
import sys
from pathlib import Path

APP_NAME = "AutoHub"
APP_VERSION = "1.0.0"

IS_FROZEN = bool(getattr(sys, "frozen", False))
_SOURCE_ROOT = Path(__file__).resolve().parent.parent

# Read-only bundled resources: the PyInstaller extraction folder when frozen, the repository otherwise.
BASE_DIR = Path(sys._MEIPASS) if IS_FROZEN else _SOURCE_ROOT
RESOURCES_DIR = BASE_DIR / "autohub" / "resources"
ICONS_DIR = RESOURCES_DIR / "icons"
LOGO_PATH = RESOURCES_DIR / "logo.png"
ICON_PATH = RESOURCES_DIR / "AutoHub.ico"
HOME_BANNER_PATH = RESOURCES_DIR / "home_banner.png"

# Writable location for logs; a frozen build must not write into the extraction folder.
LOG_DIR = Path.home() / "AppData" / "Local" / APP_NAME / "logs" if IS_FROZEN else BASE_DIR / "logs"


def resource_path(*parts: str) -> Path:
    """Path to a bundled read-only resource, valid in development and in the PyInstaller EXE."""
    return BASE_DIR.joinpath(*parts)


def require_resource(*parts: str) -> Path:
    """Like resource_path, but raises a clear error when the bundled file is missing."""
    path = resource_path(*parts)
    if not path.is_file():
        raise FileNotFoundError(f"Required {APP_NAME} resource is missing: {path}")
    return path
