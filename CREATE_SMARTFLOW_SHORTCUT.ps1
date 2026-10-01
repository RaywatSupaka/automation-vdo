$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "SmartFlow AI.lnk"
$iconPath = Join-Path $projectRoot "assets\smartflow_icon.ico"
$launcherPath = Join-Path $projectRoot "SmartFlow AI.exe"

if (-not (Test-Path -LiteralPath $launcherPath)) {
    throw "SmartFlow AI.exe was not found in the project folder."
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcherPath
$shortcut.Arguments = ""
$shortcut.WorkingDirectory = $projectRoot
$shortcut.IconLocation = $iconPath + ",0"
$shortcut.Description = "SmartFlow AI - AI Clip Creator"
$shortcut.WindowStyle = 1
$shortcut.Save()

Write-Output $shortcutPath
