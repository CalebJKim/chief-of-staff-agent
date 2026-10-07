param([Parameter(Mandatory = $true)][string]$SkillsDir, [Parameter(Mandatory = $true)][string]$WorkspaceRoot)
$ErrorActionPreference = 'Stop'
$env:PPLX_SKILLS_DIR = $SkillsDir
. (Join-Path $SkillsDir 'productivity\chief-of-staff\scripts\runtime.ps1') -WorkspaceRoot $WorkspaceRoot
if ($PSVersionTable.PSVersion.Major -ne 5) { throw 'Run this check in Windows PowerShell 5.1.' }
$ParsedBlocks = 0
$Documents = @((Join-Path $CosRoot 'SKILL.md')) + @(Get-ChildItem -LiteralPath (Join-Path $CosRoot 'references') -Filter '*.md' -File | Select-Object -ExpandProperty FullName)
foreach ($Document in $Documents) {
    $SkillText = Get-Content -LiteralPath $Document -Raw -Encoding UTF8
    foreach ($Block in [regex]::Matches($SkillText, '(?s)```powershell\r?\n(.*?)```')) {
        $Tokens = $null
        $ParseErrors = $null
        [System.Management.Automation.Language.Parser]::ParseInput($Block.Groups[1].Value, [ref]$Tokens, [ref]$ParseErrors) | Out-Null
        if ($ParseErrors.Count) { throw ($ParseErrors | Out-String) }
        $ParsedBlocks++
    }
}
foreach ($Command in @('gmail', 'drive', 'docs', 'sheets', 'slides', 'calendar', 'second-brain', 'ingest', 'brief', 'daily-brief', 'verify')) {
    & $CosExecutable $Command --help | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "$Command --help failed" }
}
if (@(Get-ChildItem -LiteralPath (Join-Path $CosRoot 'scripts') -Recurse -File | Where-Object Extension -in @('.py', '.pyc')).Count) {
    throw 'Legacy Python code remains installed.'
}
[PSCustomObject]@{Shell=$PSVersionTable.PSVersion.ToString(); ParsedBlocks=$ParsedBlocks; Backend='Rust'; Executable=$CosExecutable; StateDirectory=$env:COS_STATE_DIR} | ConvertTo-Json
