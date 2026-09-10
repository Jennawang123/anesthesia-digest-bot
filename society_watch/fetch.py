"""HTTP 抓取層：UA、timeout、重試、編碼修正。"""
import time

import requests

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def get(url: str, timeout: int = 30, attempts: int = 3) -> str:
    """抓一個頁面回傳解碼後的 HTML 字串。

    anesth.org.tw 的 Content-Type 不帶 charset，requests 此時會退回猜
    ISO-8859-1 導致整頁中文變亂碼，因此標頭沒有 charset 就改用
    apparent_encoding（實測為 utf-8）。
    """
    last_error = None
    for i in range(attempts):
        try:
            resp = requests.get(url, headers=UA, timeout=timeout)
            resp.raise_for_status()
            if "charset=" not in resp.headers.get("Content-Type", "").lower():
                resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except requests.RequestException as e:
            last_error = e
            if i == attempts - 1:
                break
            wait = 2 ** i
            print(f"    ⚠️ 抓取失敗（{type(e).__name__}），{wait}s 後重試（{i + 2}/{attempts}）")
            time.sleep(wait)
    raise last_error
