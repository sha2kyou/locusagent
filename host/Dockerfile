# ---- frontend (Vite → host/.../web/spa) ----
FROM node:22-alpine AS web

WORKDIR /build/web

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build

# ---- host ----
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY host/pyproject.toml ./host/pyproject.toml
COPY host/src ./host/src

RUN pip install ./host

COPY --from=web /build/host/src/agentpod_host/web/spa \
    /usr/local/lib/python3.11/site-packages/agentpod_host/web/spa

EXPOSE 8080

CMD ["uvicorn", "agentpod_host.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
