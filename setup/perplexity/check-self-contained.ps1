param([Parameter(Mandatory = $true)][string]$SkillsDir, [Parameter(Mandatory = $true)][string]$WorkspaceRoot)
$ErrorActionPreference = 'Stop'
$env:PPLX_SKILLS_DIR = $SkillsDir
. (Join-Path $SkillsDir 'productivity\chief-of-staff\scripts\runtime.ps1') -WorkspaceRoot $WorkspaceRoot
if ($PSVersionTable.PSVersion.Major -ne 5) { throw 'Run this check in Windows PowerShell 5.1.' }
$ParsedBlocks = 0
foreach ($SkillName in @('chief-of-staff', 'ingest')) {
    $SkillFile = Join-Path $SkillsDir "productivity\$SkillName\SKILL.md"
    $SkillText = Get-Content -LiteralPath $SkillFile -Raw
    foreach ($Block in [regex]::Matches($SkillText, '(?s)```powershell\r?\n(.*?)```')) {
        $Tokens = $null
        $ParseErrors = $null
        [System.Management.Automation.Language.Parser]::ParseInput($Block.Groups[1].Value, [ref]$Tokens, [ref]$ParseErrors) | Out-Null
        if ($ParseErrors.Count) { throw ($ParseErrors | Out-String) }
        $ParsedBlocks++
    }
}
# Help parsing does not authenticate or make requests.
foreach ($Helper in @('actions.py', 'ingest.py', 'brief.py', 'second_brain.py')) {
    & $Python (Join-Path $CosRoot "scripts\$Helper") --help | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "$Helper --help failed" }
}
$PythonInfo = @'
import sys, json, google.auth, googleapiclient.discovery; from zoneinfo import ZoneInfo; ZoneInfo("America/Los_Angeles")
print(json.dumps({'executable': sys.executable, 'paths': sys.path, 'isolated': sys.flags.isolated}))
'@ | & $Python -
if ($LASTEXITCODE -ne 0) { throw 'Python dependency check failed' }
$Info = $PythonInfo | ConvertFrom-Json
$Notes = & $Python (Join-Path $CosRoot 'scripts\second_brain.py') search 'NeoAgent V2' --max 1
if ($LASTEXITCODE -ne 0 -or -not ($Notes | ConvertFrom-Json).notes.Count) { throw 'Workspace notes check failed' }
$Brief = & $Python (Join-Path $CosRoot 'scripts\brief.py') --max-chars 14000
if ($LASTEXITCODE -ne 0) { throw 'Cached briefing check failed' }
$null = $Brief | ConvertFrom-Json
[PSCustomObject]@{Shell=$PSVersionTable.PSVersion.ToString(); ParsedBlocks=$ParsedBlocks; Helpers=4; Python=$Info.executable; PythonSource=$CosPythonSource; StateDirectory=$env:COS_STATE_DIR; Notes=$true; CachedBrief=$true} | ConvertTo-Json
