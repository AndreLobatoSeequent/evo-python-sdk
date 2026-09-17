#!/usr/bin/env bash
# Builds a .deb package for evo-cli.
#
# By default this runs build_pyinstaller.sh first. Pass --skip-pyinstaller-build
# to package an already-built dist/pyinstaller/evo directory instead.
#
# Optional signing: set LINUX_GPG_SIGNING_KEY (path to GPG key or GPG key ID)
# to sign the .deb package. When unset, an unsigned package is built.
#
# Requires dpkg-deb (preinstalled on Debian/Ubuntu) and optionally gpg for signing.
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
ARCH="amd64"

INSTALL_LOCATION="/usr/lib/evo-cli"
STAGE_DIR="$(mktemp -d)"
mkdir -p "$STAGE_DIR$INSTALL_LOCATION"
cp -R "$DIST_DIR"/. "$STAGE_DIR$INSTALL_LOCATION"/

mkdir -p "$STAGE_DIR/usr/bin"
ln -sf "$INSTALL_LOCATION/evo" "$STAGE_DIR/usr/bin/evo"

DESCRIPTION="$(uv run --no-project python3 -c "
import tomllib, sys
with open(sys.argv[1], 'rb') as f:
    print(tomllib.load(f)['project']['description'])
" "$PACKAGE_DIR/pyproject.toml")"

mkdir -p "$STAGE_DIR/DEBIAN"
sed \
    -e "s/{{VERSION}}/$VERSION/" \
    -e "s/{{DESCRIPTION}}/$DESCRIPTION/" \
    "$PACKAGE_DIR/installer/linux/control.template" > "$STAGE_DIR/DEBIAN/control"

mkdir -p "$REPO_ROOT/release"
OUTPUT_DEB="$REPO_ROOT/release/evo-cli_${VERSION}_${ARCH}.deb"
dpkg-deb --root-owner-group --build "$STAGE_DIR" "$OUTPUT_DEB"

# Sign the package if GPG key is provided
if [ -n "${LINUX_GPG_SIGNING_KEY:-}" ]; then
    if command -v gpg &> /dev/null; then
        echo "Importing GPG signing key"
        echo "$LINUX_GPG_SIGNING_KEY" | gpg --import --batch 2>/dev/null || true

        if command -v debsigs &> /dev/null; then
            echo "Signing .deb package with GPG"
            # Use the key ID if provided, otherwise default key will be used
            if [ -n "${LINUX_GPG_SIGNING_KEY_ID:-}" ]; then
                debsigs --sign=origin -k "$LINUX_GPG_SIGNING_KEY_ID" "$OUTPUT_DEB" || {
                    echo "WARNING: debsigs signing failed, package is unsigned" >&2
                }
            else
                debsigs --sign=origin "$OUTPUT_DEB" || {
                    echo "WARNING: debsigs signing failed, package is unsigned" >&2
                }
            fi
        else
            echo "WARNING: debsigs not found; .deb will be unsigned. Install: sudo apt-get install debsigs" >&2
        fi
    else
        echo "WARNING: gpg not found; .deb will be unsigned."
    fi
else
    echo "LINUX_GPG_SIGNING_KEY not set; building an unsigned package."
fi

sha256sum "$OUTPUT_DEB" | awk '{print $1}' > "$OUTPUT_DEB.sha256"

echo "Linux package built: $OUTPUT_DEB"
