"""attachments_proxy blob PUT 校验。"""

import hashlib

import pytest
from fastapi import HTTPException

from locus_host.routers.attachments_proxy import (
    _assert_body_matches_key_digest,
    _validate_blob_put_key,
    _validate_file_put_key,
)


def test_validate_blob_put_key_returns_digest():
    ws = "ws_0ceb1c565177caecc172"
    digest = "a" * 64
    key = f"{ws}/blobs/{digest}"
    assert _validate_blob_put_key(object_key=key, workspace_id=ws) == digest


def test_validate_blob_put_key_rejects_legacy_path():
    ws = "ws_0ceb1c565177caecc172"
    with pytest.raises(HTTPException) as exc:
        _validate_blob_put_key(
            object_key=f"attachments/{ws}/att_x/image/abc",
            workspace_id=ws,
        )
    assert exc.value.status_code == 400


def test_assert_body_matches_key_digest():
    data = b"hello"
    digest = hashlib.sha256(data).hexdigest()
    _assert_body_matches_key_digest(data=data, expected_digest=digest)


def test_validate_file_put_key_accepts_att_suffix():
    ws = "ws_0ceb1c565177caecc172"
    key = f"{ws}/files/att_abc123.rules.sidescript"
    _validate_file_put_key(object_key=key, workspace_id=ws)


def test_assert_body_mismatch_raises():
    with pytest.raises(HTTPException) as exc:
        _assert_body_matches_key_digest(data=b"hello", expected_digest="b" * 64)
    assert exc.value.status_code == 400
