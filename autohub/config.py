"""App-wide constants and paths."""
import sys
from pathlib import Path

APP_NAME = "AutoHub"
APP_VERSION = "1.0.0"

IS_FROZEN = bool(getattr(sys, "frozen", False))
_SOURCE_ROOT = Path(__file__).resolve().parent.parent

# Folder that holds AutoHub.exe when frozen (dist/AutoHub/), otherwise the repository root.
BASE_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else _SOURCE_ROOT
# Read-only bundled resources, shipped beside the EXE as assets/ and templates/ (build.bat moves them there).
# The _internal fallback covers a plain `pyinstaller AutoHub.spec` run that has not been relocated yet.
_FROZEN_LOOKUP = [BASE_DIR, BASE_DIR / "_internal", Path(getattr(sys, "_MEIPASS", BASE_DIR))]


def _frozen_folder(name: str) -> Path:
    return next((root / name for root in _FROZEN_LOOKUP if (root / name).is_dir()), BASE_DIR / name)


RESOURCES_DIR = _frozen_folder("assets") if IS_FROZEN else _SOURCE_ROOT / "autohub" / "resources"
TEMPLATES_DIR = _frozen_folder("templates") if IS_FROZEN else _SOURCE_ROOT / "datas" / "templates"
ICONS_DIR = RESOURCES_DIR / "icons"
LOGO_PATH = RESOURCES_DIR / "logo.png"
ICON_PATH = RESOURCES_DIR / "AutoHub.ico"
HOME_BANNER_PATH = RESOURCES_DIR / "home_banner.png"

# Writable location for logs; a frozen build must not write beside the EXE.
LOG_DIR = Path.home() / "AppData" / "Local" / APP_NAME / "logs" if IS_FROZEN else BASE_DIR / "logs"


def resource_path(*parts: str) -> Path:
    """Path relative to the application folder (beside the EXE when frozen, repository root otherwise)."""
    return BASE_DIR.joinpath(*parts)


def require_resource(*parts: str) -> Path:
    """Like resource_path, but raises a clear error when the bundled file is missing."""
    path = resource_path(*parts)
    if not path.is_file():
        raise FileNotFoundError(f"Required {APP_NAME} resource is missing: {path}")
    return path
