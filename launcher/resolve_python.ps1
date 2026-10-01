$ErrorActionPreference = "SilentlyContinue"

$projectRoot = Split-Path -Parent $PSScriptRoot
$localAppDataRoot = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
$configuredPython = [Environment]::GetEnvironmentVariable("SMARTFLOW_PYTHONW")

$candidatePaths = @(
    $configuredPython,
    (Join-Path $projectRoot ".venv\Scripts\pythonw.exe"),
    (Join-Path $localAppDataRoot "Programs\Python\Python311\pythonw.exe"),
    (Join-Path $localAppDataRoot "Programs\Python\Python312\pythonw.exe"),
    (Join-Path $localAppDataRoot "Programs\Python\Python313\pythonw.exe")
)

foreach ($candidatePath in $candidatePaths) {
    if ($candidatePath -and (Test-Path -LiteralPath $candidatePath -PathType Leaf)) {
        [Console]::Out.WriteLine([IO.Path]::GetFullPath($candidatePath))
        exit 0
    }
}

$pathCommand = Get-Command "pythonw.exe" -CommandType Application | Select-Object -First 1
if ($pathCommand -and (Test-Path -LiteralPath $pathCommand.Source -PathType Leaf)) {
    [Console]::Out.WriteLine([IO.Path]::GetFullPath($pathCommand.Source))
    exit 0
}

[Console]::Error.WriteLine("Pythonw not found")
exit 1
