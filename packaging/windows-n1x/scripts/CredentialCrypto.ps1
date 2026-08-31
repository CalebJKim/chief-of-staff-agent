Set-StrictMode -Version 2.0

$script:CredentialMagic = "COS-CREDENTIALS"
$script:CredentialVersion = 1
$script:CredentialIterations = 600000

function ConvertFrom-SecureStringPlaintext {
    param([Parameter(Mandatory = $true)][Security.SecureString]$SecureString)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Join-ByteArrays {
    param([byte[][]]$Arrays)
    $length = 0
    foreach ($array in $Arrays) { $length += $array.Length }
    $result = New-Object byte[] $length
    $offset = 0
    foreach ($array in $Arrays) {
        [Array]::Copy($array, 0, $result, $offset, $array.Length)
        $offset += $array.Length
    }
    return $result
}

function Get-CredentialKeyMaterial {
    param(
        [Parameter(Mandatory = $true)][string]$Password,
        [Parameter(Mandatory = $true)][byte[]]$Salt,
        [Parameter(Mandatory = $true)][int]$Iterations
    )
    $kdf = New-Object Security.Cryptography.Rfc2898DeriveBytes($Password, $Salt, $Iterations, [Security.Cryptography.HashAlgorithmName]::SHA256)
    try { return $kdf.GetBytes(64) } finally { $kdf.Dispose() }
}

function Test-FixedTimeEqual {
    param([byte[]]$Left, [byte[]]$Right)
    if ($null -eq $Left -or $null -eq $Right -or $Left.Length -ne $Right.Length) { return $false }
    $difference = 0
    for ($index = 0; $index -lt $Left.Length; $index++) {
        $difference = $difference -bor ($Left[$index] -bxor $Right[$index])
    }
    return ($difference -eq 0)
}

function Protect-DemoCredentialPackage {
    param(
        [Parameter(Mandatory = $true)][string]$ClientSecretPath,
        [Parameter(Mandatory = $true)][string]$TokenPath,
        [string]$WorkspaceStatePath,
        [Parameter(Mandatory = $true)][string]$OutputPath,
        [Parameter(Mandatory = $true)][Security.SecureString]$Password
    )
    foreach ($required in @($ClientSecretPath, $TokenPath)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required credential file not found: $required" }
        Get-Content -LiteralPath $required -Raw | ConvertFrom-Json | Out-Null
    }

    $payload = [ordered]@{
        created_utc = [DateTime]::UtcNow.ToString("o")
        client_secret_json = [string](Get-Content -LiteralPath $ClientSecretPath -Raw)
        token_json = [string](Get-Content -LiteralPath $TokenPath -Raw)
        workspace_state_json = if ($WorkspaceStatePath -and (Test-Path -LiteralPath $WorkspaceStatePath -PathType Leaf)) { [string](Get-Content -LiteralPath $WorkspaceStatePath -Raw) } else { $null }
    }
    $plaintext = [Text.Encoding]::UTF8.GetBytes(($payload | ConvertTo-Json -Compress))
    $salt = New-Object byte[] 16
    $iv = New-Object byte[] 16
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($salt); $rng.GetBytes($iv) } finally { $rng.Dispose() }

    $plainPassword = ConvertFrom-SecureStringPlaintext $Password
    try {
        $material = Get-CredentialKeyMaterial -Password $plainPassword -Salt $salt -Iterations $script:CredentialIterations
    } finally {
        $plainPassword = $null
    }
    $encryptionKey = New-Object byte[] 32
    $macKey = New-Object byte[] 32
    [Array]::Copy($material, 0, $encryptionKey, 0, 32)
    [Array]::Copy($material, 32, $macKey, 0, 32)

    $aes = [Security.Cryptography.Aes]::Create()
    try {
        $aes.KeySize = 256
        $aes.Mode = [Security.Cryptography.CipherMode]::CBC
        $aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7
        $aes.Key = $encryptionKey
        $aes.IV = $iv
        $encryptor = $aes.CreateEncryptor()
        try { $ciphertext = $encryptor.TransformFinalBlock($plaintext, 0, $plaintext.Length) } finally { $encryptor.Dispose() }
    } finally { $aes.Dispose() }

    $header = [Text.Encoding]::UTF8.GetBytes("$($script:CredentialMagic)|$($script:CredentialVersion)|$($script:CredentialIterations)|")
    $authenticated = Join-ByteArrays @($header, $salt, $iv, $ciphertext)
    $hmac = New-Object Security.Cryptography.HMACSHA256(,$macKey)
    try { $mac = $hmac.ComputeHash($authenticated) } finally { $hmac.Dispose() }

    $package = [ordered]@{
        magic = $script:CredentialMagic
        version = $script:CredentialVersion
        iterations = $script:CredentialIterations
        salt = [Convert]::ToBase64String($salt)
        iv = [Convert]::ToBase64String($iv)
        ciphertext = [Convert]::ToBase64String($ciphertext)
        mac = [Convert]::ToBase64String($mac)
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null
    [IO.File]::WriteAllText($OutputPath, ($package | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))

    [Array]::Clear($plaintext, 0, $plaintext.Length)
    [Array]::Clear($material, 0, $material.Length)
    [Array]::Clear($encryptionKey, 0, $encryptionKey.Length)
    [Array]::Clear($macKey, 0, $macKey.Length)
}

function Import-DemoCredentialPackage {
    param(
        [Parameter(Mandatory = $true)][string]$PackagePath,
        [Parameter(Mandatory = $true)][string]$HermesHome,
        [Parameter(Mandatory = $true)][Security.SecureString]$Password
    )
    if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) { throw "Credential package not found: $PackagePath" }
    $package = Get-Content -LiteralPath $PackagePath -Raw | ConvertFrom-Json
    if ($package.magic -ne $script:CredentialMagic -or [int]$package.version -ne $script:CredentialVersion) {
        throw "Unsupported credential package format."
    }
    $iterations = [int]$package.iterations
    $salt = [Convert]::FromBase64String([string]($package.salt))
    $iv = [Convert]::FromBase64String([string]($package.iv))
    $ciphertext = [Convert]::FromBase64String([string]($package.ciphertext))
    $expectedMac = [Convert]::FromBase64String([string]($package.mac))

    $plainPassword = ConvertFrom-SecureStringPlaintext $Password
    try { $material = Get-CredentialKeyMaterial -Password $plainPassword -Salt $salt -Iterations $iterations } finally { $plainPassword = $null }
    $encryptionKey = New-Object byte[] 32
    $macKey = New-Object byte[] 32
    [Array]::Copy($material, 0, $encryptionKey, 0, 32)
    [Array]::Copy($material, 32, $macKey, 0, 32)

    $header = [Text.Encoding]::UTF8.GetBytes("$($script:CredentialMagic)|$($script:CredentialVersion)|$iterations|")
    $authenticated = Join-ByteArrays @($header, $salt, $iv, $ciphertext)
    $hmac = New-Object Security.Cryptography.HMACSHA256(,$macKey)
    try { $actualMac = $hmac.ComputeHash($authenticated) } finally { $hmac.Dispose() }
    if (-not (Test-FixedTimeEqual $actualMac $expectedMac)) {
        throw "The credential-package password is incorrect or the package is damaged."
    }

    $aes = [Security.Cryptography.Aes]::Create()
    try {
        $aes.KeySize = 256
        $aes.Mode = [Security.Cryptography.CipherMode]::CBC
        $aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7
        $aes.Key = $encryptionKey
        $aes.IV = $iv
        $decryptor = $aes.CreateDecryptor()
        try { $plaintext = $decryptor.TransformFinalBlock($ciphertext, 0, $ciphertext.Length) } finally { $decryptor.Dispose() }
    } finally { $aes.Dispose() }

    try {
        $payloadText = [Text.Encoding]::UTF8.GetString($plaintext)
        $payload = ConvertFrom-Json -InputObject $payloadText
        $clientJson = [string]($payload.client_secret_json)
        $tokenJson = [string]($payload.token_json)
        ConvertFrom-Json -InputObject $clientJson | Out-Null
        ConvertFrom-Json -InputObject $tokenJson | Out-Null
        New-Item -ItemType Directory -Force -Path $HermesHome | Out-Null
        [IO.File]::WriteAllText((Join-Path $HermesHome "google_client_secret.json"), $clientJson, (New-Object Text.UTF8Encoding($false)))
        [IO.File]::WriteAllText((Join-Path $HermesHome "google_token.json"), $tokenJson, (New-Object Text.UTF8Encoding($false)))
        if ($payload.workspace_state_json) {
            $workspaceStateJson = [string]($payload.workspace_state_json)
            ConvertFrom-Json -InputObject $workspaceStateJson | Out-Null
            [IO.File]::WriteAllText((Join-Path $HermesHome "chief-of-staff-workspace-state.json"), $workspaceStateJson, (New-Object Text.UTF8Encoding($false)))
        }
    } finally {
        [Array]::Clear($plaintext, 0, $plaintext.Length)
        [Array]::Clear($material, 0, $material.Length)
        [Array]::Clear($encryptionKey, 0, $encryptionKey.Length)
        [Array]::Clear($macKey, 0, $macKey.Length)
    }
}
