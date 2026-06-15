"""Agent 内部鉴权测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from agentpod_agent.auth import verify_internal_token


@pytest.mark.asyncio
async def test_verify_internal_token_rejects_invalid_workspace_id() -> None:
    with patch("agentpod_agent.auth.get_settings") as mock_settings:
        mock_settings.return_value.internal_token = "secret"
        with pytest.raises(HTTPException) as exc:
            await verify_internal_token(
                x_internal_token="secret",
                x_workspace_id="ws_default",
            )
    assert exc.value.status_code == 400
    assert exc.value.detail == "invalid workspace id"


@pytest.mark.asyncio
async def test_verify_internal_token_accepts_valid_workspace_id() -> None:
    wid = "ws_b5c9f41f1254b9b780b9"
    with patch("agentpod_agent.auth.get_settings") as mock_settings:
        mock_settings.return_value.internal_token = "secret"
        with patch("agentpod_agent.auth.ensure_workspace_context", new=AsyncMock()) as ensure_ctx:
            await verify_internal_token(
                x_internal_token="secret",
                x_workspace_id=wid,
            )
    ensure_ctx.assert_awaited_once_with(wid)
