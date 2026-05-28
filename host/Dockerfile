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

EXPOSE 8080

CMD ["uvicorn", "agentpod_host.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
