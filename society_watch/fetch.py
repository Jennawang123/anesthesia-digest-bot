"""HTTP 抓取層：UA、timeout、重試、編碼決定。"""
import re
import time

import requests

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# 只在前段找，避免整頁掃描；meta charset 依規範就該在 head 前面
_META_CHARSET = re.compile(
    rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.I
)


def _header_charset(resp: requests.Response) -> str | None:
    ctype = resp.headers.get("Content-Type", "")
    m = re.search(r"charset\s*=\s*([^\s;]+)", ctype, re.I)
    return m.group(1).strip('"\'') if m else None


def _meta_charset(content: bytes) -> str | None:
    m = _META_CHARSET.search(content[:4096])
    return m.group(1).decode("ascii", "ignore") if m else None


def _decode(resp: requests.Response) -> str:
    """決定編碼並解碼。

    順序：HTTP 標頭 → 頁面自己的 <meta charset> → apparent_encoding。

    為什麼要有中間那一層：anesth.org.tw 的 Content-Type 是裸 text/html，
    requests 會退回猜 ISO-8859-1，整頁中文變亂碼；但那一頁其實有寫
    <meta charset="utf-8">，requests 完全不看。落到 apparent_encoding 是
    純統計推斷，而 CJK 編碼互相誤判時解出來的是「合法但錯誤的漢字」，
    不會拋例外、不會有 U+FFFD，任何下游檢查都攔不到——parser 照樣吐出
    N 筆亂碼標題推到 LINE。能問頁面就別用猜的。
    """
    encoding = _header_charset(resp)
    if not encoding:
        encoding = _meta_charset(resp.content)
    if not encoding:
        encoding = resp.apparent_encoding or "utf-8"
        # 推斷是最後手段，留一行紀錄讓 Actions log 看得到用了什麼
        print(f"    ℹ️ {getattr(resp, 'url', '?')} 未宣告編碼，推斷為 {encoding}")

    resp.encoding = encoding
    return resp.text


def _should_retry(error: requests.RequestException) -> bool:
    """只重試「等一下可能會好」的失敗。

    raise_for_status 拋的 HTTPError 也是 RequestException，若一律重試，
    站方改網址（404）或擋爬蟲（403）這種永久性失敗會白白多打兩次。
    """
    if isinstance(error, requests.HTTPError):
        resp = error.response
        if resp is None:
            return False
        return resp.status_code == 429 or resp.status_code >= 500
    return True   # 連線、逾時、DNS 等傳輸類一律重試


def get(url: str, timeout: int = 30, attempts: int = 3) -> str:
    """抓一個頁面回傳解碼後的 HTML 字串。"""
    if attempts < 1:
        raise ValueError("attempts 至少要 1")

    last_error = None
    for i in range(attempts):
        try:
            resp = requests.get(url, headers=UA, timeout=timeout)
            resp.raise_for_status()
            return _decode(resp)
        except requests.RequestException as e:
            last_error = e
            if not _should_retry(e):
                break
            if i == attempts - 1:
                break
            wait = 2 ** i
            print(f"    ⚠️ 抓取失敗（{type(e).__name__}），{wait}s 後重試（{i + 2}/{attempts}）")
            time.sleep(wait)
    raise last_error
