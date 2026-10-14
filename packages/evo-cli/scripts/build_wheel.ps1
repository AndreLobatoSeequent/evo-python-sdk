#!/usr/bin/env pwsh
# Builds the evo-cli wheel and validates it in a clean virtual environment.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")

Push-Location $RepoRoot
try {
    Write-Host "Building evo-cli wheel..."
    uv build --package evo-cli
    if ($LASTEXITCODE -ne 0) { throw "uv build failed" }

    $wheel = Get-ChildItem "dist" -Filter "evo_cli-*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $wheel) { throw "No evo-cli wheel found in dist/" }

    Write-Host "Validating $($wheel.Name) in a clean virtual environment..."
    uv venv --clear .venv-wheel-test
    if ($LASTEXITCODE -ne 0) { throw "Failed to create validation venv" }

    uv pip install --python ".venv-wheel-test\Scripts\python.exe" $wheel.FullName
    if ($LASTEXITCODE -ne 0) { throw "Failed to install wheel into validation venv" }

    & ".venv-wheel-test\Scripts\evo.exe" --help
    if ($LASTEXITCODE -ne 0) { throw "evo --help failed in validation venv" }

    Write-Host "Wheel build and validation succeeded: $($wheel.Name)"
}
finally {
    Pop-Location
}
