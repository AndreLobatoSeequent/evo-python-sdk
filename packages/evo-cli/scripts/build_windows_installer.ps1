#!/usr/bin/env pwsh
# Builds the signed (if configured) Windows installer for evo-cli using Inno Setup.
#
# By default this runs build_pyinstaller.ps1 first. Pass -SkipPyInstallerBuild
# to package an already-built dist/pyinstaller/evo directory instead.
#
# Optional signing: set WINDOWS_CODE_SIGNING_CERT_PATH (path to a .pfx file)
# and WINDOWS_CODE_SIGNING_PASSWORD to sign the installer and uninstaller.
# When unset, an unsigned installer is built.

[CmdletBinding()]
param(
    [switch]$SkipPyInstallerBuild
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$PackageDir = Join-Path $RepoRoot "packages\evo-cli"

if (-not $SkipPyInstallerBuild) {
    & (Join-Path $PSScriptRoot "build_pyinstaller.ps1")
}

Push-Location $RepoRoot
try {
    $distDir = Join-Path $RepoRoot "dist\pyinstaller\evo"
    if (-not (Test-Path $distDir)) {
        throw "PyInstaller dist not found at $distDir. Run build_pyinstaller.ps1 first (or omit -SkipPyInstallerBuild)."
    }

    $iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($iscc) {
        $isccPath = $iscc.Source
    }
    else {
        # Inno Setup's installer defaults to a per-user install under
        # %LOCALAPPDATA%\Programs when run without admin rights, rather than
        # Program Files - check both, across the versions we've seen in use.
        $candidates = foreach ($version in @("6", "7")) {
            "${env:ProgramFiles(x86)}\Inno Setup $version\ISCC.exe"
            "${env:ProgramFiles}\Inno Setup $version\ISCC.exe"
            "${env:LOCALAPPDATA}\Programs\Inno Setup $version\ISCC.exe"
        }
        $isccPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $isccPath) {
        throw "ISCC.exe (Inno Setup Compiler) not found. Install Inno Setup from https://jrsoftware.org/isdl.php and ensure ISCC.exe is on PATH."
    }

    $version = (uv version --short --package evo-cli).Trim()
    New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "release") | Out-Null

    $isccArgs = @(
        "/DAppVersion=$version",
        "/DSourceDir=$distDir"
    )

    if ($env:WINDOWS_CODE_SIGNING_CERT_PATH -and $env:WINDOWS_CODE_SIGNING_PASSWORD) {
        Write-Host "Signing certificate found; installer and uninstaller will be signed."

        # signtool.exe ships with the Windows SDK under Windows Kits\10\bin\<ver>\x64
        # which is NOT on PATH by default on GitHub-hosted windows-latest runners.
        # Inno Setup launches the sign command via CreateProcess, which fails with
        # "Error 2: The system cannot find the file specified" if it can't resolve
        # a bare "signtool.exe" - so we must resolve and embed the full path.
        $signtoolCmd = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
        if ($signtoolCmd) {
            $signtoolPath = $signtoolCmd.Source
        }
        else {
            $signtoolPath = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
        }
        if (-not $signtoolPath) {
            throw "signtool.exe not found. Install the Windows SDK (Windows Kits\10\bin\<version>\x64\signtool.exe) or ensure it's on PATH."
        }

        # Use Inno Setup's own $q (literal double-quote) and $f (file to sign)
        # placeholders instead of embedding real quotes here. Real quotes get
        # mangled when PowerShell re-quotes this whole argument for ISCC.exe,
        # which then re-quotes it again to invoke signtool.exe - each layer of
        # quoting corrupts the nested quotes. $q sidesteps that entirely: it's
        # plain text until Inno Setup itself substitutes it for a real quote
        # right before invoking signtool.
        $signCommand = '$q' + $signtoolPath + '$q sign /f $q' + $env:WINDOWS_CODE_SIGNING_CERT_PATH + '$q /p $q' + $env:WINDOWS_CODE_SIGNING_PASSWORD + '$q /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $f'
        $isccArgs += "/DSIGN=1"
        $isccArgs += "/Ssigntool=$signCommand"
    }
    else {
        Write-Warning "WINDOWS_CODE_SIGNING_CERT_PATH/WINDOWS_CODE_SIGNING_PASSWORD not set; building an unsigned installer."
    }

    $isccArgs += (Join-Path $PackageDir "installer\windows.iss")

    & $isccPath @isccArgs
    if ($LASTEXITCODE -ne 0) { throw "ISCC.exe failed" }

    $expected = Join-Path $RepoRoot "release\evo-cli-$version-setup-windows-x64.exe"
    if (-not (Test-Path $expected)) { throw "Expected installer not found at $expected" }

    (Get-FileHash -Algorithm SHA256 $expected).Hash.ToLower() | Out-File -Encoding ascii -NoNewline "$expected.sha256"
    Write-Host "Windows installer built: $expected"
}
finally {
    Pop-Location
}
