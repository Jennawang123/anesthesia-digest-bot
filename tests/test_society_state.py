"""狀態層測試。"""
import json
import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch import state  # noqa: E402
from society_watch.models import Event  # noqa: E402


def _ev(source, uid):
    return Event(source=source, uid=uid, title="t", date_text="d", url="u")


def test_檔案不存在時回空set(tmp_path):
    assert state.load_seen(tmp_path / "nope.json") == set()


def test_寫入後讀得回來(tmp_path):
    p = tmp_path / "seen.json"
    state.save_seen(p, {"TSA:3105", "PAIN:3142"})
    assert state.load_seen(p) == {"TSA:3105", "PAIN:3142"}


def test_寫出格式為排序且一則一行(tmp_path):
    p = tmp_path / "seen.json"
    state.save_seen(p, {"TSA:3105", "PAIN:3142", "RAPM:32"})
    text = p.read_text(encoding="utf-8")
    assert text.endswith("\n")           # 保留結尾換行，避免整檔 diff
    assert json.loads(text)["seen"] == ["PAIN:3142", "RAPM:32", "TSA:3105"]
    assert text.count('"PAIN:3142"') == 1
    # 每則各佔一行
    assert '"PAIN:3142",\n' in text


def test_只回未見過的項目():
    events = [_ev("TSA", "3105"), _ev("TSA", "3106")]
    assert [e.uid for e in state.filter_new(events, {"TSA:3105"})] == ["3106"]


def test_同一輪內重複的項目只留一筆():
    events = [_ev("TSA", "3105"), _ev("TSA", "3105")]
    assert len(state.filter_new(events, set())) == 1


def test_不同來源相同uid不互相影響():
    events = [_ev("TSA", "32"), _ev("RAPM", "32")]
    assert len(state.filter_new(events, {"TSA:32"})) == 1


def test_快照讀寫(tmp_path):
    p = tmp_path / "snap.txt"
    assert state.load_snapshot(p) == []
    state.save_snapshot(p, ["A", "B"])
    assert state.load_snapshot(p) == ["A", "B"]


def test_寫入失敗不會留下半截檔案(tmp_path, monkeypatch):
    # 直接 write_text 是先截斷再寫，中途被砍會留下壞檔，
    # 下一輪 json.loads 會炸掉且連告警都送不出去
    p = tmp_path / "seen.json"
    state.save_seen(p, {"TSA:1"})

    def boom(*args, **kwargs):
        raise KeyboardInterrupt("模擬 Actions 取消")

    monkeypatch.setattr(state.os, "replace", boom)
    with pytest.raises(KeyboardInterrupt):
        state.save_seen(p, {"TSA:1", "TSA:2"})

    assert state.load_seen(p) == {"TSA:1"}          # 舊內容完好
    assert not list(tmp_path.glob("*.tmp"))         # 暫存檔已清掉
