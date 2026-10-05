# Invoke one bundled actions.py command, or a batch with initialization once.
# Setup options must precede the service command. No advanced parameter binding:
# actions.py flags and piped JSON must reach the helper without reinterpretation.
$ErrorActionPreference = 'Stop'
$CosActionArgs = @($args)
$CosActionInput = @($input)
$CosActionWorkspace = $null
$CosActionBatch = $null
$CosActionCommand = @()
for ($i = 0; $i -lt $CosActionArgs.Count; $i++) {
    if ($CosActionArgs[$i] -eq '-WorkspaceRoot') {
        if (++$i -ge $CosActionArgs.Count) { throw '-WorkspaceRoot needs an absolute workspace path.' }
        $CosActionWorkspace = [string]$CosActionArgs[$i]
    } elseif ($CosActionArgs[$i] -eq '-Batch') {
        if (++$i -ge $CosActionArgs.Count -or $CosActionArgs[$i] -isnot [scriptblock]) {
            throw '-Batch needs a script block containing action commands.'
        }
        $CosActionBatch = $CosActionArgs[$i]
    } else {
        $CosActionCommand = @($CosActionArgs[$i..($CosActionArgs.Count - 1)])
        break
    }
}
if ($CosActionBatch -and ($CosActionCommand.Count -or $CosActionInput.Count)) {
    throw 'Use either a single command with optional piped input, or -Batch { action ... }. Pipe each batch input to its own action.'
}
if (-not $CosActionBatch -and -not $CosActionCommand.Count) {
    throw 'Supply SERVICE COMMAND [arguments], or -Batch { action SERVICE COMMAND ... }.'
}

. (Join-Path $PSScriptRoot 'runtime.ps1') -WorkspaceRoot $CosActionWorkspace

function ConvertTo-CosNativeArgument([string]$Value) {
    # Windows native command-line escaping, including embedded quotes, empty
    # arguments and backslashes before a quote or the end of an argument.
    $escaped = [regex]::Replace($Value, '(\\*)"', {
        param($match)
        ('\' * ($match.Groups[1].Value.Length * 2 + 1)) + '"'
    })
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    '"' + $escaped + '"'
}

$script:CosActionInvocationCount = 0
function action {
    $command = @($args)
    $piped = @($input)
    if (-not $command.Count) { throw 'action needs SERVICE COMMAND [arguments].' }
    $script:CosActionInvocationCount++
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $Python
    $nativeArgs = @('-X', 'utf8', '-B', $Action) + $command
    $start.Arguments = ($nativeArgs | ForEach-Object { ConvertTo-CosNativeArgument ([string]$_) }) -join ' '
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.WorkingDirectory = (Get-Location).ProviderPath
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $start.StandardOutputEncoding = $utf8
    $start.StandardErrorEncoding = $utf8
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw 'Could not start actions.py.' }
        # Drain both output streams while sending input to avoid pipe deadlocks.
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $inputFailure = $null
        try {
            if ($piped.Count) {
                $text = ($piped | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
                $bytes = $utf8.GetBytes($text + [Environment]::NewLine)
                $process.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
            }
        } catch {
            # A command-line error can close stdin early. Still surface the
            # helper's real error instead of replacing it with a broken pipe.
            $inputFailure = $_
        } finally {
            $process.StandardInput.Close()
        }
        $process.WaitForExit()
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        if ($stdout.Length) { Write-Output -NoEnumerate $stdout.TrimEnd([char[]]"`r`n") }
        if ($stderr.Length) { [Console]::Error.Write($stderr) }
        if ($process.ExitCode -ne 0) {
            throw "actions.py failed (exit code $($process.ExitCode)). Inspect the error above before retrying."
        }
        if ($inputFailure) { throw $inputFailure }
    } finally {
        $process.Dispose()
    }
}

if ($CosActionBatch) {
    & $CosActionBatch
    if (-not $script:CosActionInvocationCount) { throw 'The batch did not run any action commands.' }
} elseif ($CosActionInput.Count) {
    $CosActionInput | action @CosActionCommand
} else {
    action @CosActionCommand
}
