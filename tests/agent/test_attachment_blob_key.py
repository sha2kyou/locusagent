"""Attachment blob key and dedup helpers."""

import pytest

from agentpod_agent.storage.attachments import (
    AttachmentStorageError,
    blob_object_key,
    upload_was_skipped,
)


def test_blob_object_key():
    ws = "ws_test123"
    digest = "a" * 64
    # workspace_id comes from context; patch via monkeypatch in integration tests.
    # Here we only validate digest format enforcement.
    with pytest.raises(AttachmentStorageError):
        blob_object_key("not-a-valid-digest")


def test_blob_object_key_format(monkeypatch):
    monkeypatch.setattr(
        "agentpod_agent.storage.attachments.get_workspace_id",
        lambda: "ws_abc123",
    )
    digest = "b" * 64
    assert blob_object_key(digest) == f"attachments/ws_abc123/blobs/{digest}"


def test_upload_was_skipped():
    assert upload_was_skipped({"skipped": True}) is True
    assert upload_was_skipped({"skipped": False}) is False
    assert upload_was_skipped({"skipped": "true"}) is True
    assert upload_was_skipped({}) is False
