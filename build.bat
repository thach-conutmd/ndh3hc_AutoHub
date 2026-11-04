@echo off
setlocal
cd /d "%~dp0"

echo Cleaning old build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

where python >nul 2>&1 || (echo ERROR: python was not found on PATH. & goto :fail)
where pyinstaller >nul 2>&1 || (echo ERROR: pyinstaller was not found. Run: pip install pyinstaller & goto :fail)
if not exist AutoHub.spec (echo ERROR: AutoHub.spec is missing. & goto :fail)
if not exist autohub\resources\AutoHub.ico (echo ERROR: autohub\resources\AutoHub.ico is missing. & goto :fail)

echo Generating Windows version metadata from APP_VERSION...
python build_version_info.py || (echo ERROR: could not generate version metadata. & goto :fail)

echo Building AutoHub...
pyinstaller --clean --noconfirm AutoHub.spec || (echo ERROR: PyInstaller build failed. & goto :fail)

echo Placing editable resource folders beside AutoHub.exe...
for %%F in (assets templates) do (
    if not exist dist\AutoHub\_internal\%%F (echo ERROR: _internal\%%F was not produced. & goto :fail)
    move /y dist\AutoHub\_internal\%%F dist\AutoHub\%%F >nul || (echo ERROR: could not move %%F. & goto :fail)
)

if not exist dist\AutoHub\AutoHub.exe (echo ERROR: dist\AutoHub\AutoHub.exe was not produced. & goto :fail)
echo Build complete: dist\AutoHub\AutoHub.exe
exit /b 0

:fail
echo Build failed.
exit /b 1
