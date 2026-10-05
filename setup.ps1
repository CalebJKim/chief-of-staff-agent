# Connect Google Workspace for an installed Chief of Staff demo.
[CmdletBinding()]
param(
    [ValidateSet('hermes', 'perplexity')][string]$Harness,
    [string]$WorkspaceRoot,
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_.-]*$')][string]$Profile = 'chief-of-staff',
    [string]$HermesRoot,
    [string]$SkillsDir,
    [string]$ClientSecret,
    [switch]$Check
)
$ErrorActionPreference = 'Stop'

if (-not $Harness) {
    if ($Check) { throw 'Pass -Harness hermes or -Harness perplexity with -Check.' }
    $Harness = (Read-Host 'Which demo are you connecting? Enter hermes or perplexity').Trim().ToLowerInvariant()
    if ($Harness -notin @('hermes', 'perplexity')) { throw 'Choose hermes or perplexity.' }
}

if ($Harness -eq 'perplexity') {
    if (-not $WorkspaceRoot) { $WorkspaceRoot = Join-Path $PSScriptRoot 'CoS_Workspace' }
    $CosWorkspace = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($WorkspaceRoot)
    if (-not (Test-Path -LiteralPath (Join-Path $CosWorkspace 'CoS_SecondBrain') -PathType Container)) {
        throw 'Select the demo workspace containing CoS_SecondBrain with -WorkspaceRoot.'
    }
    $CosState = Join-Path $CosWorkspace '.chief-of-staff-state'
    if (-not $SkillsDir) { $SkillsDir = $env:PPLX_SKILLS_DIR }
    if (-not $SkillsDir) {
        $CosAccountsRoot = Join-Path $env:USERPROFILE '.pplx\users'
        $CosAccounts = @()
        if (Test-Path -LiteralPath $CosAccountsRoot -PathType Container) {
            $CosAccounts = @(Get-ChildItem -LiteralPath $CosAccountsRoot -Directory | Where-Object {
                Test-Path -LiteralPath (Join-Path $_.FullName 'skills\productivity\chief-of-staff\SKILL.md') -PathType Leaf
            })
        }
        if ($CosAccounts.Count -ne 1) {
            throw 'Could not select one Perplexity demo installation. Install the demo skills, or pass -SkillsDir with the account skills folder.'
        }
        $SkillsDir = Join-Path $CosAccounts[0].FullName 'skills'
    }
    $SkillsDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($SkillsDir)
    if (-not (Test-Path -LiteralPath (Join-Path $SkillsDir 'productivity\chief-of-staff\SKILL.md') -PathType Leaf)) {
        throw "Chief of Staff skill is missing from $SkillsDir. Install the demo skills first."
    }
    $CosManagedPython = Join-Path (Split-Path -Parent $SkillsDir) 'template\venv\Scripts\python.exe'
} else {
    if ($WorkspaceRoot -or $SkillsDir) { throw '-WorkspaceRoot and -SkillsDir apply only to Perplexity.' }
    if (-not $HermesRoot) {
        $CosRoots = @()
        if ($env:LOCALAPPDATA) { $CosRoots += Join-Path $env:LOCALAPPDATA 'hermes' }
        $CosRoots += Join-Path $env:USERPROFILE '.hermes'
        $HermesRoot = $CosRoots | Where-Object {
            Test-Path -LiteralPath (Join-Path $_ "profiles\$Profile") -PathType Container
        } | Select-Object -First 1
        if (-not $HermesRoot) { throw 'Hermes demo profile not found. Install it first, or pass -HermesRoot and -Profile.' }
    }
    $HermesRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($HermesRoot)
    $CosState = Join-Path $HermesRoot "profiles\$Profile"
    if (-not (Test-Path -LiteralPath $CosState -PathType Container)) {
        throw "Hermes profile is missing: $CosState. Install the demo profile first."
    }
    $CosManagedPython = Join-Path $CosState 'hermes-agent\venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $CosManagedPython -PathType Leaf)) {
        $CosManagedPython = Join-Path $HermesRoot 'hermes-agent\venv\Scripts\python.exe'
    }
}

if (Test-Path -LiteralPath $CosManagedPython -PathType Leaf) {
    $CosPython = $CosManagedPython
    $CosPythonSource = $Harness
} else {
    $CosSystemPython = @(Get-Command python.exe, python3.exe -CommandType Application -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notmatch '[\\/](WindowsApps|hermes|\.hermes|\.pplx|\.venv|venv)[\\/]' }) | Select-Object -First 1
    if (-not $CosSystemPython) { throw "No $Harness-managed or system Python found." }
    $CosPython = $CosSystemPython.Source
    $CosPythonSource = 'system'
}
$CosHelper = Join-Path $PSScriptRoot 'setup\google-workspace\setup.py'
if (-not (Test-Path -LiteralPath $CosHelper -PathType Leaf)) { throw "Missing setup helper: $CosHelper" }
if ($ClientSecret) { $ClientSecret = (Resolve-Path -LiteralPath $ClientSecret).ProviderPath }

if ($Check) {
    # Path inspection only: no Python execution, Google calls, writes, or sign-in.
    [ordered]@{
        harness = $Harness
        python = $CosPython
        python_source = $CosPythonSource
        credential_folder = $CosState
        client_secret_present = (Test-Path -LiteralPath (Join-Path $CosState 'google_client_secret.json') -PathType Leaf)
        token_present = (Test-Path -LiteralPath (Join-Path $CosState 'google_token.json') -PathType Leaf)
        mode = 'local-path-check'
    } | ConvertTo-Json
    return
}

$CosSavedEnvironment = @{}
foreach ($CosName in @('COS_STATE_DIR', 'HERMES_HOME', 'PYTHONUTF8', 'PYTHONDONTWRITEBYTECODE')) {
    $CosSavedEnvironment[$CosName] = [Environment]::GetEnvironmentVariable($CosName, 'Process')
}
try {
    $env:COS_STATE_DIR = $CosState
    if ($Harness -eq 'hermes') { $env:HERMES_HOME = $CosState }
    $env:PYTHONUTF8 = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $CosArguments = @('-B', '-X', 'utf8', $CosHelper, '--connect')
    if ($ClientSecret) { $CosArguments += @('--client-secret-file', $ClientSecret) }
    # An existing but broken interpreter fails here; do not switch and retry.
    & $CosPython @CosArguments
    if ($LASTEXITCODE -ne 0) { throw 'Google connection setup did not complete. See the message above.' }
    Write-Host "Google Workspace connection is ready for $Harness."
} finally {
    foreach ($CosName in $CosSavedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($CosName, $CosSavedEnvironment[$CosName], 'Process')
    }
}
