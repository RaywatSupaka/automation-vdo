@echo off
cd /d "%~dp0"
set "SMARTFLOW_PYTHONW_RESOLVED="
for /f "usebackq delims=" %%P in (`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher\resolve_python.ps1"`) do set "SMARTFLOW_PYTHONW_RESOLVED=%%P"
if not defined SMARTFLOW_PYTHONW_RESOLVED (
  echo Pythonw not found.
  pause
  exit /b 1
)
start "" "%SMARTFLOW_PYTHONW_RESOLVED%" "%~dp0app.py"
exit /b 0
