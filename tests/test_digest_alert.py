"""日報異常告警測試。不打網路。"""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import digest_alert  # noqa: E402


# ── reason ────────────────────────────────────────────────────────────────────

def test_連線例外只標類別名():
    r = digest_alert.reason(requests.ConnectionError("DNS 解不出來"))
    assert r == "ConnectionError: DNS 解不出來"


def test_anthropic例外引導去查餘額():
    class FakeAPIError(Exception):
        pass
    FakeAPIError.__module__ = "anthropic._exceptions"
    r = digest_alert.reason(FakeAPIError("credit balance is too low"))
    assert r.startswith("Anthropic API 問題（先查餘額與月上限）FakeAPIError: ")
    assert "credit balance is too low" in r


def test_其他例外標成程式錯誤():
    r = digest_alert.reason(TypeError("'<=' not supported"))
    assert r == "程式錯誤（需改 code）TypeError: '<=' not supported"


def test_SystemExit只取訊息本身():
    r = digest_alert.reason(SystemExit("所有來源合計 0 篇，week.json 未更新"))
    assert r == "所有來源合計 0 篇，week.json 未更新"


def test_訊息截到80字且換行被壓掉():
    r = digest_alert.reason(ValueError("a\nb " + "x" * 200))
    detail = r.split("ValueError: ", 1)[1]
    assert "\n" not in r
    assert detail.startswith("a b ")
    assert len(detail) == 80


# ── is_stale ──────────────────────────────────────────────────────────────────

NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)


def test_七天整不算過期():
    assert digest_alert.is_stale((NOW - timedelta(days=7)).isoformat(), NOW) is False


def test_八天算過期():
    assert digest_alert.is_stale((NOW - timedelta(days=8)).isoformat(), NOW) is True


def test_沒有時區的時間當成UTC():
    naive = (NOW - timedelta(days=8)).replace(tzinfo=None).isoformat()
    assert digest_alert.is_stale(naive, NOW) is True


def test_欄位缺失或格式錯誤視為過期():
    assert digest_alert.is_stale(None, NOW) is True
    assert digest_alert.is_stale("上週一", NOW) is True


# ── format_alert ──────────────────────────────────────────────────────────────

def test_訊息標題含階段且每筆一行():
    text = digest_alert.format_alert("每日推播", [("week.json", "過期"), ("心情小語", "壞了")])
    lines = text.split("\n")
    assert lines[0] == "⚠️ 麻醉日報異常（每日推播）"
    assert "・week.json：過期" in lines
    assert "・心情小語：壞了" in lines


# ── report ────────────────────────────────────────────────────────────────────

TODAY = date(2026, 10, 13)


class Harness:
    """把 LINE 與狀態讀寫換成記憶體版本。"""

    def __init__(self, monkeypatch, alerts=None):
        self.alerts = alerts or {}
        self.pushed = []
        self.saved = []
        monkeypatch.setattr(digest_alert.notify, "push_line", self.pushed.append)
        monkeypatch.setattr(digest_alert, "_load_state", lambda: (self.alerts, "sha1"))
        monkeypatch.setattr(
            digest_alert, "_save_state",
            lambda alerts, sha: self.saved.append((dict(alerts), sha)),
        )


def test_沒有失敗就什麼都不做(monkeypatch):
    h = Harness(monkeypatch)
    digest_alert.report("每日推播", [], today=TODAY)
    assert h.pushed == [] and h.saved == []


def test_第一次失敗會推播並記錄(monkeypatch):
    h = Harness(monkeypatch)
    digest_alert.report("每日推播", [("心情小語", "壞了")], today=TODAY)
    assert len(h.pushed) == 1
    assert "・心情小語：壞了" in h.pushed[0]
    saved, sha = h.saved[0]
    assert saved == {"心情小語": {"date": "2026-10-13", "reason": "壞了"}}
    assert sha == "sha1"


def test_冷卻期內同原因不重複推(monkeypatch):
    h = Harness(monkeypatch, {"心情小語": {"date": "2026-10-10", "reason": "壞了"}})
    digest_alert.report("每日推播", [("心情小語", "壞了")], today=TODAY)
    assert h.pushed == [] and h.saved == []


def test_冷卻期內換一種原因立刻推(monkeypatch):
    h = Harness(monkeypatch, {"心情小語": {"date": "2026-10-10", "reason": "壞了"}})
    digest_alert.report("每日推播", [("心情小語", "另一種壞法")], today=TODAY)
    assert len(h.pushed) == 1


def test_滿七天後同原因再推(monkeypatch):
    h = Harness(monkeypatch, {"心情小語": {"date": "2026-10-06", "reason": "壞了"}})
    digest_alert.report("每日推播", [("心情小語", "壞了")], today=TODAY)
    assert len(h.pushed) == 1


def test_只推到期的那幾筆(monkeypatch):
    h = Harness(monkeypatch, {"A": {"date": "2026-10-10", "reason": "x"}})
    digest_alert.report("週一抓取", [("A", "x"), ("B", "y")], today=TODAY)
    assert "・B：y" in h.pushed[0]
    assert "・A：x" not in h.pushed[0]


def test_重複的失敗只列一次(monkeypatch):
    h = Harness(monkeypatch)
    digest_alert.report("週一抓取", [("分類", "x"), ("分類", "x")], today=TODAY)
    assert h.pushed[0].count("・分類：x") == 1


def test_推播失敗不外拋且不寫狀態(monkeypatch):
    h = Harness(monkeypatch)

    def boom(text):
        raise requests.HTTPError("401")

    monkeypatch.setattr(digest_alert.notify, "push_line", boom)
    digest_alert.report("每日推播", [("心情小語", "壞了")], today=TODAY)  # 不可拋例外
    assert h.saved == []


def test_狀態讀取失敗時照樣推播(monkeypatch):
    h = Harness(monkeypatch)

    def boom():
        raise requests.ConnectionError("github 掛了")

    monkeypatch.setattr(digest_alert, "_load_state", boom)
    digest_alert.report("每日推播", [("心情小語", "壞了")], today=TODAY)
    assert len(h.pushed) == 1


def test_狀態寫入失敗不外拋(monkeypatch):
    h = Harness(monkeypatch)

    def boom(alerts, sha):
        raise requests.HTTPError("409")

    monkeypatch.setattr(digest_alert, "_save_state", boom)
    digest_alert.report("每日推播", [("心情小語", "壞了")], today=TODAY)  # 不可拋例外
    assert len(h.pushed) == 1


# ── 本機狀態檔（沒有 GITHUB_TOKEN 時）─────────────────────────────────────────

def test_本機模式讀寫磁碟檔(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setattr(digest_alert, "STATE_PATH", str(tmp_path / "alert_state.json"))
    assert digest_alert._load_state() == ({}, None)
    digest_alert._save_state({"A": {"date": "2026-10-13", "reason": "x"}}, None)
    assert digest_alert._load_state() == ({"A": {"date": "2026-10-13", "reason": "x"}}, None)


def test_send_test失敗要外拋(monkeypatch):
    import pytest

    def boom(text):
        raise requests.HTTPError("401")

    monkeypatch.setattr(digest_alert.notify, "push_line", boom)
    with pytest.raises(requests.HTTPError):
        digest_alert.send_test()
