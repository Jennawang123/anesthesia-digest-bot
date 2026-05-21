#!/usr/bin/env python3
"""
週一至週五 09:00 TWN 執行。
讀取 daily_data/week.json，格式化當日日報後推送至 LINE 群組。
若單則訊息超過 4800 字，自動接力拆分。
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta

import requests
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
LINE_TOKEN    = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_GROUP_ID = os.environ["LINE_GROUP_ID"]

TOPICS = {
    1: {"name": "重症醫學",           "day": "週一"},
    2: {"name": "疼痛與區域麻醉",     "day": "週二"},
    3: {"name": "一般麻醉與神經麻醉", "day": "週三"},
    4: {"name": "小兒與產科麻醉",     "day": "週四"},
    5: {"name": "心臟麻醉",           "day": "週五"},
}

MAX_CHARS = 4800  # LINE 上限 5000，留 200 buffer


# ── 1. Data ───────────────────────────────────────────────────────────────────

def taiwan_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=8)


def load_articles(weekday: int) -> list[dict]:
    with open("daily_data/week.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    arts = data["articles"].get(str(weekday), [])
    # 3–5 篇：5 篇以上取 5，3 篇以下全取（不足也推）
    return arts[:5] if len(arts) >= 5 else arts


# ── 2. Format ─────────────────────────────────────────────────────────────────

def build_prompt(articles: list[dict], topic: dict, date_str: str) -> str:
    article_block = "\n\n".join(
        f"[{i+1}] 《{a['journal']}》\n標題：{a['title']}\n摘要：{a['abstract'][:400]}\n連結：{a['url']}"
        for i, a in enumerate(articles)
    )

    return f"""你是麻醉科日報編輯，請將以下文章整理成 LINE 推播日報。

開頭固定格式：
🩺 麻醉科日報 {date_str}（{topic['day']}）
主題：{topic['name']}
━━━━━━━━━━━━━━━━━━━━

每篇文章格式（嚴格照此結構）：

### [完整英文標題]

> 📍 [期刊名] | [發表年月，格式：YYYY年Mon] | [研究設計，如 Phase 3 RCT / Meta-analysis / Cohort study 等] | [⭐ 星級]
>
> 🔑 [一句話核心發現，繁體中文，醫療術語保留英文]
>
> 📊 主要發現：
- [關鍵數據或發現 1]
- [關鍵數據或發現 2]
- [關鍵數據或發現 3，若有]
>
> 💡 臨床意義：[對臨床實務的影響，繁體中文，醫療術語保留英文]
>
> 🔗 [URL]

結尾：
━━━━━━━━━━━━━━━━━━━━
共 N 篇｜{date_str}

規則：
- ⭐⭐⭐ 給 RCT、重要 meta-analysis；⭐⭐ 給有臨床意義的觀察研究；⭐ 給其他
- 醫療術語、藥名、術式、縮寫、期刊名全部保留英文，不翻譯
- 📊 bullet points 列具體數值（p value、OR、HR、NNT 等），無具體數值則列關鍵比較結果
- 直接輸出訊息本體，不加任何說明文字

文章資料：
{article_block}"""


def format_message(articles: list[dict], topic: dict, date_str: str) -> str:
    if not articles:
        return (
            f"🩺 麻醉科日報 {date_str}（{topic['day']}）\n"
            f"主題：{topic['name']}\n\n"
            "本週此領域尚無新文章。"
        )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1800,
        messages=[{"role": "user", "content": build_prompt(articles, topic, date_str)}],
    )
    return response.content[0].text.strip()


# ── 3. Split ──────────────────────────────────────────────────────────────────

def split_message(text: str) -> list[str]:
    """在文章邊界（### 開頭）切割，確保每則 ≤ MAX_CHARS。"""
    if len(text) <= MAX_CHARS:
        return [text]

    import re
    # 找每篇文章的起始位置（### 開頭的行）
    boundary_positions = [m.start() for m in re.finditer(r"^###", text, re.MULTILINE)]

    if not boundary_positions:
        return [text[i:i + MAX_CHARS] for i in range(0, len(text), MAX_CHARS)]

    # 第一段包含 header（從頭到第一個 ###）
    parts = []
    current_start = 0
    last_boundary = boundary_positions[0]

    for pos in boundary_positions[1:]:
        if pos - current_start > MAX_CHARS:
            chunk = text[current_start:last_boundary].rstrip()
            parts.append(chunk)
            current_start = last_boundary
        last_boundary = pos

    parts.append(text[current_start:].strip())

    # 加接力標記
    total = len(parts)
    if total == 1:
        return parts

    result = []
    for i, part in enumerate(parts):
        if i < total - 1:
            result.append(part + f"\n\n⬇️ 接下頁（{i+1}/{total}）")
        else:
            result.append(f"⬆️ 接上頁（{i+1}/{total}）\n\n" + part)
    return result


# ── 4. Push ───────────────────────────────────────────────────────────────────

def push_line(text: str) -> None:
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "to":       LINE_GROUP_ID,
            "messages": [{"type": "text", "text": text}],
        },
        timeout=30,
    )
    resp.raise_for_status()


# ── 5. Main ───────────────────────────────────────────────────────────────────

def main():
    now_twn  = taiwan_now()
    weekday  = now_twn.isoweekday()  # 1=週一 … 5=週五
    date_str = now_twn.strftime("%Y/%m/%d")

    if weekday not in TOPICS:
        print(f"今日為週末（{weekday}），不推送。")
        return

    topic = TOPICS[weekday]
    print(f"{date_str} {topic['day']} | 主題：{topic['name']}")

    articles = load_articles(weekday)
    print(f"文章數：{len(articles)}")

    message = format_message(articles, topic, date_str)
    print(f"訊息字數：{len(message)}")

    parts = split_message(message)
    print(f"拆分為 {len(parts)} 則訊息")

    for i, part in enumerate(parts, 1):
        print(f"  推送第 {i}/{len(parts)} 則（{len(part)} 字）...")
        push_line(part)
        if i < len(parts):
            time.sleep(1)

    print("完成。")


if __name__ == "__main__":
    main()
