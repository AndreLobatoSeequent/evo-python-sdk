#!/usr/bin/env pwsh
# Builds a PyInstaller onedir distribution of evo-cli for Windows.
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
# console attached (--console). PyInstaller's --noconsole/--windowed flag
# detaches stdio, which would break `evo`'s prompts, piping, and any command
# that reads stdin.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$PackageDir = Join-Path $RepoRoot "packages\evo-cli"

Push-Location $RepoRoot
try {
    $outputDir = "dist/pyinstaller"
    $workDir = "build/pyinstaller"
    $buildVenv = ".venv-pyinstaller-build"
    foreach ($dir in @($outputDir, $workDir)) {
        if (Test-Path $dir) {
            Write-Host "Removing existing $dir"
            Remove-Item -Recurse -Force $dir
        }
    }

    Write-Host "Building evo-cli wheel..."
    uv build --package evo-cli
    if ($LASTEXITCODE -ne 0) { throw "uv build failed" }

    $wheel = Get-ChildItem "dist" -Filter "evo_cli-*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $wheel) { throw "No evo-cli wheel found in dist/" }

    Write-Host "Installing $($wheel.Name) and PyInstaller into a clean virtual environment..."
    uv venv --clear $buildVenv
    if ($LASTEXITCODE -ne 0) { throw "Failed to create build venv" }

    uv pip install --python "$buildVenv\Scripts\python.exe" $wheel.FullName "pyinstaller>=6.11" "pyinstaller-hooks-contrib>=2024.10"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install evo-cli/PyInstaller into build venv" }

    Write-Host "Building evo-cli onedir distribution with PyInstaller..."
    # --optimize 2 (-OO) strips docstrings, which Typer/Click use as command help text
    # for commands that don't set help= explicitly - that broke `--help` output for
    # subcommands in the frozen build. --optimize 1 (-O) still strips asserts but
    # keeps docstrings intact.
    & "$buildVenv\Scripts\pyinstaller.exe" `
        --onedir `
        --optimize 1 `
        --console `
        --name evo `
        --distpath $outputDir `
        --workpath $workDir `
        --specpath $workDir `
        --noconfirm `
        --collect-submodules keyring.backends `
        --copy-metadata evo-cli `
        --copy-metadata evo-sdk-common `
        --copy-metadata evo-blockmodels `
        --copy-metadata evo-compute `
        --copy-metadata evo-objects `
        --copy-metadata evo-files `
        --exclude-module setuptools `
        --exclude-module pkg_resources `
        --exclude-module _distutils_hack `
        --exclude-module pyarrow.flight --exclude-module pyarrow._flight `
        --exclude-module pyarrow.dataset --exclude-module pyarrow._dataset `
        --exclude-module pyarrow.substrait --exclude-module pyarrow._substrait `
        --exclude-module pyarrow.acero --exclude-module pyarrow._acero `
        --additional-hooks-dir (Join-Path $PackageDir "pyinstaller-hooks") `
        packages/evo-cli/src/evo/cli/__main__.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

    $distDir = Join-Path $outputDir "evo"
    $exePath = Join-Path $distDir "evo.exe"
    if (-not (Test-Path $exePath)) { throw "Expected binary not found at $exePath" }

    Write-Host "Smoke testing $exePath --help"
    & $exePath --help
    if ($LASTEXITCODE -ne 0) { throw "Smoke test failed: evo --help exited with $LASTEXITCODE" }

    Write-Host "PyInstaller onedir build succeeded: $distDir"
}
finally {
    Pop-Location
}
