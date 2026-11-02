"""Architecture rules from docs/SOLID_REQUIREMENTS.md, enforced on the source text (no imports executed)."""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent / "autohub"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _files(*parts: str) -> list[Path]:
    return sorted(ROOT.joinpath(*parts).rglob("*.py"))


def _violations(files: list[Path], forbidden: tuple[str, ...]) -> list[str]:
    return [
        f"{path.relative_to(ROOT.parent)} imports {name}"
        for path in files
        for name in sorted(_imports(path))
        if name.startswith(forbidden)
    ]


def test_ui_and_modules_never_import_services():
    # DIP-1: only bootstrap.py (the composition root) wires concrete services.
    assert _violations(_files("modules") + _files("ui"), ("autohub.services",)) == []


def test_services_never_import_qt_modules_or_ui():
    assert _violations(_files("services"), ("PySide6", "autohub.modules", "autohub.ui", "autohub.bootstrap")) == []


def test_core_never_imports_services_or_modules():
    assert _violations(_files("core"), ("autohub.services", "autohub.modules", "autohub.ui", "autohub.bootstrap")) == []


@pytest.mark.parametrize(
    "parser",
    [
        ROOT / "services" / "EcuInfoSheet" / "parser.py",
        ROOT / "services" / "SystemMatrix" / "parser.py",
        ROOT / "services" / "HWInfo" / "parser.py",
        ROOT / "services" / "KickOff" / "parser.py",
        ROOT / "modules" / "comparison" / "xml_parser.py",
    ],
)
def test_parsers_only_parse(parser):
    # SRP-5: no Excel, Qt, logging or file access inside a parser.
    assert _violations([parser], ("win32com", "PySide6", "logging", "msoffcrypto", "openpyxl", "olefile", "pptx")) == []


def test_webflow_workflows_do_not_depend_on_browser_or_page_implementations():
    files = [
        ROOT / "services" / "WebFlow" / name
        for name in ("job_batch.py", "job_plan.py", "job_filler.py")
    ]
    assert _violations(files, ("selenium", "PySide6", "Body", "browser")) == []


def test_webflow_python_modules_share_one_directory():
    package = ROOT / "services" / "WebFlow"
    assert all(path.parent == package for path in package.rglob("*.py"))


def test_only_the_settings_store_knows_where_settings_live():
    # DIP-5
    offenders = [p for p in _files("") if "APPDATA" in p.read_text(encoding="utf-8") and p.name != "settings.py"]
    assert offenders == []


def test_only_the_composition_root_names_concrete_services():
    # DIP-4: modules receive factories; nothing but bootstrap.py calls the default constructors.
    offenders = [
        f"{p.relative_to(ROOT.parent)}"
        for p in _files("modules")
        if any(name in p.read_text(encoding="utf-8") for name in ("default_settings_store", "VariantService()", "WebFlowJobService()"))
    ]
    assert offenders == []


def test_no_module_directory_is_left_without_being_built():
    from autohub.bootstrap import build_modules
    from tests.fakes import MemorySettings

    built = {type(m).__module__.split(".")[2] for m in build_modules(MemorySettings())}
    on_disk = {p.name for p in (ROOT / "modules").iterdir() if p.is_dir() and not p.name.startswith("__")}
    assert on_disk == built, "a feature module on disk is not registered in bootstrap.build_modules()"
