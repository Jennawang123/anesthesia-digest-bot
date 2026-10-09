"""點數通知的 LINE 推送：新 bot 優先、舊 bot 後備。"""
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import line  # noqa: E402


class _Resp:
    def __init__(self, status=200):
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(str(self.status))


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "token": headers["Authorization"], "to": json["to"],
                      "text": json["messages"][0]["text"]})
        return _Resp()

    monkeypatch.setattr(line.requests, "post", fake_post)
    for name in ("POINTS_LINE_CHANNEL_ACCESS_TOKEN", "POINTS_LINE_USER_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "old-token")
    monkeypatch.setenv("LINE_USER_ID", "Uold")
    return calls


def test_falls_back_to_existing_bot(sent):
    line.push_line("hi")
    assert sent == [{"url": "https://api.line.me/v2/bot/message/push",
                     "token": "Bearer old-token", "to": "Uold", "text": "hi"}]


def test_new_token_with_shared_user_id(sent, monkeypatch):
    # 新舊 channel 同一個 provider 時 user ID 相同，只需要設新 token
    monkeypatch.setenv("POINTS_LINE_CHANNEL_ACCESS_TOKEN", "new-token")
    line.push_line("hi")
    assert (sent[0]["token"], sent[0]["to"]) == ("Bearer new-token", "Uold")


def test_both_new(sent, monkeypatch):
    monkeypatch.setenv("POINTS_LINE_CHANNEL_ACCESS_TOKEN", "new-token")
    monkeypatch.setenv("POINTS_LINE_USER_ID", "Unew")
    line.push_line("hi")
    assert (sent[0]["token"], sent[0]["to"]) == ("Bearer new-token", "Unew")


def test_empty_secret_counts_as_unset(sent, monkeypatch):
    # GitHub Actions 對不存在的 secret 會傳空字串，不是不傳
    monkeypatch.setenv("POINTS_LINE_CHANNEL_ACCESS_TOKEN", "")
    monkeypatch.setenv("POINTS_LINE_USER_ID", "")
    line.push_line("hi")
    assert (sent[0]["token"], sent[0]["to"]) == ("Bearer old-token", "Uold")


def test_http_error_propagates(monkeypatch, sent):
    monkeypatch.setattr(line.requests, "post", lambda *a, **k: _Resp(500))
    with pytest.raises(requests.HTTPError):
        line.push_line("hi")
