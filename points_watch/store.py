"""已處理過的促銷（promos.json）與截止提醒判定。

「看過的文章」（seen_articles.json）直接用 society_watch.state 的
load_seen／save_seen，這裡不重寫。
"""
import json
from datetime import date
from pathlib import Path

from society_watch.state import _atomic_write

from .models import Rated

REMIND_DAYS = 2   # 🟢 促銷剩幾天（含）以內提醒
UNDATED_ACTIVE_DAYS = 21   # 沒有截止日的促銷，首見後多久內仍視為進行中


def covered(promos: dict[str, dict], promo, today: date) -> bool:
    """這筆促銷是否已被一筆「同計畫、同類型、進行中、幅度不低於它」的紀錄涵蓋。

    Promo.key 含百分比與截止日，但同一檔促銷各家寫法不同：2026-10-09 實測
    Loyalty Lobby 寫 Alaska「up to 120%、10/19 截止」，OMAAT 寫「100%」且摘要
    沒有截止日，兩個鍵不同會各推一次。幅度更高的不算被涵蓋——那是值得再通知的加碼。
    """
    for e in promos.values():
        if not isinstance(e, dict):
            continue
        if e.get("program") != promo.program or e.get("kind") != promo.kind:
            continue
        percent = e.get("percent")
        if isinstance(percent, bool) or not isinstance(percent, (int, float)):
            continue
        if percent < promo.percent:
            continue
        try:
            if e.get("end_date"):
                active = date.fromisoformat(e["end_date"]) >= today
            else:
                first = date.fromisoformat(e.get("first_seen") or "")
                active = 0 <= (today - first).days <= UNDATED_ACTIVE_DAYS
        except (TypeError, ValueError):
            continue
        if active:
            return True
    return False


def load_promos(path: Path) -> dict[str, dict]:
    if not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def save_promos(path: Path, promos: dict[str, dict]) -> None:
    _atomic_write(
        path, json.dumps(promos, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def entry(rated: Rated, today: date) -> dict:
    p = rated.promo
    return {
        "program": p.program, "kind": p.kind, "percent": p.percent,
        "cpp": rated.cpp, "grade": rated.grade,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "url": p.url, "first_seen": today.isoformat(), "reminded": False,
    }


def due_reminders(promos: dict[str, dict], today: date) -> list[str]:
    """回傳該送截止提醒的促銷鍵（已排序）。壞掉的紀錄跳過不拋例外。"""
    due = []
    for key, e in promos.items():
        if not isinstance(e, dict) or e.get("grade") != "green" or e.get("reminded"):
            continue
        try:
            end = date.fromisoformat(e.get("end_date") or "")
        except (TypeError, ValueError):
            continue
        if 0 <= (end - today).days <= REMIND_DAYS:
            due.append(key)
    return sorted(due)
