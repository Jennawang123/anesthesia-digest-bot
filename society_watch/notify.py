"""訊息格式化、拆分與 LINE 推播。"""
import os

import requests

from .models import Event
from .sources import LABELS, SOURCES

MAX_CHARS = 4800       # LINE 上限 5000，留 200 buffer（同 daily_push.py）
MARKER_RESERVE = 40    # 接頁標記「⬇️ 接下頁（1/3）」的空間，先扣掉才不會加完超標

# 分組顯示順序，依 SOURCES 出現順序去重
SOURCE_ORDER = list(dict.fromkeys(s["source"] for s in SOURCES))


def _format_one(event: Event) -> str:
    parts = [f"・{event.title}"]
    detail = event.date_text
    if event.place:
        detail = f"{detail}｜{event.place}" if detail else event.place
    if detail:
        parts.append(f"  {detail}")
    parts.append(f"  {event.url}")
    return "\n".join(parts)


def format_message(events: list[Event]) -> str:
    """依學會分組；非活動類公告降到底部「其他公告」區。"""
    main = [e for e in events if not e.minor]
    minor = [e for e in events if e.minor]

    blocks = [f"🔔 學會新活動 {len(events)} 則"]

    for source in SOURCE_ORDER:
        group = [e for e in main if e.source == source]
        if not group:
            continue
        lines = [f"【{LABELS.get(source, source)}】"]
        lines.extend(_format_one(e) for e in group)
        blocks.append("\n".join(lines))

    if minor:
        lines = ["── 其他公告 ──"]
        for e in minor:
            lines.append(f"・【{LABELS.get(e.source, e.source)}】{e.title}")
            lines.append(f"  {e.url}")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def split_message(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """在學會區塊邊界（空行）切割，確保每則 ≤ max_chars。"""
    if len(text) <= max_chars:
        return [text]

    # 先扣掉接頁標記的空間，否則加上標記後每則反而會超過 LINE 上限
    budget = max_chars - MARKER_RESERVE
    chunks = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= budget:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        # 單一區塊本身就超長，只能硬切
        while len(block) > budget:
            chunks.append(block[:budget])
            block = block[budget:]
        current = block
    if current:
        chunks.append(current)

    total = len(chunks)
    if total == 1:
        return chunks
    return [
        c + f"\n\n⬇️ 接下頁（{i + 1}/{total}）" if i < total - 1
        else f"⬆️ 接上頁（{i + 1}/{total}）\n\n" + c
        for i, c in enumerate(chunks)
    ]


def format_alert(failures: list[tuple[str, str]]) -> str:
    lines = ["⚠️ 學會監測異常", ""]
    lines.extend(f"・{source}：{reason}" for source, reason in failures)
    lines.append("")
    lines.append("請確認該站是否改版或搬家。")
    return "\n".join(lines)


def push_line(text: str) -> None:
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {os.environ['LINE_CHANNEL_ACCESS_TOKEN']}",
            "Content-Type": "application/json",
        },
        json={
            "to": os.environ["LINE_USER_ID"],
            "messages": [{"type": "text", "text": text}],
        },
        timeout=30,
    )
    resp.raise_for_status()
