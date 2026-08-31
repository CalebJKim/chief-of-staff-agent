param(
    [string]$InstallRoot,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0
. (Join-Path $PSScriptRoot "Common.ps1")
$paths = Get-DemoPaths $InstallRoot

if (-not (Test-Path -LiteralPath $paths.PythonExe -PathType Leaf)) { throw "The demo is not installed." }
$state = Join-Path $paths.HermesHome "chief-of-staff-workspace-state.json"
if (-not (Test-Path -LiteralPath $state -PathType Leaf)) { throw "Reference workspace metadata is missing. Run Repair from USB." }

Write-DemoHeader "Resetting Reference Workspace"
Write-Host "This restores the seeded Gmail, Calendar, Drive, Docs, Sheets, and Slides demo state."
if (-not (Read-YesNo "Continue?" $false)) { Write-Host "Cancelled."; exit 0 }

$previousHome = $env:HERMES_HOME
try {
    $env:HERMES_HOME = $paths.HermesHome
    & $paths.PythonExe (Join-Path $paths.App "demo\seed_workspace.py") --reset --confirm
    if ($LASTEXITCODE -ne 0) { throw "Workspace reset failed." }
    Write-DemoSuccess "Reference workspace reset"
} finally {
    $env:HERMES_HOME = $previousHome
}

if (-not $NoStart) {
    & (Join-Path $PSScriptRoot "Start-Demo.ps1") -InstallRoot $paths.Root
}
