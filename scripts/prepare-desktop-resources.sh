#!/usr/bin/env bash
# 为 Tauri 构建准备 resources/（shared-skills；完整 venv 由 rebuild.sh desktop 生成）
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RES="$ROOT_DIR/desktop/src-tauri/resources"
mkdir -p "$RES"
rm -rf "$RES/shared-skills"
cp -R "$ROOT_DIR/shared-skills" "$RES/shared-skills"
if [[ ! -x "$RES/sidecar-venv/bin/python" ]]; then
  mkdir -p "$RES/sidecar-venv/bin"
  if [[ -x "$ROOT_DIR/sidecar/.venv/bin/python" ]]; then
    echo "hint: run ./rebuild.sh desktop to bundle sidecar-venv for release"
    ln -sf "$ROOT_DIR/sidecar/.venv" "$RES/sidecar-venv-link" 2>/dev/null || true
  fi
  # Tauri 构建前需存在目录；release 构建会由 rebuild.sh desktop 填充真实 venv
  mkdir -p "$RES/sidecar-venv/bin"
  cat > "$RES/sidecar-venv/bin/python" <<'STUB'
#!/bin/sh
echo "bundled sidecar venv missing; run ./rebuild.sh desktop" >&2
exit 1
STUB
  chmod +x "$RES/sidecar-venv/bin/python"
fi
