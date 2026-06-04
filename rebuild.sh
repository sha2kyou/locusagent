#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
Usage:
  ./rebuild.sh host
      Rebuild web + host images (含前端 SPA) and restart web, host, caddy.

  ./rebuild.sh agent <user_id>
      Rebuild agent image and recreate one user isolated container.

  ./rebuild.sh full [user_id]
      Rebuild host+agent images, ensure compose services are up, then optionally recreate one user container.

  ./rebuild.sh infra
      Rebuild and restart infra services only (postgres/tei/host).
EOF
}

ensure_user_container() {
  local user_id="${1:-}"
  if [[ -z "$user_id" ]]; then
    echo "user_id is required"
    exit 1
  fi
  if ! [[ "$user_id" =~ ^[0-9]+$ ]]; then
    echo "user_id must be numeric"
    exit 1
  fi
  docker compose exec -T "host" sh -lc "python - <<'PY'
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
    export DOCKER_BUILDKIT=1
    docker compose --progress=plain build "web" "host"
    docker compose up -d --no-deps "web" "host"
    # host/web 容器 IP 会变；Caddy 可能仍连旧地址导致 502，需一并刷新上游
    docker compose restart caddy
    ;;
  agent)
    user_id="${2:-}"
    docker build -f "agent/Dockerfile" -t "agentpod-agent:latest" "."
    ensure_user_container "$user_id"
    ;;
  full)
    user_id="${2:-}"
    docker build -f "agent/Dockerfile" -t "agentpod-agent:latest" "."
    docker compose build "web" "host"
    docker compose up -d
    if [[ -n "$user_id" ]]; then
      ensure_user_container "$user_id"
    fi
    ;;
  infra)
    docker compose up -d --build "postgres" "tei" "web" "host"
    ;;
  *)
    usage
    exit 1
    ;;
esac
