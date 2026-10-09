"""國泰世華轉點加碼的狀態（cub_promos.json）、內容比對、截止提醒判定。

檔案結構：{campaignPath: {"title", "url", "partners": [夥伴 dict],
                          "first_seen": ISO 日期, "reminded": [已提醒過的截止日]}}
"""
import json
from datetime import date
from pathlib import Path

from society_watch.state import _atomic_write

# 比買點的 2 天多一天：亞洲萬里通的轉換入帳要 3–14 個工作天，
# 而且登錄窗口可能只在截止前幾天才開（2026 年是 10/28–10/30）。
REMIND_DAYS = 3


def load(path: Path) -> dict[str, dict]:
    if not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def save(path: Path, promos: dict[str, dict]) -> None:
    _atomic_write(
        path, json.dumps(promos, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def entry(title: str, url: str, partners: list[dict], today: date,
          reminded: list[str] | None = None) -> dict:
    return {"title": title, "url": url, "partners": partners,
            "first_seen": today.isoformat(), "reminded": list(reminded or [])}


def _signature(partners: list[dict]) -> list[tuple[str, ...]]:
    # 只比「會改變使用者決定」的欄位。registration／cap 是 Haiku 摘出的一句話，
    # 兩次判讀的措辭可能不同，放進來會把同一份內容誤判成有更新。
    return sorted(
        tuple(str(p.get(k)) for k in ("name", "bonus", "start", "end"))
        for p in partners if isinstance(p, dict)
    )


def same_content(a: list[dict], b: list[dict]) -> bool:
    return _signature(a) == _signature(b)


def due_groups(entry_: dict, today: date) -> list[tuple[date, list[dict]]]:
    """回傳該提醒的（截止日, 那天到期的夥伴）清單，依日期排序。壞資料跳過不拋。"""
    if not isinstance(entry_, dict) or not isinstance(entry_.get("partners"), list):
        return []
    reminded = entry_.get("reminded")
    reminded = set(reminded) if isinstance(reminded, list) else set()

    by_end: dict[date, list[dict]] = {}
    for p in entry_["partners"]:
        if not isinstance(p, dict):
            continue
        try:
            end = date.fromisoformat(p.get("end") or "")
        except (TypeError, ValueError):
            continue
        if end.isoformat() in reminded or not 0 <= (end - today).days <= REMIND_DAYS:
            continue
        by_end.setdefault(end, []).append(p)
    return sorted(by_end.items())
