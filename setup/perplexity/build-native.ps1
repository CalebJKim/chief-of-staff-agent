param(
    [ValidateSet('aarch64-pc-windows-msvc', 'x86_64-pc-windows-msvc')]
    [string]$Target = 'aarch64-pc-windows-msvc'
)
$ErrorActionPreference = 'Stop'
$RepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$NativeRoot = Join-Path $RepoRoot 'skills\productivity\chief-of-staff\native'
$PreviousTarget = $env:CARGO_TARGET_DIR
$PreviousFlags = $env:RUSTFLAGS
$PreviousPath = $env:PATH
try {
    if (-not (Get-Command clang.exe -ErrorAction SilentlyContinue)) {
        $VsWhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
        if (Test-Path -LiteralPath $VsWhere) {
            $VsRoot = & $VsWhere -latest -products '*' -property installationPath
            foreach ($Candidate in @('VC\Tools\Llvm\ARM64\bin', 'VC\Tools\Llvm\x64\bin', 'VC\Tools\Llvm\bin')) {
                if ($VsRoot -and (Test-Path -LiteralPath (Join-Path $VsRoot "$Candidate\clang.exe"))) {
                    $env:PATH = (Join-Path $VsRoot $Candidate) + ';' + $env:PATH
                    break
                }
            }
        }
    }
    $env:CARGO_TARGET_DIR = Join-Path $RepoRoot 'out\native-build'
    $env:RUSTFLAGS = ($PreviousFlags + ' -C target-feature=+crt-static').Trim()
    & cargo build --locked --release --target $Target --manifest-path (Join-Path $NativeRoot 'Cargo.toml')
    if ($LASTEXITCODE -ne 0) { throw 'Native build failed; installed binary was not changed.' }
    $Binary = Join-Path $env:CARGO_TARGET_DIR "$Target\release\cos-actions.exe"
    $Destination = Join-Path $RepoRoot 'skills\productivity\chief-of-staff\scripts\cos-actions.exe'
    Copy-Item -LiteralPath $Binary -Destination $Destination -Force
    [PSCustomObject]@{Target=$Target; Binary=$Destination; SHA256=(Get-FileHash -LiteralPath $Destination).Hash} | ConvertTo-Json
} finally {
    $env:CARGO_TARGET_DIR = $PreviousTarget
    $env:RUSTFLAGS = $PreviousFlags
    $env:PATH = $PreviousPath
}
