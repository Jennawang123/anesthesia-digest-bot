#!/usr/bin/env python3
"""取得 KRW→TWD 匯率並換算。

2026-08-18 實測三家免費服務：
    open.er-api.com        可用，免 key，每日更新    ← 採用
    api.frankfurter.app    301 重導
    api.exchangerate.host  已改為需要 access key

匯率每日更新一次即可，不需每次查詢都取。
"""

import json
import math
import urllib.request

API = "https://open.er-api.com/v6/latest/KRW"


def fetch_krw_twd(timeout=15):
    """回傳 (匯率, 更新時間字串)。失敗時拋出例外，由呼叫端決定如何處理。"""
    with urllib.request.urlopen(API, timeout=timeout) as r:
        data = json.loads(r.read())
    if data.get("result") != "success":
        raise RuntimeError(f"匯率 API 回傳非 success：{data.get('result')}")
    rate = data["rates"]["TWD"]
    return rate, data.get("time_last_update_utc", "")


def to_twd(krw, rate):
    """把韓元換算成台幣整數。rate 為 None 時回傳 None。

    用 math.floor(x + 0.5) 而非 round()：round() 是銀行家捨入，
    round(50.5) == 50，不符合四捨五入。
    """
    if rate is None:
        return None
    return math.floor(krw * rate + 0.5)
