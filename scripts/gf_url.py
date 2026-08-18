#!/usr/bin/env python3
"""把四段行程編碼成 Google Flights 的 tfs 查詢網址。

tfs 是 base64url 編碼的 protobuf。結構為 2026-08-18 以使用者實際操作
產生的網址反解得出，並經逐字元比對驗證：

    [1]  varint = 28              固定值
    [2]  varint = 2               固定值（填 1 會被 Google 拒絕並退回首頁）
    [3]  message  ← repeated，一段航程一筆
         [2]  str     出發日期 "2026-12-23"
         [13] message 出發地 { [1]=1 (機場), [2]="PUS" }
         [14] message 目的地 { [1]=1, [2]="TPE" }
    [8]  varint      成人數
    [9]  varint = 1  艙等：1 = 經濟艙
    [14] varint = 1
    [16] message { [1] = 2^64-1 }
    [19] varint = 3  行程類型：3 = multi-city

注意路徑是 /travel/flights/search（不是 /travel/flights），且必須帶
tfu=EgIIACIA，否則不會進入搜尋結果頁。

Google 未公開此格式，日後改版可能失效。fare_scan.py 會在連續多次
查無結果時警告，避免格式失效被誤判成「所有組合都沒票」。
"""

import base64

TFU = "EgIIACIA"
BASE = "https://www.google.com/travel/flights/search"

LOC_AIRPORT = 1  # location type：1 = 機場（IATA code）
CABIN_ECONOMY = 1
TRIP_MULTI_CITY = 3


def _varint(n):
    out = b""
    while True:
        x = n & 0x7F
        n >>= 7
        out += bytes([x | 0x80]) if n else bytes([x])
        if not n:
            return out


def _tag(field, wire_type):
    return _varint((field << 3) | wire_type)


def _str_field(field, value):
    raw = value.encode()
    return _tag(field, 2) + _varint(len(raw)) + raw


def _msg_field(field, payload):
    return _tag(field, 2) + _varint(len(payload)) + payload


def _varint_field(field, value):
    return _tag(field, 0) + _varint(value)


def _location(iata):
    return _varint_field(1, LOC_AIRPORT) + _str_field(2, iata)


def _leg(date, origin, dest, nonstop=False):
    body = _str_field(2, date)
    if nonstop:
        # [5]=0 等同 UI 的「僅顯示直達航班」（0 次轉機）。
        # 實測位置在日期之後、出發地之前，順序不可調換。
        body += _varint_field(5, 0)
    return body + _msg_field(13, _location(origin)) + _msg_field(14, _location(dest))


def build_tfs(legs, adults=1, cabin=CABIN_ECONOMY, nonstop=False):
    """legs: [(date, origin_iata, dest_iata), ...]，回傳 base64url 字串。

    nonstop: True 代表每段都限定直達；也可傳段索引的可迭代物件
    （如 [0]）只限定特定段。
    """
    if nonstop is True:
        ns = set(range(len(legs)))
    elif nonstop is False or nonstop is None:
        ns = set()
    else:
        ns = set(nonstop)

    body = _varint_field(1, 28) + _varint_field(2, 2)
    for i, (date, origin, dest) in enumerate(legs):
        body += _msg_field(3, _leg(date, origin, dest, i in ns))
    body += (_varint_field(8, adults)
             + _varint_field(9, cabin)
             + _varint_field(14, 1)
             + _msg_field(16, _varint_field(1, (1 << 64) - 1))
             + _varint_field(19, TRIP_MULTI_CITY))
    return base64.urlsafe_b64encode(body).decode().rstrip("=")


def build_url(legs, currency="KRW", lang="zh-TW", adults=1, nonstop=False):
    """產生可直接開啟的 Google Flights 查詢網址。"""
    tfs = build_tfs(legs, adults=adults, nonstop=nonstop)
    return f"{BASE}?tfs={tfs}&tfu={TFU}&hl={lang}&curr={currency}"
