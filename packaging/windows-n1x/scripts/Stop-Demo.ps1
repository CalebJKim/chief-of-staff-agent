param([string]$InstallRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0
. (Join-Path $PSScriptRoot "Common.ps1")
$paths = Get-DemoPaths $InstallRoot

$count = Stop-DemoServer $paths.LlamaServer
if ($count) {
    Write-DemoSuccess "Stopped $count Chief of Staff model-server process(es)"
} else {
    Write-Host "The Chief of Staff model server was not running."
}
Remove-Item -LiteralPath $paths.Pid -Force -ErrorAction SilentlyContinue
