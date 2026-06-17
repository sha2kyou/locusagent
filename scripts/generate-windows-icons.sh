#!/usr/bin/env bash
# 从方形 mark 生成 Windows 用 icon.ico 与小尺寸 PNG（桌面/任务栏/托盘）。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ICONS="$ROOT_DIR/desktop/src-tauri/icons"
SOURCE="$ICONS/icon-square.png"
GEN_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$GEN_DIR"
}
trap cleanup EXIT

if [[ ! -f "$SOURCE" ]]; then
  sips -z 1024 1024 "$ROOT_DIR/frontend/public/apple-touch-icon.png" --out "$SOURCE" >/dev/null
fi

cd "$ROOT_DIR/desktop"
npx --yes tauri icon "$SOURCE" -o "$GEN_DIR" >/dev/null

install -m 644 "$GEN_DIR/icon.ico" "$ICONS/icon.ico"
install -m 644 "$GEN_DIR/32x32.png" "$ICONS/32x32.png"
install -m 644 "$GEN_DIR/128x128.png" "$ICONS/128x128.png"
install -m 644 "$GEN_DIR/128x128@2x.png" "$ICONS/128x128@2x.png"
install -m 644 "$GEN_DIR/32x32.png" "$ICONS/tray-32.png"
sips -z 16 16 "$ICONS/tray-32.png" --out "$ICONS/tray-16.png" >/dev/null

echo "==> updated Windows icons under $ICONS"
