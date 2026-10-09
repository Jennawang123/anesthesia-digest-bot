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
