# 解析 uv 安装的 python-build-standalone 根目录（install_only_stripped）。
# 不使用 `uv python find`：构建前 `uv run` 会创建项目 .venv，find 会误返回 .venv\Scripts。
$ErrorActionPreference = "Stop"

uv python install 3.11 --reinstall | Out-Null

$installDir = if ($env:UV_PYTHON_INSTALL_DIR) {
    $env:UV_PYTHON_INSTALL_DIR
} else {
    Join-Path $env:LOCALAPPDATA "uv/python"
}

$standalone = Get-ChildItem -Path $installDir -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^cpython-3\.11(\.\d+)?-windows-x86_64-none$' } |
    Sort-Object Name |
    Select-Object -Last 1

if (-not $standalone -or -not (Test-Path (Join-Path $standalone.FullName "python.exe"))) {
    throw "uv managed python 3.11 (x64) not found under $installDir"
}

Write-Output $standalone.FullName
