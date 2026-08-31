param(
    [string]$DemoSource = $(Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$LlamaSource = "C:\llama.cpp-n1x-b9775",
    [string]$HermesHome = $(Join-Path $env:LOCALAPPDATA "hermes"),
    [string]$OutputRoot = $(Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "out\ChiefOfStaffDemo")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0
. (Join-Path $PSScriptRoot "scripts\Common.ps1")

function Copy-RequiredFile {
    param([string]$Source, [string]$Destination)
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Required source file not found: $Source" }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function New-ModelLinkOrCopy {
    param([string]$Source, [string]$Destination)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    try {
        New-Item -ItemType HardLink -Path $Destination -Target $Source -ErrorAction Stop | Out-Null
    } catch {
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
    }
}

$output = [IO.Path]::GetFullPath($OutputRoot).TrimEnd('\')
if ((Split-Path -Leaf $output) -ne "ChiefOfStaffDemo") { throw "OutputRoot must end in ChiefOfStaffDemo." }
if (Test-Path -LiteralPath $output) {
    Write-DemoStep "Removing previous generated staging folder"
    Remove-Item -LiteralPath $output -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $output | Out-Null

Write-DemoHeader "Building Chief of Staff N1X bundle"
Write-Host "Output: $output"

Write-DemoStep "Copying installer and operator files"
Copy-Item -Path (Join-Path $PSScriptRoot "root\*") -Destination $output -Recurse -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "scripts") -Destination (Join-Path $output "scripts") -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $output "_private") | Out-Null

Write-DemoStep "Exporting clean demo source"
$appDestination = Join-Path $output "payload\demo-source"
New-Item -ItemType Directory -Force -Path $appDestination | Out-Null
foreach ($name in @("SOUL.md", "PORTABILITY.md", "QUICKSTART.md", "README.md", "DEMO_SCRIPT.md", "config.example.yaml", "install.py", "requirements.txt")) {
    Copy-RequiredFile (Join-Path $DemoSource $name) (Join-Path $appDestination $name)
}
foreach ($name in @("demo", "setup", "skills", "tests")) {
    Copy-Item -LiteralPath (Join-Path $DemoSource $name) -Destination (Join-Path $appDestination $name) -Recurse -Force
}
Get-ChildItem -LiteralPath $appDestination -Directory -Recurse -Force | Where-Object Name -In @("__pycache__", ".pytest_cache") | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $appDestination -File -Recurse -Force | Where-Object Extension -In @(".pyc", ".pyo") | Remove-Item -Force

Write-DemoStep "Copying pinned llama.cpp ARM64 CUDA runtime"
$llamaDestination = Join-Path $output "payload\llama.cpp"
New-Item -ItemType Directory -Force -Path $llamaDestination | Out-Null
foreach ($file in @(Get-ChildItem -LiteralPath $LlamaSource -Filter "*.dll" -File)) {
    Copy-Item -LiteralPath $file.FullName -Destination $llamaDestination -Force
}
foreach ($name in @("llama-server.exe", "llama-cli.exe", "llama-gguf-hash.exe")) {
    Copy-RequiredFile (Join-Path $LlamaSource $name) (Join-Path $llamaDestination $name)
}
Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/ggml-org/llama.cpp/$script:DemoLlamaCommit/LICENSE" -OutFile (Join-Path $llamaDestination "LICENSE")

Write-DemoStep "Linking exact Qwen model payloads into local staging"
$modelDestination = Join-Path $output "payload\models"
New-ModelLinkOrCopy (Join-Path $LlamaSource $script:DemoModelName) (Join-Path $modelDestination $script:DemoModelName)
New-ModelLinkOrCopy (Join-Path $LlamaSource $script:DemoProjectorName) (Join-Path $modelDestination $script:DemoProjectorName)
$modelSourceText = @"
Model repository: https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF
Repository revision: 5bc3e238d916f48a861bac2f8a1990a0e9b7e98d
Model file: $script:DemoModelName
Model SHA-256: $script:DemoModelSha256
Projector file: $script:DemoProjectorName
Projector SHA-256: $script:DemoProjectorSha256
Base model license: Apache-2.0
"@
[IO.File]::WriteAllText((Join-Path $modelDestination "MODEL-SOURCE.txt"), $modelSourceText, (New-Object Text.UTF8Encoding($false)))
Invoke-WebRequest -UseBasicParsing -Uri "https://huggingface.co/Qwen/Qwen3.6-35B-A3B/raw/main/LICENSE" -OutFile (Join-Path $modelDestination "LICENSE")

Write-DemoStep "Copying signed Hermes bootstrap and pinned installer"
$hermesDestination = Join-Path $output "payload\hermes"
New-Item -ItemType Directory -Force -Path $hermesDestination | Out-Null
Copy-RequiredFile (Join-Path $HermesHome "hermes-setup.exe") (Join-Path $hermesDestination "hermes-setup.exe")
Copy-RequiredFile (Join-Path $HermesHome "hermes-agent\scripts\install.ps1") (Join-Path $hermesDestination "install.ps1")
Copy-RequiredFile (Join-Path $HermesHome "hermes-agent\LICENSE") (Join-Path $hermesDestination "LICENSE")
$hermesSourceText = @"
Hermes Agent repository: https://github.com/NousResearch/hermes-agent
Pinned commit: $script:DemoHermesCommit
Expected version family: v0.20.4
Install mode: native Windows ARM64, isolated HERMES_HOME, SkipSetup
"@
[IO.File]::WriteAllText((Join-Path $hermesDestination "SOURCE.txt"), $hermesSourceText, (New-Object Text.UTF8Encoding($false)))

Write-DemoStep "Building offline Python wheel cache"
$wheelhouse = Join-Path $output "payload\python-wheels"
New-Item -ItemType Directory -Force -Path $wheelhouse | Out-Null
& python -m pip download --disable-pip-version-check --only-binary=:all: --dest $wheelhouse -r (Join-Path $DemoSource "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Python wheel download failed." }

Write-DemoStep "Verifying the two large model artifacts"
$modelPath = Join-Path $modelDestination $script:DemoModelName
$projectorPath = Join-Path $modelDestination $script:DemoProjectorName
$actualModelHash = (Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash.ToLowerInvariant()
$actualProjectorHash = (Get-FileHash -LiteralPath $projectorPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualModelHash -ne $script:DemoModelSha256) { throw "Source model SHA-256 mismatch." }
if ($actualProjectorHash -ne $script:DemoProjectorSha256) { throw "Source projector SHA-256 mismatch." }

Write-DemoStep "Generating version and integrity manifests"
$sourceCommit = (& git -C $DemoSource rev-parse HEAD).Trim()
$artifacts = New-Object Collections.Generic.List[object]
$payloadRoot = Join-Path $output "payload"
foreach ($file in Get-ChildItem -LiteralPath $payloadRoot -File -Recurse | Sort-Object FullName) {
    $relative = $file.FullName.Substring($output.Length + 1).Replace('\', '/')
    if ($file.FullName -eq $modelPath) { $hash = $script:DemoModelSha256 }
    elseif ($file.FullName -eq $projectorPath) { $hash = $script:DemoProjectorSha256 }
    else { $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    $artifacts.Add([ordered]@{ path = $relative; bytes = $file.Length; sha256 = $hash })
}
$manifest = [ordered]@{
    format = 1
    created_utc = [DateTime]::UtcNow.ToString("o")
    target = "Windows 11 ARM64 / NVIDIA RTX Spark N1X / 64 GB / 16 GB GPU carveout"
    demo_source_commit = $sourceCommit
    hermes_commit = $script:DemoHermesCommit
    llama_cpp_commit = $script:DemoLlamaCommit
    model_repository_revision = "5bc3e238d916f48a861bac2f8a1990a0e9b7e98d"
    artifacts = $artifacts
}
[IO.File]::WriteAllText((Join-Path $output "MANIFEST.json"), ($manifest | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
$sumLines = @($artifacts | ForEach-Object { "$($_.sha256)  $($_.path)" })
[IO.File]::WriteAllLines((Join-Path $output "SHA256SUMS.txt"), $sumLines, (New-Object Text.UTF8Encoding($false)))

Write-DemoSuccess "Bundle staged successfully"
Write-Host "Next: run 'Set Credential Package Password.cmd' inside $output"
