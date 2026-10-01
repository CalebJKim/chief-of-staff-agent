# Dot-source at the start of each Perplexity shell call.
param([string]$WorkspaceRoot)
$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $OutputEncoding
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
# Explicit task workspace; keep the environment override for existing callers.
if (-not $WorkspaceRoot) { $WorkspaceRoot = $env:COS_WORKSPACE_ROOT }
# PowerShell 5.1 Resolve-Path may return no ProviderPath for extended paths.
# Convert the app's drive/UNC prefix before resolving the selected workspace.
if ($WorkspaceRoot -match '^\\\\\?\\[A-Za-z]:\\') {
    $WorkspaceRoot = $WorkspaceRoot.Substring(4)
} elseif ($WorkspaceRoot -and $WorkspaceRoot.StartsWith('\\?\UNC\', [System.StringComparison]::OrdinalIgnoreCase)) {
    $WorkspaceRoot = '\\' + $WorkspaceRoot.Substring(8)
}
if (-not $WorkspaceRoot -or $WorkspaceRoot -notmatch '^(?:[A-Za-z]:[\\/]|\\\\)') {
    throw 'Pass -WorkspaceRoot with the absolute path of the folder selected for this Perplexity task.'
}
if (-not (Test-Path -LiteralPath $WorkspaceRoot -PathType Container)) {
    throw "Workspace folder does not exist or is inaccessible: $WorkspaceRoot"
}
$CosWorkspace = (Resolve-Path -LiteralPath $WorkspaceRoot).ProviderPath
$NotesPath = Join-Path $CosWorkspace 'CoS_SecondBrain'
if (-not (Test-Path -LiteralPath $NotesPath -PathType Container)) {
    throw "Second Brain folder is missing or inaccessible: $NotesPath. Select its parent as the workspace."
}
$CosRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Runtime = Get-Content -LiteralPath (Join-Path $CosRoot 'runtime-local.json') -Raw | ConvertFrom-Json
function Resolve-CosRuntimePath([string]$RelativePath) {
    if (-not $RelativePath -or [System.IO.Path]::IsPathRooted($RelativePath)) {
        throw 'Chief of Staff runtime paths must be relative to the installed skill.'
    }
    $ResolvedPath = [System.IO.Path]::GetFullPath((Join-Path $CosRoot $RelativePath))
    if (-not $ResolvedPath.StartsWith($CosRoot.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Chief of Staff runtime paths must stay inside the installed skill.'
    }
    return $ResolvedPath
}
$CosSeedHome = Resolve-CosRuntimePath ([string]$Runtime.seed_state_root)
# Python is supplied by Perplexity. Fall back only when it is absent.
if (-not $env:PPLX_SKILLS_DIR) { throw 'PPLX_SKILLS_DIR is missing. Run from a Perplexity local thread.' }
$CosProfileRoot = Split-Path -Parent ([IO.Path]::GetFullPath($env:PPLX_SKILLS_DIR))
$ManagedPython = Join-Path $CosProfileRoot 'template\venv\Scripts\python.exe'
if (Test-Path -LiteralPath $ManagedPython -PathType Leaf) {
    $Python = $ManagedPython
    $CosPythonSource = 'perplexity'
} else {
    $SystemPython = @(Get-Command python.exe, python3.exe -CommandType Application -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notmatch '[\\/]WindowsApps[\\/]' }) | Select-Object -First 1
    if (-not $SystemPython) { throw 'No Perplexity or system Python was found.' }
    $Python = $SystemPython.Source
    $CosPythonSource = 'system'
}
# Check dependencies before creating state or starting ingestion. Never retry a job.
$PythonCheck = @'
import sys
assert sys.version_info >= (3, 10), "Python 3.10 or newer is required"
import google.auth.transport.requests
import google.oauth2.credentials
import googleapiclient.discovery
from zoneinfo import ZoneInfo
ZoneInfo("America/Los_Angeles")
'@
try {
    $PythonCheck | & $Python -B -
    if ($LASTEXITCODE -ne 0) { throw 'Python or dependency check failed.' }
} catch {
    throw "Cannot use $CosPythonSource Python at $Python. $($_.Exception.Message) The brief was not started."
}
$Action = Join-Path $CosRoot 'scripts\actions.py'
foreach ($RequiredPath in @($CosSeedHome, $Python, $Action)) {
    if (-not (Test-Path -LiteralPath $RequiredPath)) {
        throw "Chief of Staff installation is incomplete: $RequiredPath"
    }
}
# Perplexity mounts installed skills read-only. Refreshing OAuth tokens and
# writing snapshots must use the explicitly selected writable workspace.
$CosHome = Join-Path $CosWorkspace '.chief-of-staff-state'
New-Item -ItemType Directory -Path $CosHome -Force | Out-Null
foreach ($StateName in @('google_token.json', 'google_client_secret.json', 'chief-of-staff-workspace-state.json')) {
    $SeedFile = Join-Path $CosSeedHome $StateName
    $LiveFile = Join-Path $CosHome $StateName
    if (-not (Test-Path -LiteralPath $LiveFile) -and (Test-Path -LiteralPath $SeedFile)) {
        [IO.File]::WriteAllBytes($LiveFile, [IO.File]::ReadAllBytes($SeedFile))
    }
}
# The selected workspace determines the vault. Ignore old installed connections.
$BrainJson = @{ vault_path = $NotesPath } | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $CosHome 'second-brain.json'), $BrainJson, [Text.UTF8Encoding]::new($false))
$SeedSnapshot = Join-Path $CosSeedHome 'chief-of-staff\snapshot.json'
$LiveSnapshot = Join-Path $CosHome 'chief-of-staff\snapshot.json'
if (-not (Test-Path -LiteralPath $LiveSnapshot) -and (Test-Path -LiteralPath $SeedSnapshot)) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $LiveSnapshot) -Force | Out-Null
    [IO.File]::WriteAllBytes($LiveSnapshot, [IO.File]::ReadAllBytes($SeedSnapshot))
}
$env:COS_STATE_DIR = $CosHome
