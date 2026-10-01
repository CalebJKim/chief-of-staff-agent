# Run from any PowerShell directory. No environment setup is required.
[CmdletBinding()]
param(
    [switch]$Check,
    [string]$WeekOf,
    [string]$SkillsDir = $env:PPLX_SKILLS_DIR
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'

if (-not $SkillsDir) {
    $AccountsRoot = Join-Path $env:USERPROFILE '.pplx\users'
    $Accounts = @()
    if (Test-Path -LiteralPath $AccountsRoot -PathType Container) {
        $Accounts = @(Get-ChildItem -LiteralPath $AccountsRoot -Directory | Where-Object {
            Test-Path -LiteralPath (Join-Path $_.FullName 'skills\productivity\chief-of-staff\SKILL.md') -PathType Leaf
        })
    }
    if ($Accounts.Count -gt 1) { throw 'Multiple Perplexity installations found. Pass -SkillsDir with the demo account skills folder.' }
    if ($Accounts.Count -eq 1) { $SkillsDir = Join-Path $Accounts[0].FullName 'skills' }
}
$ManagedPython = $null
if ($SkillsDir) {
    $AccountRoot = Split-Path -Parent ([IO.Path]::GetFullPath($SkillsDir))
    $ManagedPython = Join-Path $AccountRoot 'template\venv\Scripts\python.exe'
}
if ($ManagedPython -and (Test-Path -LiteralPath $ManagedPython -PathType Leaf)) {
    $Python = $ManagedPython
} else {
    $SystemPython = @(Get-Command python.exe, python3.exe -CommandType Application -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notmatch '[\\/](WindowsApps|hermes|\.hermes|\.venv|venv)[\\/]' }) | Select-Object -First 1
    if (-not $SystemPython) { throw 'No Perplexity or system Python was found.' }
    $Python = $SystemPython.Source
}
# Existing but broken interpreters fail here; never retry a reset with another Python.
$ResetArgs = @('-B', (Join-Path $PSScriptRoot 'reset_workspace.py'))
if ($Check) { $ResetArgs += '--check' }
if ($WeekOf) { $ResetArgs += @('--week-of', $WeekOf) }
& $Python @ResetArgs
if ($LASTEXITCODE -ne 0) { throw "Demo reset command failed (exit $LASTEXITCODE). See the error above." }
