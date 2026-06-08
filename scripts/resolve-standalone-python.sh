#!/usr/bin/env bash
# 解析 uv 安装的 python-build-standalone 根目录（install_only_stripped）。
set -euo pipefail

uv python install 3.11 >/dev/null

install_dir="${UV_PYTHON_INSTALL_DIR:-${HOME}/.local/share/uv/python}"
latest="$(find "$install_dir" -maxdepth 1 -type d -name 'cpython-3.11*-macos-aarch64-none' 2>/dev/null | sort -V | tail -1)"

if [[ -z "$latest" || ! -x "$latest/bin/python3.11" ]]; then
  echo "error: uv managed python 3.11 (aarch64) not found under $install_dir" >&2
  exit 1
fi

printf '%s\n' "$latest"
