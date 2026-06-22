from unittest.mock import AsyncMock, patch

import pytest

from locus_agent.host_settings import clear_host_settings_runtime_cache, get_resolved_model
from locus_shared.settings_store import reload_runtime_config


@pytest.mark.asyncio
async def test_clear_host_settings_runtime_cache_refetches_model() -> None:
    fetch = AsyncMock(side_effect=["gemma4:12b-mlx", "deepseek-v4-flash"])
    with patch("locus_agent.host_settings._fetch_model_from_host", new=fetch):
        clear_host_settings_runtime_cache()
        assert await get_resolved_model("main") == "gemma4:12b-mlx"
        assert await get_resolved_model("main") == "gemma4:12b-mlx"
        fetch.assert_called_once()

        clear_host_settings_runtime_cache()
        assert await get_resolved_model("main") == "deepseek-v4-flash"
        assert fetch.call_count == 2


def test_reload_runtime_config_clears_host_settings_cache() -> None:
    with patch("locus_agent.host_settings.clear_host_settings_runtime_cache") as clear_mock:
        reload_runtime_config()
        clear_mock.assert_called_once()
