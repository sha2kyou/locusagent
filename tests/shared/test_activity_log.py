"""操作日志测试。"""

from __future__ import annotations

import json

from locus_shared import activity_log


def test_record_and_list_activity_logs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCUSAGENT_HOME", str(tmp_path))
    activity_log._ID_LOADED = False
    activity_log._NEXT_ID = 0

    id1 = activity_log.record_activity("mcp", "connect", "连接 sidefy", workspace_id="ws_b5c9f41f1254b9b780b9")
    id2 = activity_log.record_activity("skill", "save", "保存技能 demo")

    assert id2 > id1
    items = activity_log.list_activity_logs(limit=10)
    assert len(items) == 2
    assert items[0]["action"] == "save"
    assert items[1]["action"] == "connect"

    path = activity_log.activity_log_path()
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    parsed = json.loads(lines[0])
    assert parsed["category"] == "mcp"
