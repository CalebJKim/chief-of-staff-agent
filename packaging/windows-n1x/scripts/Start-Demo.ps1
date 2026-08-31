param(
    [string]$InstallRoot,
    [switch]$NoHermes
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0
. (Join-Path $PSScriptRoot "Common.ps1")
$paths = Get-DemoPaths $InstallRoot

Write-DemoHeader "Starting Chief of Staff Demo"
foreach ($file in @($paths.LlamaServer, $paths.Model, $paths.Projector, $paths.HermesExe)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "The demo is not fully installed. Missing: $file. Reattach the USB and run Repair."
    }
}

$running = Get-DemoServerProcess $paths.LlamaServer
if (-not $running) {
    if (Test-DemoServerHealth) {
        throw "Port $script:DemoPort is already occupied by another healthy llama server. Stop it or run Demo Diagnostics."
    }
    New-Item -ItemType Directory -Force -Path $paths.Logs | Out-Null
    $arguments = @(
        "-m", ('"' + $paths.Model + '"'),
        "--mmproj", ('"' + $paths.Projector + '"'),
        "--alias", $script:DemoModelAlias,
        "--host", "127.0.0.1",
        "--port", [string]$script:DemoPort,
        "--ctx-size", [string]$script:DemoContextLength,
        "--spec-type", "draft-mtp",
        "--spec-draft-n-max", "3",
        "-np", "1",
        "--jinja"
    )
    Write-DemoStep "Loading Qwen3.6 into the N1X GPU carveout"
    $process = Start-Process -FilePath $paths.LlamaServer -ArgumentList $arguments -WorkingDirectory $paths.LlamaRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $paths.Logs "llama.stdout.log") -RedirectStandardError (Join-Path $paths.Logs "llama.stderr.log")
    [IO.File]::WriteAllText($paths.Pid, [string]$process.Id, (New-Object Text.UTF8Encoding($false)))
}

$deadline = [DateTime]::UtcNow.AddMinutes(5)
$lastNotice = [DateTime]::MinValue
while (-not (Test-DemoServerHealth)) {
    if ([DateTime]::UtcNow -ge $deadline) {
        $tail = Get-Content -LiteralPath (Join-Path $paths.Logs "llama.stderr.log") -Tail 20 -ErrorAction SilentlyContinue
        throw "The model server did not become ready within five minutes.`n$($tail -join [Environment]::NewLine)"
    }
    if (([DateTime]::UtcNow - $lastNotice).TotalSeconds -ge 10) {
        Write-Host "   Model is still loading..."
        $lastNotice = [DateTime]::UtcNow
    }
    Start-Sleep -Seconds 2
}
Write-DemoSuccess "Local model server is ready at http://127.0.0.1:$script:DemoPort"

if (-not $NoHermes) {
    $previousHome = $env:HERMES_HOME
    try {
        $env:HERMES_HOME = $paths.HermesHome
        Set-Location -LiteralPath $paths.App
        Write-DemoStep "Opening Hermes"
        & $paths.HermesExe --tui
    } finally {
        $env:HERMES_HOME = $previousHome
    }
}
