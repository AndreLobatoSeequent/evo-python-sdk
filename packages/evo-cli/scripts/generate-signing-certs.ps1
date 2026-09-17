#!/usr/bin/env pwsh
# Generates self-signed certificates for all native installers (Windows, macOS, Linux).
# For development/testing purposes only.
#
# Creates:
#   - Windows code signing cert (.pfx)
#   - macOS application & installer signing certs (.p12)
#   - Linux GPG signing key
#
# All outputs are base64-encoded for easy copy-paste into GitHub secrets.

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$outputDir = Join-Path $scriptDir ".certs"
$certPassword = $env:CERT_PASSWORD ?? "EvoCLI@Dev2024"
$certOrg = $env:CERT_ORG ?? "Seequent"
$certEmail = $env:CERT_EMAIL ?? "support@seequent.com"

if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Force $outputDir | Out-Null
}

Set-Location $outputDir

Write-Host "=== Generating self-signed certificates for evo-cli ===" -ForegroundColor Cyan
Write-Host "Output directory: $outputDir"
Write-Host "Certificate password: $certPassword"
Write-Host "Organization: $certOrg"
Write-Host ""

# ============================================================================
# Windows Code Signing Certificate
# ============================================================================
Write-Host "[1/3] Generating Windows code signing certificate..." -ForegroundColor Yellow

if (Test-Path "windows-signing.pfx") {
    Write-Host "  ✓ windows-signing.pfx already exists, skipping"
} else {
    # Create a self-signed certificate
    $cert = New-SelfSignedCertificate `
        -CertStoreLocation Cert:\CurrentUser\My `
        -Subject "CN=$certOrg, O=$certOrg, C=US" `
        -FriendlyName "$certOrg Code Signing" `
        -KeyUsage DigitalSignature `
        -Type CodeSigningCert `
        -NotAfter (Get-Date).AddYears(5)

    # Export to .pfx
    $securePwd = ConvertTo-SecureString $certPassword -AsPlainText -Force
    Export-PfxCertificate -Cert $cert -FilePath "windows-signing.pfx" `
        -Password $securePwd -Force | Out-Null

    # Remove from cert store (optional - clean up)
    Remove-Item $cert.PSPath -Force

    Write-Host "  ✓ windows-signing.pfx created"
}

# ============================================================================
# macOS Signing Certificates (requires openssl - should be available on Windows)
# ============================================================================
Write-Host "[2/3] Generating macOS code signing certificates..." -ForegroundColor Yellow

# Check if openssl is available
$opensslCmd = Get-Command openssl -ErrorAction SilentlyContinue
if (-not $opensslCmd) {
    Write-Host "  ⚠ openssl not found. For macOS certs, run on macOS/Linux or install OpenSSL." -ForegroundColor Yellow
    Write-Host "  Install OpenSSL: https://slproweb.com/products/Win32OpenSSL.html"
} else {
    if ((Test-Path "macos-app-signing.p12") -and (Test-Path "macos-installer-signing.p12")) {
        Write-Host "  ✓ macOS certs already exist, skipping"
    } else {
        # Application signing certificate
        openssl genrsa -out macos-app.key 2048 2>&1 | Out-Null
        openssl req -new -x509 -key macos-app.key -out macos-app.crt `
            -days 1825 `
            -subj "/CN=$certOrg Application/O=$certOrg/C=US" `
            -addext "extendedKeyUsage=codeSigning" 2>&1 | Out-Null

        openssl pkcs12 -export -out macos-app-signing.p12 `
            -inkey macos-app.key -in macos-app.crt `
            -name "$certOrg Application" `
            -passout pass:$certPassword 2>&1 | Out-Null

        # Installer signing certificate
        openssl genrsa -out macos-installer.key 2048 2>&1 | Out-Null
        openssl req -new -x509 -key macos-installer.key -out macos-installer.crt `
            -days 1825 `
            -subj "/CN=$certOrg Installer/O=$certOrg/C=US" `
            -addext "extendedKeyUsage=codeSigning" 2>&1 | Out-Null

        openssl pkcs12 -export -out macos-installer-signing.p12 `
            -inkey macos-installer.key -in macos-installer.crt `
            -name "$certOrg Installer" `
            -passout pass:$certPassword 2>&1 | Out-Null

        Remove-Item macos-app.key, macos-app.crt, macos-installer.key, macos-installer.crt -Force

        Write-Host "  ✓ macos-app-signing.p12 created"
        Write-Host "  ✓ macos-installer-signing.p12 created"
    }
}

# ============================================================================
# Linux GPG Signing Key (requires gpg - should be available on Windows via Git Bash)
# ============================================================================
Write-Host "[3/3] Generating Linux GPG signing key..." -ForegroundColor Yellow

$gpgCmd = Get-Command gpg -ErrorAction SilentlyContinue
if (-not $gpgCmd) {
    Write-Host "  ⚠ gpg not found. For GPG keys, run on macOS/Linux or install GPG for Windows:" -ForegroundColor Yellow
    Write-Host "    https://gpg4win.org/"
} else {
    if (Test-Path "linux-signing.gpg") {
        Write-Host "  ✓ linux-signing.gpg already exists, skipping"
    } else {
        # Create GPG key
        $gpgBatch = @"
%no-protection
Key-Type: RSA
Key-Length: 2048
Name-Real: $certOrg
Name-Email: $certEmail
Expire-Date: 1825d
"@
        $gpgBatch | Set-Content -Path "gpg-batch.txt" -Encoding UTF8

        & gpg --batch --generate-key gpg-batch.txt 2>&1 | Select-String -Pattern "key|error" | ForEach-Object { Write-Host "  $_" } || $true
        Remove-Item "gpg-batch.txt" -Force

        # Export the key
        & gpg --output linux-signing.gpg --armor --export-secret-keys "$certOrg" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ✗ Failed to export GPG key. Make sure '$certOrg' key was created." -ForegroundColor Red
        } else {
            Write-Host "  ✓ linux-signing.gpg created"
        }
    }
}

# ============================================================================
# Encode certificates to base64 for GitHub secrets
# ============================================================================
Write-Host ""
Write-Host "=== Generating base64-encoded secrets for GitHub ===" -ForegroundColor Cyan
Write-Host ""

if (Test-Path "windows-signing.pfx") {
    Write-Host "WINDOWS_CODE_SIGNING_CERT:" -ForegroundColor Green
    $winCertB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $outputDir "windows-signing.pfx")))
    Write-Host $winCertB64
    Write-Host ""
}

if (Test-Path "macos-app-signing.p12") {
    Write-Host "APPLE_CERTIFICATE (Application):" -ForegroundColor Green
    $macCertB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $outputDir "macos-app-signing.p12")))
    Write-Host $macCertB64
    Write-Host ""
}

if (Test-Path "linux-signing.gpg") {
    Write-Host "LINUX_GPG_SIGNING_KEY:" -ForegroundColor Green
    Get-Content "linux-signing.gpg"
    Write-Host ""
}

Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "✓ Organization: $certOrg"
Write-Host "✓ Certificate password: $certPassword"
Write-Host ""
Write-Host "GitHub Secrets to add:"
Write-Host "  WINDOWS_CODE_SIGNING_CERT         (paste base64 output)"
Write-Host "  WINDOWS_CODE_SIGNING_PASSWORD     → $certPassword"
Write-Host "  APPLE_CERTIFICATE                 (paste base64 output)"
Write-Host "  APPLE_CERTIFICATE_PASSWORD        → $certPassword"
Write-Host "  APPLE_SIGNING_IDENTITY            → $certOrg Application  (no quotes)"
Write-Host "  APPLE_INSTALLER_SIGNING_IDENTITY  → $certOrg Application  (no quotes; reuses the same imported cert)"
Write-Host ""
Write-Host "NOTE: macos-installer-signing.p12 was also generated, but publish-evo-cli.yaml" -ForegroundColor DarkGray
Write-Host "only imports APPLE_CERTIFICATE (the application cert) into the CI keychain," -ForegroundColor DarkGray
Write-Host "so APPLE_INSTALLER_SIGNING_IDENTITY reuses that same identity above unless" -ForegroundColor DarkGray
Write-Host "you add a matching import step for the installer cert." -ForegroundColor DarkGray
Write-Host "  LINUX_GPG_SIGNING_KEY             (paste GPG key output)"
Write-Host ""
Write-Host "Certificate files are in: $outputDir" -ForegroundColor Yellow
Write-Host ""
Write-Host "NOTE: To customize, set `$env:CERT_ORG and `$env:CERT_EMAIL before running:" -ForegroundColor DarkGray
Write-Host '  $env:CERT_ORG = "My Company"; $env:CERT_EMAIL = "me@example.com"; .\generate-signing-certs.ps1' -ForegroundColor DarkGray
Write-Host ""
