#!/usr/bin/env bash
# Generates self-signed certificates for all native installers (Windows, macOS, Linux).
# For development/testing purposes only.
#
# Creates:
#   - Windows code signing cert (.pfx)
#   - macOS application & installer signing certs (.p12)
#   - Linux GPG signing key
#
# All outputs are base64-encoded for easy copy-paste into GitHub secrets.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/.certs"
CERT_PASSWORD="${CERT_PASSWORD:-EvoCLI@Dev2024}"
CERT_ORG="${CERT_ORG:-Seequent}"
CERT_EMAIL="${CERT_EMAIL:-support@seequent.com}"

mkdir -p "$OUTPUT_DIR"
cd "$OUTPUT_DIR"

echo "=== Generating self-signed certificates for evo-cli ==="
echo "Output directory: $OUTPUT_DIR"
echo "Certificate password: $CERT_PASSWORD"
echo "Organization: $CERT_ORG"
echo ""

# ============================================================================
# Windows Code Signing Certificate
# ============================================================================
echo "[1/3] Generating Windows code signing certificate..."

if [ -f "windows-signing.pfx" ]; then
    echo "  ✓ windows-signing.pfx already exists, skipping"
else
    # Create a private key and self-signed certificate
    openssl genrsa -out windows-signing.key 2048
    openssl req -new -x509 -key windows-signing.key -out windows-signing.crt \
        -days 1825 \
        -subj "/CN=$CERT_ORG/O=$CERT_ORG/C=US" \
        -addext "extendedKeyUsage=codeSigning"

    # Convert to PKCS#12 (.pfx) format
    openssl pkcs12 -export -out windows-signing.pfx \
        -inkey windows-signing.key -in windows-signing.crt \
        -name "$CERT_ORG" \
        -passout pass:"$CERT_PASSWORD"

    rm windows-signing.key windows-signing.crt
    echo "  ✓ windows-signing.pfx created"
fi

# ============================================================================
# macOS Signing Certificates
# ============================================================================
echo "[2/3] Generating macOS code signing certificates..."

if [ -f "macos-app-signing.p12" ] && [ -f "macos-installer-signing.p12" ]; then
    echo "  ✓ macOS certs already exist, skipping"
else
    # Application signing certificate
    openssl genrsa -out macos-app.key 2048
    openssl req -new -x509 -key macos-app.key -out macos-app.crt \
        -days 1825 \
        -subj "/CN=$CERT_ORG Application/O=$CERT_ORG/C=US" \
        -addext "extendedKeyUsage=codeSigning"

    openssl pkcs12 -export -out macos-app-signing.p12 \
        -inkey macos-app.key -in macos-app.crt \
        -name "$CERT_ORG Application" \
        -passout pass:"$CERT_PASSWORD"

    # Installer signing certificate
    openssl genrsa -out macos-installer.key 2048
    openssl req -new -x509 -key macos-installer.key -out macos-installer.crt \
        -days 1825 \
        -subj "/CN=$CERT_ORG Installer/O=$CERT_ORG/C=US" \
        -addext "extendedKeyUsage=codeSigning"

    openssl pkcs12 -export -out macos-installer-signing.p12 \
        -inkey macos-installer.key -in macos-installer.crt \
        -name "$CERT_ORG Installer" \
        -passout pass:"$CERT_PASSWORD"

    rm macos-app.key macos-app.crt macos-installer.key macos-installer.crt
    echo "  ✓ macos-app-signing.p12 created"
    echo "  ✓ macos-installer-signing.p12 created"
fi

# ============================================================================
# Linux GPG Signing Key
# ============================================================================
echo "[3/3] Generating Linux GPG signing key..."

if [ -f "linux-signing.gpg" ]; then
    echo "  ✓ linux-signing.gpg already exists, skipping"
else
    # Create GPG key batch file for non-interactive key generation
    cat > gpg-batch.txt <<EOF
%no-protection
Key-Type: RSA
Key-Length: 2048
Name-Real: $CERT_ORG
Name-Email: $CERT_EMAIL
Expire-Date: 1825d
EOF

    gpg --batch --generate-key gpg-batch.txt 2>&1 | grep -i "key\|error" || true
    rm gpg-batch.txt

    # Export the key
    gpg --output linux-signing.gpg --armor --export-secret-keys "$CERT_ORG" || {
        echo "  ✗ Failed to export GPG key. Make sure '$CERT_ORG' key was created."
        exit 1
    }
    echo "  ✓ linux-signing.gpg created"
fi

# ============================================================================
# Encode certificates to base64 for GitHub secrets
# ============================================================================
echo ""
echo "=== Generating base64-encoded secrets for GitHub ==="
echo ""

# Windows
echo "WINDOWS_CODE_SIGNING_CERT:"
base64 -w 0 windows-signing.pfx > windows-cert.b64
cat windows-cert.b64
echo ""
echo ""

# macOS Application
echo "APPLE_CERTIFICATE (Application - use for binary signing):"
base64 -w 0 macos-app-signing.p12 > macos-app-cert.b64
cat macos-app-cert.b64
echo ""
echo ""

# macOS Installer
echo "macos-installer-signing.p12 was also generated, but publish-evo-cli.yaml"
echo "only imports APPLE_CERTIFICATE (the application cert) into the CI keychain,"
echo "so APPLE_INSTALLER_SIGNING_IDENTITY should reuse that same identity below"
echo "unless you add a matching import step for the installer cert."
echo ""
echo ""

# Linux GPG (armor format, already text-based)
echo "LINUX_GPG_SIGNING_KEY:"
cat linux-signing.gpg
echo ""
echo ""

# Summary
echo "=== Summary ==="
echo "✓ Organization: $CERT_ORG"
echo "✓ Certificate password: $CERT_PASSWORD"
echo ""
echo "GitHub Secrets to add:"
echo "  WINDOWS_CODE_SIGNING_CERT         → $(cat windows-cert.b64 | cut -c1-50)..."
echo "  WINDOWS_CODE_SIGNING_PASSWORD     → $CERT_PASSWORD"
echo "  APPLE_CERTIFICATE                 → $(cat macos-app-cert.b64 | cut -c1-50)..."
echo "  APPLE_CERTIFICATE_PASSWORD        → $CERT_PASSWORD"
echo "  APPLE_SIGNING_IDENTITY            → $CERT_ORG Application  (no quotes)"
echo "  APPLE_INSTALLER_SIGNING_IDENTITY  → $CERT_ORG Application  (no quotes; reuses the same imported cert)"
echo "  LINUX_GPG_SIGNING_KEY             → (see output above)"
echo "  LINUX_GPG_SIGNING_KEY_ID          → $(gpg --list-keys --with-colons "$CERT_ORG" 2>/dev/null | grep fpr | cut -d: -f10 | head -1)"
echo ""
echo "All certificate files are in: $OUTPUT_DIR"
echo ""
echo "NOTE: To customize, set CERT_ORG and CERT_EMAIL environment variables before running:"
echo "  CERT_ORG=\"My Company\" CERT_EMAIL=\"me@example.com\" bash generate-signing-certs.sh"
echo ""
