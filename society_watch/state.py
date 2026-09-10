"""去重狀態與 Wix 快照的讀寫。

seen.json 只增不減：TSA 是 15 筆滾動視窗，舊活動會掉出列表，
若為省空間裁剪，該筆日後重新出現就會重推。一則 uid 數十 bytes，
跑十年不過數百 KB，不值得為此冒重推風險。
"""
import json
from pathlib import Path
from typing import Iterable

from .models import Event


def load_seen(path: Path) -> set[str]:
    if not Path(path).exists():
        return set()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return set(data.get("seen", []))


def save_seen(path: Path, keys: Iterable[str]) -> None:
    """排序後 pretty-print、一則一行、保留結尾換行。

    格式沿用 daily_data/sent_articles.json，讓每日 commit 的 diff
    只有真正新增的那幾行。
    """
    payload = {"seen": sorted(keys)}
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def filter_new(events: Iterable[Event], seen: set[str]) -> list[Event]:
    """濾出未通知過的項目，並去掉同一輪內的重複（保持原順序）。"""
    result = []
    batch_seen = set()
    for event in events:
        if event.key in seen or event.key in batch_seen:
            continue
        batch_seen.add(event.key)
        result.append(event)
    return result


def load_snapshot(path: Path) -> list[str]:
    if not Path(path).exists():
        return []
    text = Path(path).read_text(encoding="utf-8")
    return [line for line in text.split("\n") if line.strip()]


def save_snapshot(path: Path, lines: list[str]) -> None:
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
