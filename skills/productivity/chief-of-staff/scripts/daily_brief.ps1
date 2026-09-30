param([switch]$Fixture)
$ErrorActionPreference = 'Stop'
# Setup and execution always run in the same shell call.
. (Join-Path $PSScriptRoot 'runtime.ps1')
if ($env:COS_STATE_DIR -ne $CosHome -or -not (Test-Path -LiteralPath $CosHome -PathType Container)) {
    throw 'Chief of Staff workspace initialization failed. The brief was not started.'
}
$BriefArguments = @('-X', 'utf8', '-B', (Join-Path $CosRoot 'scripts\daily_brief.py'))
if ($Fixture) {
    $BriefArguments += @('--fixture', (Join-Path $CosRoot 'tests\fixtures\workspace.json'))
}
& $Python @BriefArguments
if ($LASTEXITCODE -ne 0) { throw 'Chief of Staff command failed; inspect the error above.' }
