#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  exec "$ROOT_DIR/rebuild.sh"
fi

exec "$ROOT_DIR/rebuild.sh" desktop
