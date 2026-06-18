"""host_notify 辅助函数测试。"""

from __future__ import annotations

from locus_agent.host_notify import _artifact_notify_category


def test_artifact_notify_category_respects_max_length() -> None:
    long_label = "类" * 80
    category = _artifact_notify_category(long_label)
    assert len(category) <= 64
    assert category.startswith("保存产物（")
    assert category.endswith("）")
