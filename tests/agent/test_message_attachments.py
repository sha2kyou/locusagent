"""用户消息附件持久化与上下文回注测试。"""

from __future__ import annotations

from agentpod_agent.core.persistence import (
    _compose_user_content_with_attachments,
    build_persisted_user_message_text,
)


def test_build_persisted_user_message_text_includes_attachment_names() -> None:
    attachments = [
        {"id": "att_abc", "name": "screenshot.png", "kind": "image"},
    ]
    text = build_persisted_user_message_text(
        "",
        attachments=attachments,
        attachment_ids=["att_abc"],
    )
    assert "[用户附件] screenshot.png (image, id=att_abc)" in text
    assert "[attachment_ids:" in text


def test_compose_user_content_labels_image_filename() -> None:
    attachments = [
        {
            "id": "att_abc",
            "name": "photo.jpg",
            "kind": "image",
            "processable": True,
            "imageDataUrl": "data:image/jpeg;base64,abc",
        },
    ]
    composed = _compose_user_content_with_attachments("请描述这张图", attachments)
    assert isinstance(composed, list)
    texts = [p["text"] for p in composed if p.get("type") == "text"]
    assert any("photo.jpg" in t for t in texts)
    assert any(p.get("type") == "image_url" for p in composed)
