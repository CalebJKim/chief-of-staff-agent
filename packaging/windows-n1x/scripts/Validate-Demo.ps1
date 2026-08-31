param(
    [string]$InstallRoot,
    [switch]$FullHashes,
    [switch]$StartServer
)

$ErrorActionPreference = "Continue"
Set-StrictMode -Version 2.0
. (Join-Path $PSScriptRoot "Common.ps1")
$paths = Get-DemoPaths $InstallRoot
$failures = New-Object Collections.Generic.List[string]

function Run-Check {
    param([string]$Name, [scriptblock]$Check)
    try {
        & $Check
        Write-DemoSuccess $Name
    } catch {
        $failures.Add("$Name`: $($_.Exception.Message)")
        Write-Host "[FAILED] $Name - $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-DemoHeader "Chief of Staff Demo Diagnostics"
Run-Check "N1X hardware and memory configuration" { $null = Assert-N1XPreflight }
Run-Check "Required installation files" {
    foreach ($file in @($paths.LlamaServer, $paths.Model, $paths.Projector, $paths.HermesExe, $paths.PythonExe, (Join-Path $paths.App "install.py"))) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing $file" }
    }
}
if ($FullHashes) {
    Run-Check "Qwen model SHA-256" {
        if ((Get-FileHash -LiteralPath $paths.Model -Algorithm SHA256).Hash.ToLowerInvariant() -ne $script:DemoModelSha256) { throw "Hash mismatch" }
    }
    Run-Check "Projector SHA-256" {
        if ((Get-FileHash -LiteralPath $paths.Projector -Algorithm SHA256).Hash.ToLowerInvariant() -ne $script:DemoProjectorSha256) { throw "Hash mismatch" }
    }
}
if ($StartServer -and -not (Test-DemoServerHealth)) {
    Run-Check "Start local model server" { & (Join-Path $PSScriptRoot "Start-Demo.ps1") -InstallRoot $paths.Root -NoHermes }
}
Run-Check "Local model-server health" { if (-not (Test-DemoServerHealth)) { throw "Server is not running; use Start Chief of Staff Demo." } }
Run-Check "Hermes version" {
    $previousHome = $env:HERMES_HOME
    try { $env:HERMES_HOME = $paths.HermesHome; & $paths.HermesExe --version | Out-Host; if ($LASTEXITCODE -ne 0) { throw "Hermes failed" } } finally { $env:HERMES_HOME = $previousHome }
}
Run-Check "Google live authorization" {
    $previousHome = $env:HERMES_HOME
    try {
        $env:HERMES_HOME = $paths.HermesHome
        & $paths.PythonExe (Join-Path $paths.App "setup\google-workspace\setup.py") --check-live | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Google live check failed" }
    } finally { $env:HERMES_HOME = $previousHome }
}
Run-Check "Chief of Staff verification" {
    $previousHome = $env:HERMES_HOME
    try {
        $env:HERMES_HOME = $paths.HermesHome
        & $paths.PythonExe (Join-Path $paths.App "skills\productivity\ingest\scripts\verify.py") | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Verification script failed" }
    } finally { $env:HERMES_HOME = $previousHome }
}
Run-Check "Unit tests" {
    Push-Location $paths.App
    try {
        & $paths.PythonExe -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw "Top-level tests failed" }
        & $paths.PythonExe -m unittest discover -s skills\productivity\ingest\tests -v
        if ($LASTEXITCODE -ne 0) { throw "Ingest tests failed" }
        & $paths.PythonExe -m unittest discover -s skills\productivity\chief-of-staff\tests -v
        if ($LASTEXITCODE -ne 0) { throw "Chief of Staff tests failed" }
    } finally { Pop-Location }
}

Write-Host ""
if ($failures.Count) {
    Write-Host "$($failures.Count) diagnostic check(s) failed:" -ForegroundColor Red
    foreach ($failure in $failures) { Write-Host " - $failure" }
    exit 1
}
Write-Host "All requested diagnostics passed." -ForegroundColor Green
