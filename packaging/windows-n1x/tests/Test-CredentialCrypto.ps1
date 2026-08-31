$ErrorActionPreference = "Stop"
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("cos-crypto-test-" + [guid]::NewGuid().ToString("N"))
$scripts = Join-Path (Split-Path -Parent $PSScriptRoot) "scripts"
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
    [IO.File]::WriteAllText((Join-Path $testRoot "client.json"), '{"installed":{"client_id":"dummy","client_secret":"dummy"}}')
    [IO.File]::WriteAllText((Join-Path $testRoot "token.json"), '{"type":"authorized_user","refresh_token":"dummy"}')
    [IO.File]::WriteAllText((Join-Path $testRoot "state.json"), '{"folder_id":"dummy"}')
    . (Join-Path $scripts "CredentialCrypto.ps1")
    $secure = ConvertTo-SecureString "correct horse battery staple" -AsPlainText -Force
    Protect-DemoCredentialPackage -ClientSecretPath (Join-Path $testRoot "client.json") -TokenPath (Join-Path $testRoot "token.json") -WorkspaceStatePath (Join-Path $testRoot "state.json") -OutputPath (Join-Path $testRoot "credentials.enc") -Password $secure
    Import-DemoCredentialPackage -PackagePath (Join-Path $testRoot "credentials.enc") -HermesHome (Join-Path $testRoot "imported") -Password $secure
    if (-not (Test-Path -LiteralPath (Join-Path $testRoot "imported\google_token.json"))) { throw "Token was not restored." }
    if (-not (Test-Path -LiteralPath (Join-Path $testRoot "imported\chief-of-staff-workspace-state.json"))) { throw "Workspace state was not restored." }
    $wrong = ConvertTo-SecureString "this is the wrong password" -AsPlainText -Force
    $rejected = $false
    try { Import-DemoCredentialPackage -PackagePath (Join-Path $testRoot "credentials.enc") -HermesHome (Join-Path $testRoot "wrong") -Password $wrong } catch { $rejected = $true }
    if (-not $rejected) { throw "Wrong password was not rejected." }
    Write-Host "CRYPTO_ROUNDTRIP_OK"
} finally {
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
