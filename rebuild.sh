#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

python3 "$ROOT_DIR/scripts/sync-version.py"

setup_bundle_resources() {
  local bundle_root="$ROOT_DIR/desktop/src-tauri/resources"
  local bundle_venv="$bundle_root/sidecar-venv"
  local fresh="${1:-0}"
  local py

  if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv required for desktop bundle (https://docs.astral.sh/uv/)" >&2
    exit 1
  fi

  if [[ "$fresh" == "1" || ! -x "$bundle_venv/bin/python3" ]]; then
    local standalone_root
    echo "==> prepare bundled sidecar python (uv standalone 3.11, may take several minutes)"
    rm -rf "$bundle_venv"
    standalone_root="$(bash "$ROOT_DIR/scripts/resolve-standalone-python.sh")"
    echo "==> copy standalone python from $standalone_root"
    mkdir -p "$bundle_venv"
    ditto "$standalone_root/" "$bundle_venv/"
    rm -f "$bundle_venv/lib/python3.11/EXTERNALLY-MANAGED"
  else
    echo "==> refresh bundled sidecar python (incremental)"
  fi

  py="$bundle_venv/bin/python3"
  ln -sf python3 "$bundle_venv/bin/python"

  "$py" -m ensurepip --upgrade >/dev/null 2>&1 || true
  "$py" -m pip install -U pip
  "$py" -m pip install --no-cache-dir \
    "$ROOT_DIR/shared" "$ROOT_DIR/host" "$ROOT_DIR/agent" "$ROOT_DIR/sidecar"

  echo "==> prune bundle python (drop pip tooling, bytecode cache)"
  "$py" -m pip uninstall -y pip setuptools wheel >/dev/null 2>&1 || true
  find "$bundle_venv" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

  echo "==> verify bundled sidecar import"
  "$py" -c "import locusagent, locus_host, locus_agent, locus_shared"

  echo "==> copy shared-skills into bundle resources"
  rm -rf "$bundle_root/shared-skills"
  cp -R "$ROOT_DIR/shared-skills" "$bundle_root/shared-skills"
}

repackage_dmg() {
  local app_src="$ROOT_DIR/desktop/src-tauri/target/release/bundle/macos/Locus Agent.app"
  local dmg_dir="$ROOT_DIR/desktop/src-tauri/target/release/bundle/dmg"
  local version
  version="$(tr -d '[:space:]' < "$ROOT_DIR/VERSION")"
  local dmg_out="$dmg_dir/LocusAgent_${version}_macos-arm64.dmg"

  if [[ ! -d "$app_src" ]]; then
    echo "error: missing $app_src" >&2
    exit 1
  fi

  rm -f "$dmg_dir"/LocusAgent_*.dmg
  mkdir -p "$dmg_dir"
  echo "==> repackage DMG from Locus Agent.app"
  hdiutil create -volname "Locus Agent" -srcfolder "$app_src" -ov -format UDZO "$dmg_out"
}

publish_desktop_artifacts() {
  local dist="$ROOT_DIR/dist"
  local app_src="$ROOT_DIR/desktop/src-tauri/target/release/bundle/macos/Locus Agent.app"
  local dmg_dir="$ROOT_DIR/desktop/src-tauri/target/release/bundle/dmg"

  rm -rf "$dist/Locus Agent.app" "$dist"/LocusAgent_*.dmg 2>/dev/null || true
  mkdir -p "$dist"

  if [[ -d "$app_src" ]]; then
    echo "==> copy Locus Agent.app -> dist/"
    ditto "$app_src" "$dist/Locus Agent.app"
  else
    echo "warning: missing $app_src" >&2
  fi

  local dmg=""
  if [[ -d "$dmg_dir" ]]; then
    dmg=$(ls -t "$dmg_dir"/LocusAgent_*.dmg 2>/dev/null | head -1 || true)
  fi
  if [[ -n "$dmg" && -f "$dmg" ]]; then
    echo "==> copy $(basename "$dmg") -> dist/"
    cp "$dmg" "$dist/"
  else
    echo "warning: no LocusAgent_*.dmg found under $dmg_dir" >&2
  fi

  if [[ -d "$dist/Locus Agent.app" ]]; then
    echo "==> done: $dist/Locus Agent.app"
    ls -lh "$dist"
  else
    echo "==> build finished; check desktop/src-tauri/target/release/bundle/" >&2
    exit 1
  fi
}

fresh_venv=0
for arg in "$@"; do
  case "$arg" in
    --fresh-venv) fresh_venv=1 ;;
    *)
      echo "error: unknown option: $arg" >&2
      echo "usage: ./rebuild.sh [--fresh-venv]" >&2
      exit 1
      ;;
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

echo "==> build Locus Agent.app (Tauri, cargo may take a few minutes)"
"$ROOT_DIR/scripts/prepare-desktop-resources.sh"
cd "$ROOT_DIR/desktop"
if [[ ! -d node_modules ]]; then
  npm install
fi
npm run build

if [[ -d "$ROOT_DIR/desktop/src-tauri/target/release/bundle/macos/Locus Agent.app" ]]; then
  repackage_dmg
fi

publish_desktop_artifacts
