#!/usr/bin/env python3
"""解析 Google Flights 中文介面的航班列表文字。

所有格式均以 2026-08-18 實測抓取的真實文字為準。列表項文字範例：

    下午6:55 |  –  | 晚上8:25 | 長榮航空 | 2 小時 30 分鐘 | PUS–TPE | 直達 |
    154 公斤 CO2e | 比一般排放量高出 22% | ￦1,774,600 | 整趟行程

轉機版本：

    下午2:55 |  –  | 下午1:05+1 | 長榮航空 | 15 小時 10 分鐘 | VIE–TPE |
    轉機 1 次 | 1 小時 20 分鐘 BKK | ... | ￦2,401,200 | 整趟行程

注意：幣別符號是全形 ￦（U+FFE6），不是半形 ₩（U+20A9）。
用半形寫 regex 會完全抓不到價格。
"""

import re

# 中文時段前綴 → 是否需要加 12 小時
_PERIOD_ADD_12 = {
    "凌晨": False,   # 凌晨12:10 = 00:10（特例見下方）
    "清晨": False,
    "上午": False,
    "中午": False,
    "下午": True,
    "晚上": True,
}

_CLOCK_RE = re.compile(
    r"(凌晨|清晨|上午|中午|下午|晚上)\s*(\d{1,2}):(\d{2})\s*(?:\+(\d))?"
)


def parse_clock(text):
    """把「下午6:55」轉成 ("18:55", 0)，回傳 (HH:MM, 跨日天數)。

    無法解析時回傳 None。
    """
    m = _CLOCK_RE.search(text)
    if not m:
        return None
    period, hour, minute, plus_days = m.groups()
    hour = int(hour)

    if _PERIOD_ADD_12[period]:
        if hour < 12:
            hour += 12
    elif period == "凌晨" and hour == 12:
        # 「凌晨12:10」代表 00:10
        hour = 0

    return f"{hour:02d}:{minute}", int(plus_days or 0)


# 全形 ￦ (U+FFE6)。半形 ₩ (U+20A9) 抓不到 Google Flights 的價格。
_PRICE_RE = re.compile(r"[￦₩]\s?([\d,]{4,})")
_ROUTE_RE = re.compile(r"([A-Z]{3})[–\-—]([A-Z]{3})")
_DURATION_RE = re.compile(r"(\d+\s*小時(?:\s*\d+\s*分鐘)?|\d+\s*分鐘)")
# 轉機點：「1 小時 20 分鐘 BKK」的結尾機場代碼
_VIA_RE = re.compile(r"分鐘\s+([A-Z]{3})")
_CARRIER_RE = re.compile(r"(長榮航空|中華航空|大韓航空|[一-鿿]{2,6}航空)")


def parse_row(text):
    """解析一列航班文字，回傳 dict；非航班列回傳 None。

    回傳欄位：depart, arrive, arrive_plus_days, carrier, duration,
    from, to, nonstop, via, price
    """
    route = _ROUTE_RE.search(text)
    price = _PRICE_RE.search(text)
    if not route or not price:
        return None

    clocks = _CLOCK_RE.findall(text)
    if len(clocks) < 2:
        return None
    depart = parse_clock(_rebuild_clock(clocks[0]))
    arrive = parse_clock(_rebuild_clock(clocks[1]))
    if not depart or not arrive:
        return None

    nonstop = "直達" in text
    via = None
    if not nonstop:
        m = _VIA_RE.search(text)
        via = m.group(1) if m else None

    carrier = _CARRIER_RE.search(text)
    duration = _DURATION_RE.search(text)

    return {
        "depart": depart[0],
        "arrive": arrive[0],
        "arrive_plus_days": arrive[1],
        "carrier": carrier.group(1) if carrier else None,
        "duration": duration.group(1).strip() if duration else None,
        "from": route.group(1),
        "to": route.group(2),
        "nonstop": nonstop,
        "via": via,
        "price": int(price.group(1).replace(",", "")),
    }


def _rebuild_clock(groups):
    """把 _CLOCK_RE.findall 的 tuple 還原成可再解析的字串。"""
    period, hour, minute, plus_days = groups
    s = f"{period}{hour}:{minute}"
    return s + f"+{plus_days}" if plus_days else s
