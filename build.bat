@echo off
setlocal
cd /d "%~dp0"

echo Cleaning old build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Generating Windows version metadata...
python build_version_info.py || goto :fail

echo Building AutoHub...
pyinstaller --clean --noconfirm AutoHub.spec || goto :fail

echo Build complete: dist\AutoHub.exe
exit /b 0

:fail
echo Build failed.
exit /b 1
