"""鉴权隔离中间件测试。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentpod_host.middleware.auth_isolation import install_auth_isolation


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/api/v1/models")
    async def v1_models():
        return {"ok": True}

    @app.get("/api/workspace/ping")
    async def workspace_ping():
        return {"ok": True}

    @app.get("/api/scheduled-tasks/")
    async def scheduled_tasks():
        return {"ok": True}

    @app.get("/api/scheduled-tasks")
    async def scheduled_tasks_root():
        return {"ok": True}

    install_auth_isolation(app)
    return TestClient(app)


def test_bearer_allowed_on_v1_models():
    client = _client()
    response = client.get("/api/v1/models", headers={"Authorization": "Bearer apod_test"})
    assert response.status_code == 200


def test_bearer_blocked_on_workspace():
    client = _client()
    response = client.get("/api/workspace/ping", headers={"Authorization": "Bearer apod_test"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "bearer_on_session_path"


def test_bearer_blocked_on_scheduled_tasks():
    client = _client()
    response = client.get("/api/scheduled-tasks/", headers={"Authorization": "Bearer apod_test"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "bearer_on_session_path"


def test_bearer_blocked_on_scheduled_tasks_without_trailing_slash():
    client = _client()
    response = client.get("/api/scheduled-tasks", headers={"Authorization": "Bearer apod_test"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "bearer_on_session_path"


def test_session_blocked_on_v1_without_bearer():
    client = _client()
    client.cookies.set("apod_session", "fake")
    response = client.get("/api/v1/models")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "session_on_bearer_path"
