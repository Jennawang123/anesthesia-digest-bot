"""狀態層測試。"""
import json
import sys
from datetime import date

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


def test_首次失敗就告警():
    assert state.should_alert({}, "TSA", date(2026, 9, 10), "連線失敗") is True


def test_七天內同樣的壞法不再告警():
    alerts = {"TSA": {"date": "2026-09-10", "reason": "連線失敗"}}
    assert state.should_alert(alerts, "TSA", date(2026, 9, 14), "連線失敗") is False


def test_滿七天後再次告警():
    alerts = {"TSA": {"date": "2026-09-10", "reason": "連線失敗"}}
    assert state.should_alert(alerts, "TSA", date(2026, 9, 17), "連線失敗") is True


def test_冷卻期內換一種壞法要立刻告警():
    # 連線失敗與「解析出 0 筆，疑似改版」是兩個不同的問題、要做的事也不同，
    # 第二個被第一個的冷卻期吃掉就會靜默七天
    alerts = {"TSA": {"date": "2026-09-10", "reason": "連線失敗"}}
    assert state.should_alert(alerts, "TSA", date(2026, 9, 11), "解析出 0 筆，疑似改版") is True


def test_不同站各自計算節流():
    alerts = {"TSA": {"date": "2026-09-10", "reason": "連線失敗"}}
    assert state.should_alert(alerts, "PAIN", date(2026, 9, 11), "連線失敗") is True


def test_告警紀錄壞掉時一律fail_open():
    # 這個檔 commit 在 public repo 裡、可能被手動改壞。
    # 壞掉要當成「該告警」，而不是靜默，更不能讓例外穿出去把整個 run 弄死
    today = date(2026, 9, 11)
    for broken in ["2026-09-10", "", None, 20260910, [], {"date": "2026/09/10"},
                   {"date": "九月十日"}, {"date": None}, {}]:
        assert state.should_alert({"TSA": broken}, "TSA", today, "連線失敗") is True


def test_未來日期不會造成長期靜默():
    # 手改或時鐘偏移寫進未來日期的話，原本會一路靜默到那一天
    alerts = {"TSA": {"date": "2027-01-01", "reason": "連線失敗"}}
    assert state.should_alert(alerts, "TSA", date(2026, 9, 11), "連線失敗") is True


def test_告警紀錄讀寫(tmp_path):
    p = tmp_path / "alerts.json"
    assert state.load_alerts(p) == {}
    alerts = {}
    state.record_alert(alerts, "TSA", date(2026, 9, 10), "連線失敗")
    state.save_alerts(p, alerts)
    assert state.load_alerts(p) == {"TSA": {"date": "2026-09-10", "reason": "連線失敗"}}


def test_告警紀錄也要原子寫入(tmp_path, monkeypatch):
    # 這個檔只在「真的需要告警的那天」被讀，留半截檔的話平常完全正常，
    # 偏偏在出事那天讓整個 run 死在告警之前
    p = tmp_path / "alerts.json"
    state.save_alerts(p, {"TSA": {"date": "2026-09-10", "reason": "連線失敗"}})

    def boom(*args, **kwargs):
        raise KeyboardInterrupt("模擬 Actions 取消")

    monkeypatch.setattr(state.os, "replace", boom)
    with pytest.raises(KeyboardInterrupt):
        state.save_alerts(p, {"TSA": {"date": "2026-09-99", "reason": "壞掉"}})
    assert state.load_alerts(p)["TSA"]["date"] == "2026-09-10"
    assert not list(tmp_path.glob("*.tmp"))


def test_告警檔不是dict時回空(tmp_path):
    p = tmp_path / "alerts.json"
    p.write_text('["壞掉的格式"]', encoding="utf-8")
    assert state.load_alerts(p) == {}


def test_心跳狀態讀寫(tmp_path):
    p = tmp_path / "heartbeat.json"
    assert state.load_heartbeat(p) is None
    state.save_heartbeat(p, "2026-09")
    assert state.load_heartbeat(p) == "2026-09"


def test_該月尚未送過就要送():
    assert state.should_heartbeat(None, date(2026, 9, 11)) is True
    assert state.should_heartbeat("2026-08", date(2026, 9, 11)) is True


def test_同月不重複送():
    # 同一個月手動再觸發一次 workflow 不應該再送一則
    assert state.should_heartbeat("2026-09", date(2026, 9, 30)) is False


def test_心跳不綁定每月一號():
    # 1 號當天若網路失敗，該月第一次成功執行仍要送，否則會缺一拍造成假警報
    assert state.should_heartbeat("2026-08", date(2026, 9, 17)) is True
