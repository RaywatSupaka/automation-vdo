@echo off
setlocal
cd /d "%~dp0"

set "SMARTFLOW_BUILD_PYTHON=%~dp0.build-env\Scripts\python.exe"
if not exist "%SMARTFLOW_BUILD_PYTHON%" (
    echo SmartFlow build environment was not found at .build-env\Scripts\python.exe.
    echo Prepare .build-env before building a customer installer.
    set "SMARTFLOW_BUILD_RESULT=2"
    goto finish
)

"%SMARTFLOW_BUILD_PYTHON%" "%~dp0tools\build_installer_one_click.py" %*
set "SMARTFLOW_BUILD_RESULT=%ERRORLEVEL%"

:finish
echo.
if "%SMARTFLOW_BUILD_RESULT%"=="0" (
    echo SmartFlow installer task completed.
) else (
    echo SmartFlow installer was NOT approved or completed. Exit code: %SMARTFLOW_BUILD_RESULT%
)
if "%~1"=="" pause
exit /b %SMARTFLOW_BUILD_RESULT%
