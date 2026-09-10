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
        self.url = "https://example.com"

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


def test_標頭無charset時優先看頁面自己的meta(monkeypatch):
    # anesth.org.tw 就是這種：Content-Type 裸 text/html，但頁面寫了
    # <meta charset="utf-8">。能問頁面就別用統計猜。
    body = '<meta charset="utf-8"><h4>鎮靜活動</h4>'.encode("utf-8")
    resp = FakeResponse(body, "text/html")
    resp.apparent_encoding = "big5"      # 猜錯的話會解成亂碼
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: resp)
    assert "鎮靜活動" in fetch.get("https://example.com")


def test_標頭有charset時尊重標頭(monkeypatch):
    # apparent_encoding 刻意設成不同值：兩者相同的話，就算實作誤把標頭
    # 無條件覆寫掉，這個測試也照樣會過（mutation 實測確認過）
    resp = FakeResponse("鎮靜活動".encode("utf-8"), "text/html; charset=utf-8")
    resp.apparent_encoding = "big5"
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


def _http_error(status: int) -> requests.HTTPError:
    resp = FakeResponse(b"", "text/html; charset=utf-8")
    resp.status_code = status
    return requests.HTTPError(f"{status}", response=resp)


def test_永久性失敗不重試(monkeypatch):
    # raise_for_status 拋的 HTTPError 也是 RequestException，一律重試的話
    # 站方改網址(404)或擋爬蟲(403)會白白多打兩次
    calls = []

    def gone(*a, **k):
        calls.append(1)
        raise _http_error(404)

    monkeypatch.setattr(fetch.requests, "get", gone)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    with pytest.raises(requests.HTTPError):
        fetch.get("https://example.com")
    assert len(calls) == 1


def test_伺服器錯誤仍會重試(monkeypatch):
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        raise _http_error(503)

    monkeypatch.setattr(fetch.requests, "get", flaky)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    with pytest.raises(requests.HTTPError):
        fetch.get("https://example.com")
    assert len(calls) == 3


def test_attempts為零時明確報錯():
    with pytest.raises(ValueError):
        fetch.get("https://example.com", attempts=0)
