param(
    [string]$InstallRoot,
    [switch]$Repair,
    [switch]$SkipWorkspacePreparation,
    [switch]$ForceCredentials
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0
. (Join-Path $PSScriptRoot "Common.ps1")
. (Join-Path $PSScriptRoot "CredentialCrypto.ps1")

$bundleRoot = Get-DemoBundleRoot
$paths = Get-DemoPaths $InstallRoot
$payload = Join-Path $bundleRoot "payload"
$credentialPackage = Join-Path $bundleRoot "_private\google-credentials.enc"
$manifestPath = Join-Path $bundleRoot "MANIFEST.json"

function Assert-BundleFiles {
    $required = @(
        (Join-Path $payload "models\$script:DemoModelName"),
        (Join-Path $payload "models\$script:DemoProjectorName"),
        (Join-Path $payload "llama.cpp\llama-server.exe"),
        (Join-Path $payload "demo-source\install.py"),
        (Join-Path $payload "hermes\install.ps1"),
        $credentialPackage,
        $manifestPath
    )
    foreach ($file in $required) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Bundle file is missing: $file" }
    }
}

function Assert-FreeSpace {
    param([string]$TargetRoot)
    $full = [IO.Path]::GetFullPath($TargetRoot)
    $driveRoot = [IO.Path]::GetPathRoot($full)
    $drive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID = '$($driveRoot.TrimEnd('\'))'"
    $required = 30GB
    if (-not $drive -or $drive.FreeSpace -lt $required) {
        $free = if ($drive) { [math]::Round($drive.FreeSpace / 1GB, 1) } else { 0 }
        throw "At least 30 GiB of free local disk space is required; $free GiB is available."
    }
}

function Invoke-HermesInstaller {
    $installer = Join-Path $payload "hermes\install.ps1"
    $userVariables = @("HERMES_HOME", "HERMES_GIT_BASH_PATH", "UV_INSTALL_DIR")
    $saved = @{}
    foreach ($name in $userVariables) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, "User") }
    $savedPath = [Environment]::GetEnvironmentVariable("Path", "User")
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer -SkipSetup -SkipComputerUse -Commit $script:DemoHermesCommit -HermesHome $paths.HermesHome -InstallDir $paths.HermesInstall
        if ($LASTEXITCODE -ne 0) { throw "Hermes installer failed with exit code $LASTEXITCODE." }
    } finally {
        foreach ($name in $userVariables) { [Environment]::SetEnvironmentVariable($name, $saved[$name], "User") }
        [Environment]::SetEnvironmentVariable("Path", $savedPath, "User")
    }
    if (-not (Test-Path -LiteralPath $paths.HermesExe -PathType Leaf)) { throw "Hermes executable was not created at $($paths.HermesExe)." }
    if (-not (Test-Path -LiteralPath $paths.PythonExe -PathType Leaf)) { throw "Hermes Python environment was not created at $($paths.PythonExe)." }
}

function Import-DemoCredentials {
    if ((Test-Path -LiteralPath (Join-Path $paths.HermesHome "google_token.json")) -and -not $ForceCredentials) {
        Write-DemoSuccess "Existing imported Google credentials preserved"
        return
    }
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $password = Read-Host "Credential-package passphrase" -AsSecureString
        try {
            Write-DemoStep "Decrypting the local credential package"
            Import-DemoCredentialPackage -PackagePath $credentialPackage -HermesHome $paths.HermesHome -Password $password
            Write-DemoSuccess "Google OAuth client, token, and workspace metadata imported"
            return
        } catch {
            if ($attempt -eq 3) { throw }
            Write-DemoWarning $_.Exception.Message
            Write-Host "Please try again."
        }
    }
}

function Set-HermesConfiguration {
    $previousHome = $env:HERMES_HOME
    try {
        $env:HERMES_HOME = $paths.HermesHome
        & $paths.HermesExe config set model.default $script:DemoModelAlias | Out-Host
        & $paths.HermesExe config set model.provider custom | Out-Host
        & $paths.HermesExe config set model.base_url "http://127.0.0.1:$($script:DemoPort)/v1" | Out-Host
        & $paths.HermesExe config set model.context_length ([string]$script:DemoContextLength) | Out-Host
        & $paths.HermesExe tools enable skills terminal --platform cli | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Hermes configuration failed." }
    } finally {
        $env:HERMES_HOME = $previousHome
    }
}

function Install-AppDependencies {
    $wheelhouse = Join-Path $payload "python-wheels"
    $requirements = Join-Path $paths.App "requirements.txt"
    & $paths.PythonExe -m pip install --disable-pip-version-check --no-index --find-links $wheelhouse -r $requirements
    if ($LASTEXITCODE -ne 0) { throw "Offline Python dependency installation failed." }
    & $paths.PythonExe (Join-Path $paths.App "install.py") --hermes-home $paths.HermesHome
    if ($LASTEXITCODE -ne 0) { throw "Chief of Staff skill installation failed." }
}

function Test-InstalledArtifact {
    param([string]$Path, [string]$ExpectedHash, [string]$Label)
    Write-DemoStep "Verifying $Label"
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedHash) { throw "$Label failed SHA-256 verification." }
    Write-DemoSuccess "$Label verified"
}

function Create-DemoShortcuts {
    $desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
    if (-not $desktop) { return }
    $shell = New-Object -ComObject WScript.Shell
    $items = @(
        @{ Name = "Start Chief of Staff Demo"; Script = "Start-Demo.ps1" },
        @{ Name = "Reset and Start Fresh Demo"; Script = "Reset-Demo.ps1" },
        @{ Name = "Chief of Staff Demo Diagnostics"; Script = "Validate-Demo.ps1" }
    )
    foreach ($item in $items) {
        $shortcut = $shell.CreateShortcut((Join-Path $desktop ($item.Name + ".lnk")))
        $shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
        $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $paths.Root "launcher\$($item.Script)")`""
        $shortcut.WorkingDirectory = $paths.App
        $shortcut.Description = $item.Name
        $shortcut.Save()
    }
    Write-DemoSuccess "Desktop shortcuts created"
}

Write-DemoHeader "Chief of Staff Demo Setup"
Write-Host "Bundle:  $bundleRoot"
Write-Host "Install: $($paths.Root)"
Write-Host "This installs an isolated demo profile and does not replace another Hermes profile."

Assert-BundleFiles
Assert-FreeSpace $paths.Root
$preflight = Assert-N1XPreflight
Write-DemoSuccess "$($preflight.GPUName); $($preflight.InstalledGiB) GiB unified memory; $($preflight.GPUCarveoutGiB) GiB GPU carveout; driver $($preflight.Driver)"

Write-DemoHeader "Copying version-locked payload"
New-Item -ItemType Directory -Force -Path $paths.Root, $paths.Logs | Out-Null
Invoke-RobocopyChecked (Join-Path $payload "llama.cpp") $paths.LlamaRoot
Invoke-RobocopyChecked (Join-Path $payload "models") (Join-Path $paths.Root "models")
Invoke-RobocopyChecked (Join-Path $payload "demo-source") $paths.App
Invoke-RobocopyChecked $PSScriptRoot (Join-Path $paths.Root "launcher")
Test-InstalledArtifact $paths.Model $script:DemoModelSha256 "Qwen model"
Test-InstalledArtifact $paths.Projector $script:DemoProjectorSha256 "multimodal projector"

Write-DemoHeader "Installing Hermes and the Chief of Staff agent"
if ($Repair -or -not (Test-Path -LiteralPath $paths.HermesExe -PathType Leaf)) {
    Invoke-HermesInstaller
} else {
    Write-DemoSuccess "Existing isolated Hermes runtime preserved"
}
Install-AppDependencies
Set-HermesConfiguration
Import-DemoCredentials

$previousHome = $env:HERMES_HOME
try {
    $env:HERMES_HOME = $paths.HermesHome
    Write-DemoStep "Checking Google authorization with a live API call"
    & $paths.PythonExe (Join-Path $paths.App "setup\google-workspace\setup.py") --check-live
    if ($LASTEXITCODE -ne 0) {
        throw "The imported OAuth token is not usable. Run the bundled Google reconnect flow before the demo."
    }
    Write-DemoSuccess "Google authorization is live"

    if (-not $SkipWorkspacePreparation) {
        $statePath = Join-Path $paths.HermesHome "chief-of-staff-workspace-state.json"
        if (Test-Path -LiteralPath $statePath) {
            Write-DemoStep "Resetting the existing reference workspace to its demo baseline"
            & $paths.PythonExe (Join-Path $paths.App "demo\seed_workspace.py") --reset --confirm
        } else {
            Write-DemoStep "Creating the reference Google Workspace"
            & $paths.PythonExe (Join-Path $paths.App "demo\seed_workspace.py") --confirm
        }
        if ($LASTEXITCODE -ne 0) { throw "Google Workspace preparation failed." }
        Write-DemoSuccess "Reference workspace is ready"
    }

    Write-DemoStep "Running Chief of Staff verification"
    & $paths.PythonExe (Join-Path $paths.App "skills\productivity\ingest\scripts\verify.py")
    if ($LASTEXITCODE -ne 0) { throw "Chief of Staff verification failed." }
} finally {
    $env:HERMES_HOME = $previousHome
}

$installState = [ordered]@{
    installed_utc = [DateTime]::UtcNow.ToString("o")
    bundle_root = $bundleRoot
    install_root = $paths.Root
    hermes_commit = $script:DemoHermesCommit
    llama_commit = $script:DemoLlamaCommit
    model = $script:DemoModelName
    port = $script:DemoPort
    context_length = $script:DemoContextLength
}
[IO.File]::WriteAllText($paths.State, ($installState | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
Create-DemoShortcuts

Write-DemoHeader "Demo ready"
Write-Host "Use the 'Start Chief of Staff Demo' desktop shortcut."
Write-Host "The USB can be removed after installation."
Write-Host ""
Read-Host "Press Enter to close"
