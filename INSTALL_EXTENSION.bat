@echo off
setlocal
cd /d "%~dp0"
set "SMARTFLOW_INSTALL_ROOT=%~dp0"
rem Use the canonical source folder; verify the release and desktop agree first.
powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference = 'Stop'; try { $root = $env:SMARTFLOW_INSTALL_ROOT; $extensionDir = Join-Path $root 'browser_extension'; $manifest = Get-Content -Raw -LiteralPath (Join-Path $extensionDir 'manifest.json') | ConvertFrom-Json; $release = Get-Content -Raw -LiteralPath (Join-Path $root 'CURRENT_RELEASE.json') | ConvertFrom-Json; $bridge = Get-Content -Raw -LiteralPath (Join-Path $root 'core/local_bridge.py'); $required = [regex]::Match($bridge, 'REQUIRED_EXTENSION_VERSION\s*=\s*\x22([^\x22]+)\x22'); if (-not $required.Success) { throw 'Cannot read the desktop required Extension version.' }; $version = [string]$manifest.version; if (-not $version -or $version -ne $required.Groups[1].Value -or $version -ne [string]$release.runtime.extension_version) { throw ('Extension version mismatch: source=' + $version + ', desktop=' + $required.Groups[1].Value + ', release=' + $release.runtime.extension_version) }; Write-Host ''; Write-Host ('SmartFlow AI Extension version: ' + $version); Write-Host ('Select this folder: ' + $extensionDir); Write-Host ''; Write-Host '1. Enable Developer mode in Chrome.'; Write-Host '2. Click Load unpacked and select the folder shown above.'; Write-Host ('3. Confirm that Chrome shows SmartFlow AI version ' + $version + '.'); Write-Host 'If this folder is already installed, click Reload on that Extension.'; Start-Process 'chrome.exe' -ArgumentList 'chrome://extensions'; Start-Process 'explorer.exe' -ArgumentList ([char]34 + $extensionDir + [char]34) } catch { Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red; exit 1 }"
if errorlevel 1 (
    echo.
    echo Extension validation failed. Correct the error before installing.
    pause
    exit /b 1
)
pause
endlocal
