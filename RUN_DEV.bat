@echo off
setlocal
cd /d "%~dp0"
set "SMARTFLOW_DEV_BYPASS_MEMBERSHIP=1"
call "%~dp0RUN.bat"
endlocal
