"""訊息格式化、拆分與 LINE 推播。"""
import os

import requests

from .models import Event
from .sources import LABELS, SOURCES

MAX_CHARS = 4800       # LINE 上限 5000，留 200 安全邊界
MARKER_RESERVE = 40    # 接頁標記「⬇️ 接下頁（1/3）」的空間，先扣掉才不會加完超標

# 分組顯示順序，依 SOURCES 出現順序去重
SOURCE_ORDER = list(dict.fromkeys(s["source"] for s in SOURCES))


def _line_len(text: str) -> int:
    """LINE 的字數是以 UTF-16 code unit 計，非 BMP 字元（多數 emoji）算 2。

    Python 的 len() 算的是 code point，會低估。標題若帶多個 emoji，
    用 len() 判斷就可能送出超過 5000 的訊息，LINE 回 400，推播從此卡住。
    """
    return len(text.encode("utf-16-le")) // 2


def _cut(text: str, budget: int) -> str:
    """取不超過 budget 個 UTF-16 unit 的最長前綴，不會把 emoji 切一半。"""
    total = 0
    for i, ch in enumerate(text):
        width = 2 if ord(ch) > 0xFFFF else 1
        if total + width > budget:
            return text[:i]
        total += width
    return text


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

    # 不在 SOURCE_ORDER 上的來源（新增來源時忘了寫進 sources.py）不可以直接丟掉：
    # 標題的則數用 len(events) 會對不上，而且該事件仍會進 seen.json，
    # 於是「抓得到、算得進、就是不推播」，且因為狀態已前進而永遠不再推。
    orphans = [e for e in main if e.source not in SOURCE_ORDER]
    if orphans:
        lines = ["【未分類來源】"]
        lines.extend(_format_one(e) for e in orphans)
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
    if max_chars <= MARKER_RESERVE:
        # budget 會 <= 0，硬切迴圈的切片長度不再遞減 → 無窮迴圈（不是拋錯，是卡死）
        raise ValueError(f"max_chars 必須大於 {MARKER_RESERVE}")

    if _line_len(text) <= max_chars:
        return [text]

    # 先扣掉接頁標記的空間，否則加上標記後每則反而會超過 LINE 上限
    budget = max_chars - MARKER_RESERVE
    chunks = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if _line_len(candidate) <= budget:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        # 單一區塊本身就超長，只能硬切
        while _line_len(block) > budget:
            head = _cut(block, budget)
            chunks.append(head)
            block = block[len(head):]
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
    """推播一則訊息。

    ⚠️ 結尾的 raise_for_status() 是整個「不漏報」保證的支點：推播失敗必須
    拋例外穿出去，main.run() 才不會呼叫 advance_state()。這行不可拿掉。

    ⚠️ 但它擋不住「LINE 回 200 卻沒送達」。官方明文：請求一旦被平台接受
    （HTTP 200）就無法重試，即使因為使用者封鎖了官方帳號而未能正確送達。
    userId 打錯或使用者封鎖時，這裡看起來完全成功，狀態照樣前進，
    每一則都被標記已推播而永遠不再出現——沒有任何訊號。
    唯一的防線是部署後人工確認真的收到訊息（見 Task 14）。
    """
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
