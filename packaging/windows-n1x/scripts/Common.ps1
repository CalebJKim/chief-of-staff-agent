Set-StrictMode -Version 2.0

$script:DemoHermesCommit = "efb6b40f94ebce3c1f0cfe197942b17d68e2136b"
$script:DemoLlamaCommit = "be4a6a63e"
$script:DemoModelName = "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"
$script:DemoProjectorName = "mmproj-BF16.gguf"
$script:DemoModelSha256 = "0b21525e972670ed59e1812e170b27c26355381f0656ecc4e25617ece7dac58b"
$script:DemoProjectorSha256 = "da63cb47a76763c712393f8a017070188a304fa39f8aeea6edc629ed7b975cfa"
$script:DemoModelAlias = "qwen3.6-35b-a3b"
$script:DemoPort = 8080
$script:DemoContextLength = 65536

function Get-DemoBundleRoot {
    return (Split-Path -Parent $PSScriptRoot)
}

function Get-DemoInstallRoot {
    param([string]$Override)
    if ($Override) {
        return [IO.Path]::GetFullPath($Override)
    }
    return (Join-Path $env:LOCALAPPDATA "ChiefOfStaffDemo")
}

function Get-DemoPaths {
    param([string]$InstallRoot)
    $root = Get-DemoInstallRoot $InstallRoot
    return [pscustomobject]@{
        Root = $root
        App = Join-Path $root "app"
        HermesHome = Join-Path $root "hermes"
        HermesInstall = Join-Path $root "hermes\hermes-agent"
        HermesExe = Join-Path $root "hermes\hermes-agent\bin\hermes.exe"
        PythonExe = Join-Path $root "hermes\hermes-agent\venv\Scripts\python.exe"
        LlamaRoot = Join-Path $root "llama.cpp"
        LlamaServer = Join-Path $root "llama.cpp\llama-server.exe"
        Model = Join-Path $root ("models\" + $script:DemoModelName)
        Projector = Join-Path $root ("models\" + $script:DemoProjectorName)
        Logs = Join-Path $root "logs"
        State = Join-Path $root "install-state.json"
        Pid = Join-Path $root "llama-server.pid"
    }
}

function Write-DemoHeader {
    param([string]$Text)
    Write-Host ""
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

function Write-DemoStep {
    param([string]$Text)
    Write-Host "-> $Text" -ForegroundColor Cyan
}

function Write-DemoSuccess {
    param([string]$Text)
    Write-Host "[OK] $Text" -ForegroundColor Green
}

function Write-DemoWarning {
    param([string]$Text)
    Write-Host "[WARNING] $Text" -ForegroundColor Yellow
}

function Find-NvidiaSmi {
    $command = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    $candidate = Get-ChildItem -LiteralPath "$env:SystemRoot\System32\DriverStore\FileRepository" -Filter "nvidia-smi.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($candidate) { return $candidate.FullName }
    return $null
}

function Get-N1XPreflight {
    $os = Get-CimInstance Win32_OperatingSystem
    $computer = Get-CimInstance Win32_ComputerSystem
    $gpu = Get-CimInstance Win32_VideoController | Where-Object Name -Match "RTX Spark N1X" | Select-Object -First 1
    $smi = Find-NvidiaSmi
    $gpuMiB = $null
    $driver = $null
    if ($smi) {
        $row = & $smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits 2>$null | Select-Object -First 1
        if ($row) {
            $parts = @($row -split "," | ForEach-Object { $_.Trim() })
            if ($parts.Count -ge 3) {
                $gpuMiB = [double]$parts[1]
                $driver = $parts[2]
            }
        }
    }
    return [pscustomobject]@{
        IsArm64 = ($os.OSArchitecture -match "ARM")
        OS = $os.Caption
        OSVersion = $os.Version
        IsN1X = [bool]$gpu
        GPUName = if ($gpu) { $gpu.Name } else { $null }
        Driver = $driver
        InstalledGiB = [math]::Round((Get-CimInstance Win32_PhysicalMemory | Measure-Object Capacity -Sum).Sum / 1GB, 2)
        CPUVisibleGiB = [math]::Round($computer.TotalPhysicalMemory / 1GB, 2)
        GPUCarveoutGiB = if ($gpuMiB) { [math]::Round(($gpuMiB * 1MB) / 1GB, 2) } else { $null }
        NvidiaSmi = $smi
    }
}

function Assert-N1XPreflight {
    $result = Get-N1XPreflight
    if (-not $result.IsArm64) { throw "This bundle requires Windows ARM64." }
    if (-not $result.IsN1X) { throw "NVIDIA RTX Spark N1X was not detected." }
    if (-not $result.NvidiaSmi) { throw "nvidia-smi was not found; install or repair the NVIDIA N1X driver." }
    if ($result.InstalledGiB -lt 60) { throw "At least 64 GB nominal unified memory is required." }
    if ($result.GPUCarveoutGiB -and $result.GPUCarveoutGiB -lt 15) {
        throw "The GPU carveout is $($result.GPUCarveoutGiB) GiB; this bundle expects the 16 GB GPU / 48 GB CPU configuration."
    }
    return $result
}

function Invoke-RobocopyChecked {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    & robocopy.exe $Source $Destination /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /J /NP
    if ($LASTEXITCODE -ge 8) {
        throw "Copy failed from '$Source' to '$Destination' (robocopy exit $LASTEXITCODE)."
    }
}

function Test-DemoServerHealth {
    param([int]$Port = $script:DemoPort)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3 -ErrorAction Stop
        return ($response.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Get-DemoServerProcess {
    param([string]$ServerPath)
    $resolved = if (Test-Path -LiteralPath $ServerPath) { (Resolve-Path -LiteralPath $ServerPath).Path } else { $ServerPath }
    return @(Get-CimInstance Win32_Process -Filter "Name = 'llama-server.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and ([string]::Equals($_.ExecutablePath, $resolved, [StringComparison]::OrdinalIgnoreCase))
    })
}

function Stop-DemoServer {
    param([string]$ServerPath)
    $processes = Get-DemoServerProcess $ServerPath
    foreach ($process in $processes) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    return $processes.Count
}

function Assert-SafeDemoPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedLeaf
    )
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if ([IO.Path]::GetPathRoot($full).TrimEnd('\') -eq $full) {
        throw "Refusing to operate on a drive root: $full"
    }
    if ((Split-Path -Leaf $full) -ne $ExpectedLeaf) {
        throw "Refusing unexpected path '$full'; expected leaf '$ExpectedLeaf'."
    }
    return $full
}

function Read-YesNo {
    param([string]$Prompt, [bool]$DefaultYes = $false)
    $suffix = if ($DefaultYes) { "[Y/n]" } else { "[y/N]" }
    $answer = Read-Host "$Prompt $suffix"
    if (-not $answer) { return $DefaultYes }
    return $answer.Trim().ToLowerInvariant().StartsWith("y")
}
