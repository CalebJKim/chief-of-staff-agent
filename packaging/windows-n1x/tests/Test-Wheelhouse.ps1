param(
    [Parameter(Mandatory = $true)][string]$Wheelhouse,
    [Parameter(Mandatory = $true)][string]$Requirements
)

$ErrorActionPreference = "Stop"
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("cos-wheel-test-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
    & python -m pip install --disable-pip-version-check --no-index --find-links $Wheelhouse --target $testRoot -r $Requirements
    if ($LASTEXITCODE -ne 0) { throw "Offline wheel installation failed." }
    $previousPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = $testRoot
        & python -c "import googleapiclient, google.oauth2.credentials, google_auth_oauthlib.flow, httplib2; print('OFFLINE_WHEELHOUSE_OK')"
        if ($LASTEXITCODE -ne 0) { throw "Offline wheel import check failed." }
    } finally {
        $env:PYTHONPATH = $previousPythonPath
    }
} finally {
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
