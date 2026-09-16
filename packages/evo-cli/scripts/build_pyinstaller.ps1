#!/usr/bin/env pwsh
# Builds a PyInstaller onedir distribution of evo-cli for Windows.
#
# Requires the `build-pyinstaller` dependency group (installed on demand via
# `uv run --group build-pyinstaller`).
#
# Note: evo-cli is an interactive CLI, so the build intentionally keeps a
# console attached (--console). PyInstaller's --noconsole/--windowed flag
# detaches stdio, which would break `evo`'s prompts, piping, and any command
# that reads stdin.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")

Push-Location $RepoRoot
try {
    $outputDir = "dist/pyinstaller"
    $workDir = "build/pyinstaller"
    foreach ($dir in @($outputDir, $workDir)) {
        if (Test-Path $dir) {
            Write-Host "Removing existing $dir"
            Remove-Item -Recurse -Force $dir
        }
    }

    Write-Host "Building evo-cli onedir distribution with PyInstaller..."
    uv run --package evo-cli --group build-pyinstaller pyinstaller `
        --onedir `
        --optimize 2 `
        --console `
        --name evo `
        --distpath $outputDir `
        --workpath $workDir `
        --specpath $workDir `
        --noconfirm `
        --collect-submodules keyring.backends `
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
