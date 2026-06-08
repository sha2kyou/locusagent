#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

python3 "$ROOT_DIR/scripts/sync-version.py"

usage() {
  cat <<'EOF'
Usage:
  ./rebuild.sh
      Build macOS desktop app (default). Same as ./rebuild.sh desktop.

  ./rebuild.sh desktop
      Build macOS desktop app (bundle venv + SPA + Tauri .app / .dmg).
      Copies release artifacts to dist/ at repo root.

  ./rebuild.sh sidecar
      Create/update sidecar venv only (editable, for dev — no .app rebuild).

  ./rebuild.sh desktop --fresh-venv
      Force full rebuild of bundled Python venv (slow; default is incremental).

  ./rebuild.sh migrate-docker [extra args]
      Migrate Docker volume apod-data-2 to ~/.agentpod (see scripts/migrate_docker_volume.py).
EOF
}

setup_sidecar_venv() {
  local venv="$ROOT_DIR/sidecar/.venv"
  if [[ ! -d "$venv" ]]; then
    python3 -m venv "$venv"
  fi
  # shellcheck disable=SC1091
  source "$venv/bin/activate"
  echo "==> sidecar dev venv: install dependencies"
  pip install -U pip
  pip install -e "$ROOT_DIR/shared" -e "$ROOT_DIR/host" -e "$ROOT_DIR/agent" -e "$ROOT_DIR/sidecar"
  pip install pytest pytest-asyncio httpx
}

setup_bundle_resources() {
  local bundle_root="$ROOT_DIR/desktop/src-tauri/resources"
  local bundle_venv="$bundle_root/sidecar-venv"
  local fresh="${1:-0}"

  if [[ "$fresh" == "1" || ! -x "$bundle_venv/bin/python" ]]; then
    echo "==> prepare bundled sidecar venv (full install, may take several minutes)"
    rm -rf "$bundle_venv"
    python3 -m venv --copies "$bundle_venv"
  else
    echo "==> refresh bundled sidecar venv (incremental)"
  fi

  # shellcheck disable=SC1091
  source "$bundle_venv/bin/activate"
  pip install -U pip
  pip install "$ROOT_DIR/shared" "$ROOT_DIR/host" "$ROOT_DIR/agent" "$ROOT_DIR/sidecar"

  echo "==> copy shared-skills into bundle resources"
  rm -rf "$bundle_root/shared-skills"
  cp -R "$ROOT_DIR/shared-skills" "$bundle_root/shared-skills"
}

repackage_dmg() {
  local app_src="$ROOT_DIR/desktop/src-tauri/target/release/bundle/macos/AgentPod.app"
  local dmg_dir="$ROOT_DIR/desktop/src-tauri/target/release/bundle/dmg"
  local version
  version="$(tr -d '[:space:]' < "$ROOT_DIR/VERSION")"
  local dmg_out="$dmg_dir/AgentPod_${version}_aarch64.dmg"

  if [[ ! -d "$app_src" ]]; then
    echo "error: missing $app_src" >&2
    exit 1
  fi

  rm -f "$dmg_dir"/AgentPod_*.dmg
  mkdir -p "$dmg_dir"
  echo "==> repackage DMG from relocated AgentPod.app"
  hdiutil create -volname "AgentPod" -srcfolder "$app_src" -ov -format UDZO "$dmg_out"
}

publish_desktop_artifacts() {
  local dist="$ROOT_DIR/dist"
  local app_src="$ROOT_DIR/desktop/src-tauri/target/release/bundle/macos/AgentPod.app"
  local dmg_dir="$ROOT_DIR/desktop/src-tauri/target/release/bundle/dmg"

  rm -rf "$dist"/AgentPod.app "$dist"/AgentPod_*.dmg 2>/dev/null || true
  mkdir -p "$dist"

  if [[ -d "$app_src" ]]; then
    echo "==> copy AgentPod.app -> dist/"
    ditto "$app_src" "$dist/AgentPod.app"
  else
    echo "warning: missing $app_src" >&2
  fi

  local dmg=""
  if [[ -d "$dmg_dir" ]]; then
    dmg=$(ls -t "$dmg_dir"/AgentPod_*.dmg 2>/dev/null | head -1 || true)
  fi
  if [[ -n "$dmg" && -f "$dmg" ]]; then
    echo "==> copy $(basename "$dmg") -> dist/"
    cp "$dmg" "$dist/"
  else
    echo "warning: no AgentPod_*.dmg found under $dmg_dir" >&2
  fi

  if [[ -d "$dist/AgentPod.app" ]]; then
    echo "==> done: $dist/AgentPod.app"
    ls -lh "$dist"
  else
    echo "==> build finished; check desktop/src-tauri/target/release/bundle/" >&2
    exit 1
  fi
}

rebuild_desktop() {
  local fresh_venv=0
  for arg in "$@"; do
    case "$arg" in
      --fresh-venv) fresh_venv=1 ;;
    esac
  done

  setup_bundle_resources "$fresh_venv"

  if ! command -v cargo >/dev/null 2>&1; then
    echo "error: Rust toolchain not found (cargo). Install from https://rustup.rs or: brew install rust"
    exit 1
  fi

  echo "==> build desktop frontend (frontend/dist-desktop)"
  cd "$ROOT_DIR/frontend"
  if [[ ! -d node_modules ]]; then
    npm install
  fi
  npm run build:desktop

  echo "==> build AgentPod.app (Tauri, cargo may take a few minutes)"
  "$ROOT_DIR/scripts/prepare-desktop-resources.sh"
  cd "$ROOT_DIR/desktop"
  if [[ ! -d node_modules ]]; then
    npm install
  fi
  npm run build

  if [[ -d "$ROOT_DIR/desktop/src-tauri/target/release/bundle/macos/AgentPod.app" ]]; then
    echo "==> embed Python.framework into AgentPod.app"
    bash "$ROOT_DIR/scripts/relocate-bundle-python.sh" \
      "$ROOT_DIR/desktop/src-tauri/target/release/bundle/macos/AgentPod.app"
    repackage_dmg
  fi

  publish_desktop_artifacts
}

cmd="${1:-desktop}"
if [[ "$cmd" == "--fresh-venv" ]]; then
  rebuild_desktop --fresh-venv
  exit 0
fi
if [[ $# -gt 0 ]]; then
  shift
fi
case "$cmd" in
  sidecar)
    setup_sidecar_venv
    echo "==> sidecar venv ready: sidecar/.venv"
    ;;
  desktop)
    rebuild_desktop "$@"
    ;;
  migrate-docker)
    python3 "$ROOT_DIR/scripts/migrate_docker_volume.py" "$@"
    ;;
  *)
    usage
    exit 1
    ;;
esac
