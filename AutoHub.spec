# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)
VERSION_FILE = ROOT / "build" / "version_info.txt"
ICON_FILE = ROOT / "autohub" / "resources" / "AutoHub.ico"
TEMPLATES_DIR = ROOT / "datas" / "templates"
RESOURCES_DIR = ROOT / "autohub" / "resources"

for required in (ROOT / "main.py", ICON_FILE, VERSION_FILE, TEMPLATES_DIR, RESOURCES_DIR):
    if not required.exists():
        raise SystemExit(f"AutoHub.spec: required build input is missing: {required}")

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(RESOURCES_DIR), "assets"),
        (str(TEMPLATES_DIR), "templates"),
    ],
    hiddenimports=[
        # Windows COM automation (Excel, ADODB); imported lazily in the app, so listed explicitly.
        "pythoncom",
        "pywintypes",
        # pywin32 runtime dependency of win32com.client (date/time conversion); no PyInstaller hook provides it.
        "win32timezone",
        "win32com.client",
        "win32com.client.gencache",
        # Every win32com submodule (client, dynamic, gencache, gen_py, ...) is loaded at runtime by Excel automation.
        *collect_submodules("win32com"),
        # selenium.webdriver resolves Edge/Chrome/etc. lazily (webdriver.Edge in WebFlow.py), so collect every submodule.
        *collect_submodules("selenium"),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoHub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_FILE),
    version=str(VERSION_FILE),
)

# One-folder output: dist/AutoHub/ holds AutoHub.exe and _internal/ (DLLs and modules).
# build.bat moves the editable resource folders (assets/, templates/) beside the EXE after the build.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AutoHub",
)
