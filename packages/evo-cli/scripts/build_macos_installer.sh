#!/usr/bin/env bash
# Builds a macOS .pkg installer for evo-cli.
#
# By default this runs build_pyinstaller.sh first. Pass --skip-pyinstaller-build
# to package an already-built dist/pyinstaller/evo directory instead.
#
# Optional signing/notarization (skipped with a warning when unset):
#   APPLE_SIGNING_IDENTITY            codesign identity for binaries/dylibs
#   APPLE_INSTALLER_SIGNING_IDENTITY  productsign identity for the .pkg
#   APPLE_ID, APPLE_TEAM_ID, APPLE_APP_SPECIFIC_PASSWORD
#                                      notarytool credentials (all three
#                                      required to notarize/staple)
set -euo pipefail

SKIP_PYINSTALLER_BUILD=0
for arg in "$@"; do
    case "$arg" in
        --skip-pyinstaller-build) SKIP_PYINSTALLER_BUILD=1 ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PACKAGE_DIR="$REPO_ROOT/packages/evo-cli"
cd "$REPO_ROOT"

if [ "$SKIP_PYINSTALLER_BUILD" -eq 0 ]; then
    bash "$SCRIPT_DIR/build_pyinstaller.sh"
fi

DIST_DIR="$REPO_ROOT/dist/pyinstaller/evo"
if [ ! -d "$DIST_DIR" ]; then
    echo "PyInstaller dist not found at $DIST_DIR. Run build_pyinstaller.sh first (or omit --skip-pyinstaller-build)." >&2
    exit 1
fi

VERSION="$(uv version --short --package evo-cli)"
case "$(uname -m)" in
    arm64) PKG_ARCH="arm64" ;;
    x86_64) PKG_ARCH="x64" ;;
    *)
        echo "Unsupported architecture: $(uname -m)" >&2
        exit 1
        ;;
esac

INSTALL_LOCATION="/usr/local/lib/evo-cli"
STAGE_DIR="$(mktemp -d)"
STAGE_INSTALL_DIR="$STAGE_DIR/payload"
mkdir -p "$STAGE_INSTALL_DIR"
cp -R "$DIST_DIR"/. "$STAGE_INSTALL_DIR"/

SCRIPTS_DIR="$(mktemp -d)"
cat > "$SCRIPTS_DIR/postinstall" <<'EOF'
#!/bin/bash
set -e
mkdir -p /usr/local/bin
ln -sf /usr/local/lib/evo-cli/evo /usr/local/bin/evo
exit 0
EOF
chmod +x "$SCRIPTS_DIR/postinstall"

if [ -n "${APPLE_SIGNING_IDENTITY:-}" ]; then
    echo "Codesigning binaries with identity: $APPLE_SIGNING_IDENTITY"
    while IFS= read -r -d '' f; do
        codesign --force --options runtime --timestamp --sign "$APPLE_SIGNING_IDENTITY" "$f"
    done < <(find "$STAGE_INSTALL_DIR" -type f \( -perm -u+x -o -name "*.dylib" -o -name "*.so" \) -print0)
else
    echo "WARNING: APPLE_SIGNING_IDENTITY not set; building an unsigned package." >&2
fi

mkdir -p "$REPO_ROOT/release"
COMPONENT_PKG="$STAGE_DIR/evo-cli-component.pkg"
# --root points at just the payload; --install-location names the target
# path separately, so pkgbuild creates the intermediate directories
# (/usr, /usr/local, /usr/local/lib) at install time without adding them to
# the package's file manifest. Baking the full path into --root instead
# (with --install-location /) makes pkgbuild record /usr itself as an
# owned entry, which the installer rejects as writing to the sealed,
# read-only system volume ("attempting to install content to the system
# volume"), even though /usr/local is actually on the writable data volume.
pkgbuild \
    --root "$STAGE_INSTALL_DIR" \
    --scripts "$SCRIPTS_DIR" \
    --identifier com.seequent.evo-cli \
    --version "$VERSION" \
    --install-location "$INSTALL_LOCATION" \
    "$COMPONENT_PKG"

OUTPUT_PKG="$REPO_ROOT/release/evo-cli-$VERSION-macos-$PKG_ARCH.pkg"

if [ -n "${APPLE_INSTALLER_SIGNING_IDENTITY:-}" ]; then
    productsign --sign "$APPLE_INSTALLER_SIGNING_IDENTITY" "$COMPONENT_PKG" "$OUTPUT_PKG"
else
    cp "$COMPONENT_PKG" "$OUTPUT_PKG"
fi

if [ -n "${APPLE_ID:-}" ] && [ -n "${APPLE_TEAM_ID:-}" ] && [ -n "${APPLE_APP_SPECIFIC_PASSWORD:-}" ]; then
    echo "Notarizing $OUTPUT_PKG"
    xcrun notarytool submit "$OUTPUT_PKG" \
        --apple-id "$APPLE_ID" \
        --team-id "$APPLE_TEAM_ID" \
        --password "$APPLE_APP_SPECIFIC_PASSWORD" \
        --wait
    xcrun stapler staple "$OUTPUT_PKG"
else
    echo "WARNING: Apple notarization credentials not set; skipping notarization." >&2
fi

shasum -a 256 "$OUTPUT_PKG" | awk '{print $1}' > "$OUTPUT_PKG.sha256"

echo "macOS package built: $OUTPUT_PKG"
