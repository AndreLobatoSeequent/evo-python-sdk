# Code Signing Setup for evo-cli Native Installers

This guide explains how to set up self-signed certificates for all native installers (Windows, macOS, Linux).

## Overview

The GitHub Actions workflow in `.github/workflows/publish-evo-cli.yaml` supports automatic code signing for:
- **Windows**: `.exe` installer and uninstaller
- **macOS**: Application binaries and `.pkg` installer
- **Linux**: `.deb` package

When signing secrets are not configured, unsigned installers are built (which work but trigger security warnings).

## Quick Start

### 1. Generate Self-Signed Certificates

#### On Windows (using PowerShell):
```powershell
cd packages/evo-cli/scripts
.\generate-signing-certs.ps1
```

#### On macOS/Linux (using Bash):
```bash
cd packages/evo-cli/scripts
bash generate-signing-certs.sh
```

Both scripts will:
- Create `.certs/` subdirectory with certificate files
- Output base64-encoded secrets ready for GitHub
- Display the certificate password and key IDs you'll need

By default, certificates are issued to **Seequent** (`support@seequent.com`), matching the
`evo-cli` package's `pyproject.toml` authorship. To sign under a different name/email, set
`CERT_ORG` and `CERT_EMAIL` before running:

```bash
CERT_ORG="My Company" CERT_EMAIL="me@example.com" bash generate-signing-certs.sh
```
```powershell
$env:CERT_ORG = "My Company"; $env:CERT_EMAIL = "me@example.com"; .\generate-signing-certs.ps1
```

### 2. Add Secrets to GitHub

Go to your repository → **Settings → Secrets and variables → Actions → New repository secret**

Add these secrets (exact names matter):

#### Windows Signing
```
WINDOWS_CODE_SIGNING_CERT
WINDOWS_CODE_SIGNING_PASSWORD
```

#### macOS Signing
```
APPLE_CERTIFICATE                 (use the base64 from macos-app-signing.p12)
APPLE_CERTIFICATE_PASSWORD
APPLE_SIGNING_IDENTITY            (use: "Seequent Application")
APPLE_INSTALLER_SIGNING_IDENTITY  (use: "Seequent Installer")
```

#### Linux Signing
```
LINUX_GPG_SIGNING_KEY             (paste the full GPG key output)
LINUX_GPG_SIGNING_KEY_ID          (optional - auto-detected if not provided)
```

### 3. Test Your Setup

Trigger the workflow manually:
1. Go to **Actions → Build and publish evo-cli → Run workflow**
2. Enter a tag name (e.g., `evo-cli@v0.1.0-dev.999`)
3. The workflow will now build signed installers

Verify signatures:
```bash
# Windows
Get-AuthenticodeSignature "release\evo-cli-*.exe" | Format-List *

# macOS
codesign -v "release/evo-cli-*.pkg"
spctl -a -vvv -t install "release/evo-cli-*.pkg"

# Linux
debsigs --check "release/evo-cli_*.deb"
```

## Platform-Specific Details

### Windows

- **File**: `windows-signing.pfx`
- **Format**: PKCS#12 binary
- **Workflow**: 
  1. Certificate is imported from base64-encoded secret
  2. Passed to Inno Setup via `signtool.exe`
  3. Both installer and uninstaller are signed
- **Testing**: Try installing locally - the "unknown publisher" warning should be gone if signed by a trusted CA, or present but with your cert name if self-signed

### macOS

- **Files**: 
  - `macos-app-signing.p12` - for binary/dylib signing
  - `macos-installer-signing.p12` - for package signing (can be same as app)
- **Format**: PKCS#12 binary
- **Workflow**:
  1. Certificate is imported into a temporary keychain
  2. All executables and dylibs are signed with `codesign`
  3. The `.pkg` is signed with `productsign`
  4. (Optional) Notarization is skipped for self-signed certs
- **Limitations**: 
  - Self-signed certificates won't pass Gatekeeper by default
  - Notarization is only available with Apple Developer ID certificates
  - Users will see a Gatekeeper warning on first run

### Linux

- **File**: `linux-signing.gpg` (GPG private key)
- **Format**: ASCII-armored text
- **Workflow**:
  1. GPG key is imported into the build environment
  2. `debsigs` is used to sign the `.deb` package
  3. Signing verifies package integrity and origin
- **Requirements**: `debsigs` must be installed (`apt-get install debsigs`)
- **Testing**: `debsigs --check <package.deb>`

## Renewing Certificates

Self-signed certificates expire after 5 years. To renew:

```bash
# Remove old certificates
rm -rf packages/evo-cli/scripts/.certs

# Regenerate
bash packages/evo-cli/scripts/generate-signing-certs.sh

# Update GitHub secrets with new base64 values
```

## Production Deployment

For production releases, consider:

### Windows
- Purchase a **Code Signing Certificate** from a trusted CA (Digicert, Sectigo, etc.)
- Follow the same setup process but use the production certificate

### macOS
- Enroll in [Apple Developer Program](https://developer.apple.com/)
- Obtain a **Developer ID Application** certificate for signing binaries
- Obtain a **Developer ID Installer** certificate for signing packages
- Use the `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_SPECIFIC_PASSWORD` secrets to enable notarization

### Linux
- Generate an organization GPG key with your company info
- Publish the public key to a key server (keys.openpgp.org, etc.)
- Users can verify package authenticity: `apt-key add <public-key>`

## Troubleshooting

### Certificate not found during build
- Verify secrets are named exactly as shown above (case-sensitive on Linux)
- Check GitHub Actions log for the secret import step
- Ensure base64 encoding is correct (no newlines, single line)

### Signing fails on macOS
- For self-signed certs: Remove the `--timestamp` flag from build script (already handled)
- For Developer ID: Ensure keychain is unlocked and certificate is imported correctly
- Check: `security find-identity -v -p codesigning`

### Signing fails on Linux
- Ensure `debsigs` is installed: `apt-get install debsigs`
- Check GPG key import: `gpg --list-keys`
- Verify key has signing capability: `gpg --list-secret-keys --with-colons`

### Windows SmartScreen still warns
- Self-signed certificates will still show warnings (expected)
- Use a code signing certificate from a trusted CA to avoid warnings
- Users can click "More info" → "Run anyway" if they trust your app

## Scripts Reference

### `generate-signing-certs.ps1` (Windows PowerShell)
Generates Windows code signing certificate using PowerShell's built-in crypto APIs.
Requires: Windows 10+, PowerShell 5.0+

### `generate-signing-certs.sh` (macOS/Linux Bash)
Generates all three certificate types using OpenSSL and GPG.
Requires: bash, openssl, gpg

### Build Scripts with Signing Support
- `build_windows_installer.ps1` - Signs via `signtool.exe` and Inno Setup
- `build_macos_installer.sh` - Signs binaries and package
- `build_linux_package.sh` - Signs package with `debsigs`

All scripts are idempotent and gracefully skip signing if secrets are not provided.
