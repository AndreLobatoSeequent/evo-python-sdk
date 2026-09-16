#!/usr/bin/env bash
# Builds a PyInstaller onedir distribution of evo-cli for macOS or Linux.
#
# Builds evo-cli's wheel and installs it (plus PyInstaller itself) into a
# throwaway virtual environment, rather than freezing from the shared
# workspace .venv. The workspace venv accumulates dependencies from every
# package's dev/notebooks extras (e.g. evo-sdk-common[notebooks] pulls in
# IPython/Jupyter), and PyInstaller bundles anything merely *importable* in
# its build environment that some optional/guarded code path references -
# not just what evo-cli actually needs. Freezing from a clean, wheel-only
# install keeps the frozen binary scoped to evo-cli's real dependency
# graph. This cut a real build from 230 MB / 3077 modules down to roughly
# 130 MB / 1900 modules.
#
# Note: evo-cli is an interactive CLI, so the build intentionally keeps a
# console attached (--console). PyInstaller's --windowed/--noconsole flag is
# a no-op for --onedir on Linux and produces a GUI .app bundle on macOS,
# either of which would break `evo`'s stdio-based interaction, so it is
# deliberately not used here.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PACKAGE_DIR="$REPO_ROOT/packages/evo-cli"
cd "$REPO_ROOT"

OUTPUT_DIR="dist/pyinstaller"
WORK_DIR="build/pyinstaller"
BUILD_VENV=".venv-pyinstaller-build"
for dir in "$OUTPUT_DIR" "$WORK_DIR"; do
    if [ -d "$dir" ]; then
        echo "Removing existing $dir"
        rm -rf "$dir"
    fi
done

echo "Building evo-cli wheel..."
uv build --package evo-cli

wheel="$(ls -t dist/evo_cli-*.whl | head -n1)"
if [ -z "$wheel" ]; then
    echo "No evo-cli wheel found in dist/" >&2
    exit 1
fi

echo "Installing $(basename "$wheel") and PyInstaller into a clean virtual environment..."
uv venv --clear "$BUILD_VENV"
uv pip install --python "$BUILD_VENV/bin/python" "$wheel" "pyinstaller>=6.11" "pyinstaller-hooks-contrib>=2024.10"

echo "Building evo-cli onedir distribution with PyInstaller..."
"$BUILD_VENV/bin/pyinstaller" \
    --onedir \
    --optimize 2 \
    --console \
    --name evo \
    --distpath "$OUTPUT_DIR" \
    --workpath "$WORK_DIR" \
    --specpath "$WORK_DIR" \
    --noconfirm \
    --collect-submodules keyring.backends \
    --exclude-module setuptools \
    --exclude-module pkg_resources \
    --exclude-module _distutils_hack \
    --exclude-module pyarrow.flight --exclude-module pyarrow._flight \
    --exclude-module pyarrow.dataset --exclude-module pyarrow._dataset \
    --exclude-module pyarrow.substrait --exclude-module pyarrow._substrait \
    --exclude-module pyarrow.acero --exclude-module pyarrow._acero \
    --additional-hooks-dir "$PACKAGE_DIR/pyinstaller-hooks" \
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
