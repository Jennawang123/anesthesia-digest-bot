#!/usr/bin/env python3
"""產生待掃描的四段行程組合。

四段結構固定為境外票模式：
    腿1  <亞洲進> → TPE      讓票價以該國為 fare origin
    腿2  TPE → <長程目的地>
    腿3  <長程目的地> → TPE
    腿4  TPE → <亞洲出>      回到出發區域，形成 open-jaw

Phase 1（韓國進出 × 歐洲兩點）為 4 × 2 × 108 = 864 組。
"""

import hashlib
from datetime import date, timedelta

PHASE1 = {
    "asia_in": ["ICN", "PUS"],
    "asia_out": ["ICN", "PUS"],
    "long_haul": ["VIE", "MXP"],
    "windows": {
        "leg1": ("2026-12-21", "2026-12-23"),
        "leg2": ("2027-02-25", "2027-02-27"),
        "leg3": ("2027-03-05", "2027-03-08"),
        "leg4": ("2027-04-14", "2027-04-16"),
    },
}


# Phase 2：亞洲端與日期窗同 Phase 1，長程改為美西。
# 使用者明確排除 SEA，只要 LAX 與 SFO。
PHASE2 = {
    "asia_in": ["ICN", "PUS"],
    "asia_out": ["ICN", "PUS"],
    "long_haul": ["LAX", "SFO"],
    "windows": PHASE1["windows"],
}

def date_windows(start, end):
    """把起訖日展開成每日字串清單（含頭含尾）。"""
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    out = []
    while d0 <= d1:
        out.append(d0.isoformat())
        d0 += timedelta(days=1)
    return out


def combo_id(legs):
    """由四段內容產生穩定 id，確保同組合重複掃描落在同一筆。"""
    key = "|".join(f"{d}:{o}-{t}" for d, o, t in legs)
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def generate(config):
    """依設定產生所有組合，回傳 [{"id":..., "legs":[(date,from,to)x4]}]。"""
    w = config["windows"]
    d1 = date_windows(*w["leg1"])
    d2 = date_windows(*w["leg2"])
    d3 = date_windows(*w["leg3"])
    d4 = date_windows(*w["leg4"])

    combos = []
    for a_in in config["asia_in"]:
        for a_out in config["asia_out"]:
            for dest in config["long_haul"]:
                for x1 in d1:
                    for x2 in d2:
                        for x3 in d3:
                            for x4 in d4:
                                legs = [
                                    (x1, a_in, "TPE"),
                                    (x2, "TPE", dest),
                                    (x3, dest, "TPE"),
                                    (x4, "TPE", a_out),
                                ]
                                combos.append({"id": combo_id(legs), "legs": legs})
    return combos
