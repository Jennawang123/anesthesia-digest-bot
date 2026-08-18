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
