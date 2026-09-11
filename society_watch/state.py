"""去重狀態與 Wix 快照的讀寫。

seen.json 只增不減：TSA 是 15 筆滾動視窗，舊活動會掉出列表，
若為省空間裁剪，該筆日後重新出現就會重推。一則 uid 數十 bytes，
跑十年不過數百 KB，不值得為此冒重推風險。
"""
import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

from .models import Event


def _atomic_write(path: Path, text: str) -> None:
    """先寫暫存檔再 os.replace 換上去。

    直接 write_text 是先截斷再寫：程序在寫入中途被砍（Actions 逾時或
    取消）會留下半截檔案，下一輪 json.loads 直接拋例外，整個 run 在
    collect() 之前就死掉——連告警都送不出去，唯一訊號是 Actions 紅燈。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


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
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


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
    _atomic_write(path, "\n".join(lines) + "\n")


ALERT_COOLDOWN_DAYS = 7


def load_alerts(path: Path) -> dict[str, dict]:
    """回傳 {告警key: {"date": ISO日期, "reason": 失敗原因}}。"""
    if not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def save_alerts(path: Path, alerts: dict[str, dict]) -> None:
    # 要走 _atomic_write：這個檔只有在「真的需要告警的那天」才會被讀，
    # 留下半截檔的話平常完全正常，偏偏在出事那天讓整個 run 死在告警之前。
    _atomic_write(
        path,
        json.dumps(alerts, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def record_alert(alerts: dict[str, dict], source: str, today: date, reason: str) -> None:
    alerts[source] = {"date": today.isoformat(), "reason": reason}


def should_alert(alerts: dict[str, dict], source: str, today: date, reason: str) -> bool:
    """該不該為這次失敗送告警。

    節流是「同一站、同一種壞法」7 天一次。換一種壞法要立刻說：
    連線失敗與「解析出 0 筆，疑似改版」是兩個不同的問題、要做的事也不同，
    第二個若被第一個的冷卻期吃掉，就會靜默七天。

    這個檔是 commit 進 public repo、可能被手動編輯的，所以一律 fail-open：
    值壞掉、型別不對、或日期落在未來（時鐘偏移或手改）都當成「該告警」。
    寧可多吵一次，也不要因為一個壞掉的欄位而靜默——更不要讓 ValueError
    穿出去，那會讓整個 run 死在告警之前，連當天的活動推播都一起沒了。
    """
    entry = alerts.get(source)
    if not isinstance(entry, dict):
        return True
    if entry.get("reason") != reason:
        return True
    try:
        last = date.fromisoformat(entry.get("date", ""))
    except (TypeError, ValueError):
        return True
    if last > today:
        return True
    return today - last >= timedelta(days=ALERT_COOLDOWN_DAYS)
