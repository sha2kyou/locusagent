# 解析 uv 安装的 python-build-standalone 根目录（install_only_stripped）。
$ErrorActionPreference = "Stop"

uv python install 3.11 --reinstall | Out-Null

$installDir = if ($env:UV_PYTHON_INSTALL_DIR) {
    $env:UV_PYTHON_INSTALL_DIR
} else {
    Join-Path $env:LOCALAPPDATA "uv/python"
}

$pyExe = & uv python find --managed-python 3.11 2>$null
if ($pyExe -and (Test-Path $pyExe)) {
    Write-Output (Split-Path $pyExe -Parent)
    exit 0
}

$standalone = Get-ChildItem -Path $installDir -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^cpython-3\.11(\.\d+)?-windows-x86_64-none$' } |
    Sort-Object Name |
    Select-Object -Last 1

if (-not $standalone -or -not (Test-Path (Join-Path $standalone.FullName "python.exe"))) {
    throw "uv managed python 3.11 (x64) not found under $installDir"
}

Write-Output $standalone.FullName
