FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates nodejs npm && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -g 10001 agentpod && \
    useradd -u 10001 -g 10001 -m -s /usr/sbin/nologin agentpod && \
    mkdir -p /data /app/skills && \
    chown -R agentpod:agentpod /data /app

COPY agent/pyproject.toml ./agent/pyproject.toml

# 先仅按 pyproject 安装依赖（不受 agent/src 变更影响），并缓存 pip 下载内容。
RUN --mount=type=cache,target=/root/.cache/pip python - <<'PY' | xargs -r pip install
import tomllib
from pathlib import Path

cfg = tomllib.loads(Path("/app/agent/pyproject.toml").read_text(encoding="utf-8"))
deps = cfg.get("project", {}).get("dependencies", [])
print(" ".join(str(d) for d in deps))
PY

COPY agent/src ./agent/src
COPY shared-skills ./shared-skills

# 再安装项目本身，避免每次源码变更都重下三方依赖。
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-deps ./agent && \
    cp -r ./shared-skills/. /app/skills/ && \
    chown -R agentpod:agentpod /app/skills

USER agentpod:agentpod

EXPOSE 8000

CMD ["uvicorn", "agentpod_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
