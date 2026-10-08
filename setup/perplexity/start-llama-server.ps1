$ErrorActionPreference = "Stop"

$llamaRoot = "C:\llama.cpp-n1x-b9775"
$server = Join-Path $llamaRoot "llama-server.exe"
$model = Join-Path $llamaRoot "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"
$projector = Join-Path $llamaRoot "mmproj-BF16.gguf"

$existing = Get-CimInstance Win32_Process -Filter "Name = 'llama-server.exe'" |
    Where-Object { $_.ExecutablePath -eq $server }
if ($existing) {
    exit 0
}

$arguments = @(
    "-m", $model,
    "--mmproj", $projector,
    "--alias", "qwen3.6-35b-a3b",
    "--host", "127.0.0.1",
    "--port", "8080",
    "--ctx-size", "131072",
    "--gpu-layers", "all",
    "--fit", "off",
    "--spec-type", "draft-mtp",
    "--spec-draft-n-max", "3",
    "--top-k", "1",
    "--reasoning-budget", "756",
    "-np", "1",
    "--jinja"
)

Start-Process `
    -FilePath $server `
    -ArgumentList $arguments `
    -WorkingDirectory $llamaRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $llamaRoot "startup.stdout.log") `
    -RedirectStandardError (Join-Path $llamaRoot "startup.stderr.log")
