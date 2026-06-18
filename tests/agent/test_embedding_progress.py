"""embedding_progress 单元测试。"""

from __future__ import annotations

import pytest

from locus_agent.embedding_progress import _aggregate_counts, _build_summary, _empty_counts


def test_build_summary_percent():
    totals = {"pending": 2, "ready": 8, "failed": 0, "skipped": 3}
    summary = _build_summary(totals)
    assert summary["remaining"] == 2
    assert summary["indexable"] == 10
    assert summary["percent"] == 80.0


def test_build_summary_empty_indexable():
    totals = _empty_counts()
    summary = _build_summary(totals)
    assert summary["percent"] is None
    assert summary["remaining"] == 0


def test_aggregate_counts():
    by_kind = {
        "memory": {"pending": 1, "ready": 2, "failed": 0, "skipped": 0},
        "message": {"pending": 3, "ready": 4, "failed": 1, "skipped": 2},
    }
    totals = _aggregate_counts(by_kind)
    assert totals["pending"] == 4
    assert totals["ready"] == 6
    assert totals["failed"] == 1
    assert totals["skipped"] == 2
