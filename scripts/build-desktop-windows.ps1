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
    } else {
        Write-Host "==> refresh bundled sidecar python (incremental)"
    }

    $py = Join-Path $BundleVenv "python.exe"

    & $py -m ensurepip --upgrade 2>$null
    & $py -m pip install -U pip
    & $py -m pip install --no-cache-dir `
        (Join-Path $RootDir "shared") `
        (Join-Path $RootDir "host") `
        (Join-Path $RootDir "agent") `
        (Join-Path $RootDir "sidecar")

    Write-Host "==> prune bundle python (drop pip tooling, bytecode cache)"
    & $py -m pip uninstall -y pip setuptools wheel 2>$null

    Get-ChildItem -Path $BundleVenv -Recurse -Directory -Filter "__pycache__" |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    Write-Host "==> verify bundled sidecar import"
    & $py -c "import agentpod, agentpod_host, agentpod_agent, agentpod_shared"

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

Write-Host "==> build AgentPod Windows installer (Tauri, cargo may take a few minutes)"
Set-Location (Join-Path $RootDir "desktop")
npm ci

if (-not (Test-Path "src-tauri/icons/icon.ico")) {
    Write-Host "==> generate Windows icon from icon.png"
    npx tauri icon src-tauri/icons/icon.png
}

npm run build -- --bundles nsis

$nsisDir = Join-Path $RootDir "desktop/src-tauri/target/release/bundle/nsis"
$setupExe = Get-ChildItem -Path $nsisDir -Filter "*setup.exe" -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $setupExe) {
    throw "NSIS setup.exe not found under $nsisDir"
}

$distDir = Join-Path $RootDir "dist"
if (Test-Path $distDir) {
    Get-ChildItem -Path $distDir -Filter "AgentPod_*_windows-x64.exe" -ErrorAction SilentlyContinue |
        Remove-Item -Force
}
New-Item -ItemType Directory -Force -Path $distDir | Out-Null

$outName = "AgentPod_${Version}_windows-x64.exe"
$outPath = Join-Path $distDir $outName
Copy-Item -Path $setupExe.FullName -Destination $outPath -Force

Write-Host "==> done: $outPath"
Get-ChildItem $distDir
