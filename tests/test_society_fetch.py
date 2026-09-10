"""抓取層測試。離線測編碼與重試，另有 --live 測試打真實網站。"""
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch import fetch  # noqa: E402


class FakeResponse:
    def __init__(self, body: bytes, content_type: str):
        self.content = body
        self.headers = {"Content-Type": content_type}
        self.encoding = "ISO-8859-1"   # requests 無 charset 時的預設猜測
        self.apparent_encoding = "utf-8"
        self.status_code = 200

    @property
    def text(self):
        return self.content.decode(self.encoding)

    def raise_for_status(self):
        pass


def test_標頭無charset時改用apparent_encoding(monkeypatch):
    body = "鎮靜活動".encode("utf-8")
    monkeypatch.setattr(
        fetch.requests, "get",
        lambda *a, **k: FakeResponse(body, "text/html"),
    )
    assert fetch.get("https://example.com") == "鎮靜活動"


def test_標頭有charset時尊重標頭(monkeypatch):
    resp = FakeResponse("鎮靜活動".encode("utf-8"), "text/html; charset=utf-8")
    resp.encoding = "utf-8"
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: resp)
    assert fetch.get("https://example.com") == "鎮靜活動"


def test_失敗會重試三次後放棄(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise requests.ConnectionError("斷線")

    monkeypatch.setattr(fetch.requests, "get", boom)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    with pytest.raises(requests.ConnectionError):
        fetch.get("https://example.com")
    assert len(calls) == 3


def test_第二次就成功則不再重試(monkeypatch):
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise requests.ConnectionError("斷線")
        return FakeResponse("OK".encode("utf-8"), "text/html; charset=utf-8")

    monkeypatch.setattr(fetch.requests, "get", flaky)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    fetch.get("https://example.com")
    assert len(calls) == 2


@pytest.mark.live
def test_實際抓TSA不亂碼():
    html = fetch.get("https://www.anesth.org.tw/events/index.asp")
    assert "鎮靜" in html or "工作坊" in html
