"""MCP 配置桌面环境 URL 规范化。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agentpod_agent.config import get_settings
from agentpod_agent.mcp_.config import load_mcp_config
from agentpod_agent.workspace import workspace_data_dir


@pytest.fixture
def mcp_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ws_id = "ws_test000000000000000001"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    root = workspace_data_dir(ws_id)
    (root / "agent.sqlite").write_bytes(b"")
    yield ws_id
    get_settings.cache_clear()


def test_load_mcp_config_rewrites_docker_internal_url(mcp_workspace: str) -> None:
    cfg_path = workspace_data_dir(mcp_workspace) / "mcp.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "servers": [
                    {
                        "name": "sidefy",
                        "transport": "http",
                        "url": "http://host.docker.internal:39281/mcp",
                        "headers": {"Host": "host.docker.internal:39281"},
                    }
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    configs = load_mcp_config(mcp_workspace)
    assert len(configs) == 1
    assert configs[0].url == "http://127.0.0.1:39281/mcp"
    assert configs[0].headers["Host"] == "127.0.0.1:39281"

    saved = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert saved["servers"][0]["url"] == "http://127.0.0.1:39281/mcp"
    assert saved["servers"][0]["headers"]["Host"] == "127.0.0.1:39281"
