#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
Usage:
  ./rebuild.sh host
      Rebuild and restart host only (without dependencies).

  ./rebuild.sh agent <user_id>
      Rebuild agent image and recreate one user isolated container.

  ./rebuild.sh full [user_id]
      Rebuild full compose stack, then optionally recreate one user container.

  ./rebuild.sh clean-placeholder
      Remove exited one-shot placeholder container: agentpod-agent-image-1.
EOF
}

ensure_user_container() {
  local user_id="${1:-}"
  if [[ -z "$user_id" ]]; then
    echo "user_id is required"
    exit 1
  fi
  docker exec "agentpod-host-1" sh -lc "python - <<'PY'
import asyncio
from agentpod_host.db import init_engine, dispose_engine
from agentpod_host.orchestrator.lifecycle import ensure_user_container

USER_ID = ${user_id}

async def main():
    await init_engine()
    try:
        st = await ensure_user_container(USER_ID, force_recreate=True)
        print('status', st.value)
    finally:
        await dispose_engine()

asyncio.run(main())
PY"
}

cmd="${1:-}"
case "$cmd" in
  host)
    docker compose build "host"
    docker compose up -d --no-deps "host"
    ;;
  agent)
    user_id="${2:-}"
    docker build -f "agent/Dockerfile" -t "agentpod-agent:latest" "."
    ensure_user_container "$user_id"
    ;;
  full)
    user_id="${2:-}"
    docker compose down
    docker build -f "agent/Dockerfile" -t "agentpod-agent:latest" "."
    docker compose build "host"
    docker compose up -d
    if [[ -n "$user_id" ]]; then
      ensure_user_container "$user_id"
    fi
    ;;
  clean-placeholder)
    docker rm "agentpod-agent-image-1" 2>/dev/null || true
    ;;
  *)
    usage
    exit 1
    ;;
esac
