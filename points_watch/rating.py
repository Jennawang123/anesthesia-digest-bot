"""Promo ＋ 基準 → 每點成本與評等。純函式，另含基準檔的讀取與改寫。"""
import json
import re
from pathlib import Path

from .models import Promo, Rated

GREEN_RATIO = 1.03      # 平或破歷史最佳（3% 內）
YELLOW_RATIO = 1.15     # 比歷史最佳貴 15% 以內
DIVERGE = 0.10          # 公式值與文章報價差距超過這個比例就採文章報價
SUSPICIOUS_RATIO = 0.70  # 低於歷史最佳的七成＝幾乎必是抽錯
_EPS = 1e-9             # 浮點誤差容忍，讓「剛好在門檻上」穩定落在門檻內


class SuspiciousPrice(ValueError):
    """算出的價格低得不合理。拋出去由 main 記成失敗並告警，不推播、不改基準。"""


def _formula(kind: str, percent: int, base_cpp: float) -> float:
    if kind == "discount":
        return base_cpp * (1 - percent / 100)
    return base_cpp / (1 + percent / 100)


def rate(promo: Promo, baseline: dict) -> Rated:
    best = baseline["best_cpp"]
    cpp = round(_formula(promo.kind, promo.percent, baseline["base_cpp"]), 2)
    from_article = False
    stated = promo.stated_cpp
    if stated is not None and abs(cpp - stated) / stated > DIVERGE:
        cpp, from_article = round(stated, 2), True

    if cpp < best * SUSPICIOUS_RATIO:
        raise SuspiciousPrice("每點成本低於歷史最佳的七成，疑似抽取錯誤")

    if cpp <= best * GREEN_RATIO + _EPS:
        grade = "green"
    elif cpp <= best * YELLOW_RATIO + _EPS:
        grade = "yellow"
    else:
        grade = "red"
    return Rated(promo=promo, cpp=cpp, best_cpp=best, grade=grade,
                 new_low=cpp < best - _EPS, from_article=from_article)


def load_baselines(path: Path) -> dict[str, dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def update_best(text: str, program: str, new_best: float) -> str:
    """把某計畫的 best_cpp 換成新值，其餘一個字元都不動。

    刻意不用 json.load＋json.dump：整檔重寫會重排版面，把一個數字的變更
    放大成整檔 diff（CLAUDE.md 開發流程第二條）。baselines.json 一個計畫
    一行，這裡靠該版面做單行內取代。
    """
    pattern = re.compile(
        r'("' + re.escape(program) + r'":\s*\{[^}\n]*"best_cpp":\s*)[0-9.]+'
    )
    out, n = pattern.subn(lambda m: f"{m.group(1)}{new_best:.2f}", text, count=1)
    if n != 1:
        raise KeyError(program)
    return out
