param([string]$InstallRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0
. (Join-Path $PSScriptRoot "Common.ps1")
$paths = Get-DemoPaths $InstallRoot
$bundleRoot = Get-DemoBundleRoot

$safeInstallRoot = Assert-SafeDemoPath -Path $paths.Root -ExpectedLeaf "ChiefOfStaffDemo"
$safeBundleRoot = Assert-SafeDemoPath -Path $bundleRoot -ExpectedLeaf "ChiefOfStaffDemo"

Write-DemoHeader "Finalize and Remove Chief of Staff Demo"
Write-Host "This will:"
Write-Host " - stop the local model server"
Write-Host " - optionally remove the seeded Google workspace"
Write-Host " - revoke the copied Google OAuth token"
Write-Host " - remove the isolated installation from this PC"
Write-Host " - remove $safeBundleRoot from the USB"
Write-Host ""
$confirmation = Read-Host "Type FINALIZE to continue"
if ($confirmation -cne "FINALIZE") { Write-Host "Cancelled."; exit 0 }

$null = Stop-DemoServer $paths.LlamaServer

if (Test-Path -LiteralPath $paths.PythonExe -PathType Leaf) {
    $previousHome = $env:HERMES_HOME
    try {
        $env:HERMES_HOME = $paths.HermesHome
        $statePath = Join-Path $paths.HermesHome "chief-of-staff-workspace-state.json"
        if ((Test-Path -LiteralPath $statePath -PathType Leaf) -and (Read-YesNo "Remove the seeded Gmail, Calendar, and Drive demo workspace?" $true)) {
            Write-DemoStep "Removing seeded Google Workspace data"
            & $paths.PythonExe (Join-Path $paths.App "demo\seed_workspace.py") --cleanup --confirm
            if ($LASTEXITCODE -ne 0) { throw "Google workspace cleanup failed. Nothing local or on the USB has been deleted." }
        }
        if (Test-Path -LiteralPath (Join-Path $paths.HermesHome "google_token.json") -PathType Leaf) {
            Write-DemoStep "Revoking copied Google OAuth token"
            & $paths.PythonExe (Join-Path $paths.App "setup\google-workspace\setup.py") --revoke
            if ($LASTEXITCODE -ne 0) { throw "OAuth revocation failed. Nothing local or on the USB has been deleted." }
        }
    } finally {
        $env:HERMES_HOME = $previousHome
    }
}

$desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
foreach ($name in @("Start Chief of Staff Demo.lnk", "Reset and Start Fresh Demo.lnk", "Chief of Staff Demo Diagnostics.lnk")) {
    $shortcut = Join-Path $desktop $name
    Remove-Item -LiteralPath $shortcut -Force -ErrorAction SilentlyContinue
}

if (Test-Path -LiteralPath $safeInstallRoot) {
    Write-DemoStep "Removing isolated installation from this PC"
    Remove-Item -LiteralPath $safeInstallRoot -Recurse -Force
}

Write-DemoStep "Removing the single demo folder from the USB"
Remove-Item -LiteralPath $safeBundleRoot -Recurse -Force
Write-Host ""
Write-Host "Demo finalized. The token was revoked before local and USB deletion." -ForegroundColor Green
Write-Host "Ordinary flash deletion is not forensic secure erasure, but a recovered revoked token cannot authorize Google access."
