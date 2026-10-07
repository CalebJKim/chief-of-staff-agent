# Initialize and run the bundled, read-only Second Brain helper in one call.
# Parse only the launcher option; pass Python flags such as --max unchanged.
$ErrorActionPreference = 'Stop'
$CosBrainArgs = @($args)
if ($CosBrainArgs.Count -lt 3 -or $CosBrainArgs[0] -ne '-WorkspaceRoot') {
    throw 'Use run-second-brain.ps1 -WorkspaceRoot WORKSPACE_ROOT search|read [arguments].'
}
$CosBrainWorkspace = [string]$CosBrainArgs[1]
$CosBrainCommand = @($CosBrainArgs[2..($CosBrainArgs.Count - 1)])

. (Join-Path $PSScriptRoot 'runtime.ps1') -WorkspaceRoot $CosBrainWorkspace -NativeActions
& $Action second-brain @CosBrainCommand
if ($LASTEXITCODE -ne 0) {
    throw 'second_brain.py failed; inspect the error above.'
}
