"""workspace id 格式校验。"""

import pytest

from agentpod_shared.workspace_ids import generate_workspace_id, is_valid_workspace_id, normalize_workspace_id


def test_generate_workspace_id_is_valid():
    wid = generate_workspace_id()
    assert wid.startswith("ws_")
    assert is_valid_workspace_id(wid)


@pytest.mark.parametrize(
    "value",
    [
        "ws_default",
        "ws_abc",
        "ws_0123456789abcdef012",
        "ws_0123456789abcdef01234",
    ],
)
def test_rejects_invalid_workspace_ids(value: str):
    assert not is_valid_workspace_id(value)


def test_normalize_accepts_valid_id():
    assert normalize_workspace_id("ws_0123456789abcdef0123") == "ws_0123456789abcdef0123"


def test_normalize_rejects_invalid_id():
    with pytest.raises(ValueError, match="invalid workspace id"):
        normalize_workspace_id("ws_default")
