param(
    [string]$HermesHome = $(if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA "hermes" }),
    [string]$OutputPath = $(Join-Path (Split-Path -Parent $PSScriptRoot) "_private\google-credentials.enc")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0
. (Join-Path $PSScriptRoot "CredentialCrypto.ps1")

$client = Join-Path $HermesHome "google_client_secret.json"
$token = Join-Path $HermesHome "google_token.json"
$workspaceState = Join-Path $HermesHome "chief-of-staff-workspace-state.json"

Write-Host "Chief of Staff demo credential package" -ForegroundColor Cyan
Write-Host "This prompt is local. Your passphrase is masked and is not written to chat, logs, scripts, or command history."
Write-Host "Use a unique passphrase and save it in your password manager."
Write-Host ""

$first = Read-Host "New credential-package passphrase" -AsSecureString
$second = Read-Host "Confirm passphrase" -AsSecureString
$firstPlain = ConvertFrom-SecureStringPlaintext $first
$secondPlain = ConvertFrom-SecureStringPlaintext $second
try {
    if ([string]::IsNullOrWhiteSpace($firstPlain)) { throw "The passphrase cannot be empty." }
    if ($firstPlain.Length -lt 12) { throw "Use at least 12 characters." }
    if ($firstPlain -cne $secondPlain) { throw "The passphrases did not match." }
} finally {
    $firstPlain = $null
    $secondPlain = $null
}

Write-Host "Encrypting credential package..."
Protect-DemoCredentialPackage -ClientSecretPath $client -TokenPath $token -WorkspaceStatePath $workspaceState -OutputPath $OutputPath -Password $first
Write-Host ""
Write-Host "[OK] Encrypted credential package created at:" -ForegroundColor Green
Write-Host $OutputPath
Write-Host "No plaintext credential files were copied into the bundle."
