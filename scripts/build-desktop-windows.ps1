param(
    [switch]$FreshVenv
)

$ErrorActionPreference = "Stop"
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RootDir

uv run python scripts/sync-version.py

$Version = (Get-Content VERSION -Raw).Trim()
$BundleRoot = Join-Path $RootDir "desktop/src-tauri/resources"
$BundleVenv = Join-Path $BundleRoot "sidecar-venv"

function Assert-LastExitCode {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

function Remove-ExternallyManagedMarker {
    param([string]$Root)
    $knownPaths = @(
        (Join-Path $Root "Lib\EXTERNALLY-MANAGED"),
        (Join-Path $Root "lib\python3.11\EXTERNALLY-MANAGED")
    )
    foreach ($path in $knownPaths) {
        if (Test-Path $path) {
            Set-ItemProperty -LiteralPath $path -Name IsReadOnly -Value $false
            Remove-Item -LiteralPath $path -Force
        }
    }
    Get-ChildItem -Path $Root -Recurse -File -Filter "EXTERNALLY-MANAGED" -ErrorAction SilentlyContinue |
        ForEach-Object {
            $_.IsReadOnly = $false
            Remove-Item -LiteralPath $_.FullName -Force
        }
}

function Invoke-BundledPip {
    param(
        [string]$Python,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$PipArgs
    )
    $allArgs = $PipArgs + @("--break-system-packages")
    & $Python -m pip @allArgs
    Assert-LastExitCode ("pip " + ($PipArgs -join " "))
}

function Setup-BundleResources {
    param([bool]$Fresh)

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv required for desktop bundle (https://docs.astral.sh/uv/)"
    }

    $pyExe = Join-Path $BundleVenv "python.exe"
    if ($Fresh -or -not (Test-Path $pyExe)) {
        Write-Host "==> prepare bundled sidecar python (uv standalone 3.11, may take several minutes)"
        if (Test-Path $BundleVenv) {
            Remove-Item -Recurse -Force $BundleVenv
        }

        $standaloneRoot = & (Join-Path $PSScriptRoot "resolve-standalone-python.ps1")
        Write-Host "==> copy standalone python from $standaloneRoot"
        New-Item -ItemType Directory -Force -Path $BundleVenv | Out-Null
        Copy-Item -Path (Join-Path $standaloneRoot "*") -Destination $BundleVenv -Recurse -Force
        foreach ($required in @("python.exe", "Lib", "python311.dll")) {
            $path = Join-Path $BundleVenv $required
            if (-not (Test-Path $path)) {
                throw "bundled python incomplete after copy, missing: $required"
            }
        }
    } else {
        Write-Host "==> refresh bundled sidecar python (incremental)"
    }

    $py = Join-Path $BundleVenv "python.exe"

    Remove-ExternallyManagedMarker -Root $BundleVenv

    & $py -m ensurepip --upgrade 2>$null
    Invoke-BundledPip -Python $py install -U pip
    Invoke-BundledPip -Python $py install --no-cache-dir `
        (Join-Path $RootDir "shared") `
        (Join-Path $RootDir "host") `
        (Join-Path $RootDir "agent") `
        (Join-Path $RootDir "sidecar")

    Write-Host "==> prune bundle python (drop pip tooling, bytecode cache)"
    & $py -m pip uninstall -y pip setuptools wheel --break-system-packages 2>$null

    Get-ChildItem -Path $BundleVenv -Recurse -Directory -Filter "__pycache__" |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    Write-Host "==> verify bundled sidecar import"
    & $py -c "import locusagent, locus_host, locus_agent, locus_shared"
    Assert-LastExitCode "bundled sidecar import"

    Write-Host "==> copy shared-skills into bundle resources"
    $skillsDest = Join-Path $BundleRoot "shared-skills"
    if (Test-Path $skillsDest) {
        Remove-Item -Recurse -Force $skillsDest
    }
    Copy-Item -Path (Join-Path $RootDir "shared-skills") -Destination $skillsDest -Recurse
}

Setup-BundleResources -Fresh $FreshVenv.IsPresent

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    throw "Rust toolchain not found (cargo). Install from https://rustup.rs"
}

Write-Host "==> build desktop frontend (frontend/dist-desktop)"
Set-Location (Join-Path $RootDir "frontend")
npm ci
npm run build:desktop

Write-Host "==> build Locus Agent Windows installer (Tauri, cargo may take a few minutes)"
Set-Location (Join-Path $RootDir "desktop")
npm ci

Write-Host "==> generate Windows icons (icon.ico, tray PNGs)"
bash (Join-Path $RootDir "scripts/generate-windows-icons.sh")

npm run build -- --bundles nsis

$nsisDir = Join-Path $RootDir "desktop/src-tauri/target/release/bundle/nsis"
$setupExe = Get-ChildItem -Path $nsisDir -Filter "*setup.exe" -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $setupExe) {
    throw "NSIS setup.exe not found under $nsisDir"
}

$distDir = Join-Path $RootDir "dist"
if (Test-Path $distDir) {
    Get-ChildItem -Path $distDir -Filter "LocusAgent_*_windows-x64.exe" -ErrorAction SilentlyContinue |
        Remove-Item -Force
}
New-Item -ItemType Directory -Force -Path $distDir | Out-Null

$outName = "LocusAgent_${Version}_windows-x64.exe"
$outPath = Join-Path $distDir $outName
Copy-Item -Path $setupExe.FullName -Destination $outPath -Force

Write-Host "==> done: $outPath"
Get-ChildItem $distDir
