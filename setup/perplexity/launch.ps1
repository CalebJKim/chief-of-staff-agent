$ErrorActionPreference = 'Stop'
# The packaged app keeps account-specific skills and saves its model endpoint
# through Settings > Local Inference. Development environment overrides are ignored.
$Package = Get-AppxPackage 'PerplexityAI.PerplexityApp'
if (-not $Package) { throw 'The supplied Perplexity MSIX has not been installed.' }
if (Get-Process -Name Perplexity -ErrorAction SilentlyContinue) {
    Write-Host 'Perplexity is already running. Choose Computer and the Custom local model.'
    exit 0
}
Start-Process -FilePath (Join-Path $Package.InstallLocation 'app\Perplexity.exe')
