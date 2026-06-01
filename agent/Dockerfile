FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
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
COPY agent/src ./agent/src
COPY shared-skills ./shared-skills

RUN pip install ./agent && \
    cp -r ./shared-skills/. /app/skills/ && \
    chown -R agentpod:agentpod /app/skills

USER agentpod:agentpod

EXPOSE 8000

CMD ["uvicorn", "agentpod_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
