@echo off
cd /d "%~dp0"
py -3 "%~dp0smartflow_cli.py" %*
exit /b %errorlevel%
