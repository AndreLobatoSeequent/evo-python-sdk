#!/usr/bin/env bash
# Builds a PyInstaller onedir distribution of evo-cli for macOS or Linux.
#
# Requires the `build-pyinstaller` dependency group (installed on demand via
# `uv run --group build-pyinstaller`).
#
# Note: evo-cli is an interactive CLI, so the build intentionally keeps a
# console attached (--console). PyInstaller's --windowed/--noconsole flag is
# a no-op for --onedir on Linux and produces a GUI .app bundle on macOS,
# either of which would break `evo`'s stdio-based interaction, so it is
# deliberately not used here.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

OUTPUT_DIR="dist/pyinstaller"
WORK_DIR="build/pyinstaller"
for dir in "$OUTPUT_DIR" "$WORK_DIR"; do
    if [ -d "$dir" ]; then
        echo "Removing existing $dir"
        rm -rf "$dir"
    fi
done

echo "Building evo-cli onedir distribution with PyInstaller..."
uv run --package evo-cli --group build-pyinstaller pyinstaller \
    --onedir \
    --optimize 2 \
    --console \
    --name evo \
    --distpath "$OUTPUT_DIR" \
    --workpath "$WORK_DIR" \
    --specpath "$WORK_DIR" \
    --noconfirm \
    --collect-submodules keyring.backends \
    packages/evo-cli/src/evo/cli/__main__.py

DIST_DIR="$OUTPUT_DIR/evo"
EXE_PATH="$DIST_DIR/evo"
if [ ! -f "$EXE_PATH" ]; then
    echo "Expected binary not found at $EXE_PATH" >&2
    exit 1
fi

echo "Smoke testing $EXE_PATH --help"
"$EXE_PATH" --help

echo "PyInstaller onedir build succeeded: $DIST_DIR"
