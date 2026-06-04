#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
Usage:
  ./build-desktop.sh
      Build macOS desktop app (web dist-desktop + Tauri bundle).

Environment:
  AGENTPOD_API_URL   Host API base URL baked into default gateway (default: http://127.0.0.1:1223)
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

python3 "$ROOT_DIR/scripts/sync-version.py"

if ! command -v cargo >/dev/null 2>&1; then
  echo "error: Rust toolchain not found (cargo). Install from https://rustup.rs or: brew install rust"
  exit 1
fi

echo "==> build desktop frontend (web/dist-desktop)"
cd "$ROOT_DIR/web"
if [[ ! -d node_modules ]]; then
  npm install
fi
npm run build:desktop

echo "==> build AgentPod.app (Tauri)"
cd "$ROOT_DIR/desktop"
if [[ ! -d node_modules ]]; then
  npm install
fi
npm run build

APP_PATH="$ROOT_DIR/desktop/src-tauri/target/release/bundle/macos/AgentPod.app"
if [[ -d "$APP_PATH" ]]; then
  echo "==> done: $APP_PATH"
else
  echo "==> build finished; check desktop/src-tauri/target/release/bundle/"
fi
