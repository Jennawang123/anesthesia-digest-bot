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


def load_sent_urls() -> set[str]:
    try:
        with open("daily_data/sent_articles.json", "r", encoding="utf-8") as f:
            return set(json.load(f).get("sent_urls", []))
    except FileNotFoundError:
        return set()


def save_sent_urls(urls: set[str]) -> None:
    gh_token = os.environ.get("GITHUB_TOKEN")
    gh_repo  = os.environ.get("GITHUB_REPOSITORY")
    data     = {"sent_urls": sorted(urls)}

    with open("daily_data/sent_articles.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    if gh_token and gh_repo:
        import base64
        content_b64 = base64.b64encode(
            json.dumps(data, ensure_ascii=False, indent=2).encode()
        ).decode()
        headers = {
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        url = f"https://api.github.com/repos/{gh_repo}/contents/daily_data/sent_articles.json"
        get  = requests.get(url, headers=headers)
        sha  = get.json().get("sha") if get.status_code == 200 else None
        payload: dict = {
            "message": "chore: update sent articles [skip ci]",
            "content": content_b64,
            "committer": {"name": "github-actions[bot]", "email": "github-actions[bot]@users.noreply.github.com"},
        }
        if sha:
            payload["sha"] = sha
        requests.put(url, headers=headers, json=payload).raise_for_status()


def load_articles(weekday: int) -> tuple[list[dict], str | None]:
    with open("daily_data/week.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    topic_data = data["articles"].get(str(weekday), {})
    # 新格式：{"hot_theme": "...", "items": [...]}
    # 舊格式相容：直接是 list
    if isinstance(topic_data, dict):
        hot_theme = topic_data.get("hot_theme")
        arts = topic_data.get("items", [])
    else:
        hot_theme = None
        arts = topic_data

    # 過濾已推送文章
    sent = load_sent_urls()
    arts = [a for a in arts if a.get("url", "") not in sent]

    # 每本期刊最多 2 篇，確保來源多元，總篇數 3–5
    seen: dict[str, int] = {}
    selected = []
    for a in arts:
        journal = a.get("journal", "")
        if seen.get(journal, 0) < 2:
            selected.append(a)
            seen[journal] = seen.get(journal, 0) + 1
        if len(selected) == 5:
            break

    if len(selected) < 3:
        selected = arts[:5]

    return selected, hot_theme


# ── 2. Format ─────────────────────────────────────────────────────────────────

def build_prompt(articles: list[dict], topic: dict, date_str: str, hot_theme: str | None = None) -> str:
    article_block = "\n\n".join(
        f"[{i+1}] 《{a['journal']}》\n標題：{a['title']}\n摘要：{a['abstract'][:400]}\n連結：{a['url']}"
        for i, a in enumerate(articles)
    )

    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    n = len(articles)

    hot_line = f"\n🔥 本週熱點：{hot_theme}" if hot_theme else ""

    return f"""你是麻醉科日報編輯，請將以下文章整理成 LINE 推播日報。

開頭固定格式：
🩺 麻醉科日報 {date_str}（{topic['day']}）
主題：{topic['name']}{hot_line}
━━━━━━━━━━━━━━━━━━━━

每篇文章格式（依序用 {" ".join(number_emojis[:n])} 編號，嚴格照此結構，不可有 ### 或 > 符號）：

[數字emoji] [完整英文標題]

📍 [期刊名] | [發表年月，格式：YYYY年Mon] | [研究設計] | [⭐星級]

🔑 [一句話核心發現，繁體中文，醫療術語保留英文]

📊 主要發現：
• [關鍵數據或發現 1]
• [關鍵數據或發現 2]
• [關鍵數據或發現 3，若有]

💡 [臨床意義，繁體中文，醫療術語保留英文]

🔗 [URL]

（每篇之間空一行分隔）

結尾：
━━━━━━━━━━━━━━━━━━━━
共 {n} 篇｜{date_str}

規則：
- ⭐⭐⭐ 給 RCT、重要 meta-analysis；⭐⭐ 給有臨床意義的觀察研究；⭐ 給其他
- 醫療術語、藥名、術式、縮寫、期刊名全部保留英文，不翻譯
- 📊 bullet points 用 • 開頭，列具體數值（p value、OR、HR、NNT 等）
- 直接輸出訊息本體，不加任何說明文字

文章資料：
{article_block}"""


def format_message(articles: list[dict], topic: dict, date_str: str, hot_theme: str | None = None) -> str:
    if not articles:
        return (
            f"🩺 麻醉科日報 {date_str}（{topic['day']}）\n"
            f"主題：{topic['name']}\n\n"
            "本週此領域尚無新文章。"
        )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1800,
        messages=[{"role": "user", "content": build_prompt(articles, topic, date_str, hot_theme)}],
    )
    return response.content[0].text.strip()


# ── 3. Split ──────────────────────────────────────────────────────────────────

def split_message(text: str) -> list[str]:
    """在文章邊界（### 開頭）切割，確保每則 ≤ MAX_CHARS。"""
    if len(text) <= MAX_CHARS:
        return [text]

    import re
    # 找每篇文章的起始位置（數字 emoji 開頭的行）
    boundary_positions = [m.start() for m in re.finditer(r"^[1-5]️⃣", text, re.MULTILINE)]

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
    weekday  = int(os.environ.get("FORCE_WEEKDAY", now_twn.isoweekday()))
    date_str = now_twn.strftime("%Y/%m/%d")

    if weekday not in TOPICS:
        print(f"今日為週末（{weekday}），不推送。")
        return

    topic = TOPICS[weekday]
    print(f"{date_str} {topic['day']} | 主題：{topic['name']}")

    articles, hot_theme = load_articles(weekday)
    print(f"文章數：{len(articles)} | 熱點：{hot_theme or '-'}")

    message = format_message(articles, topic, date_str, hot_theme)
    print(f"訊息字數：{len(message)}")

    parts = split_message(message)
    print(f"拆分為 {len(parts)} 則訊息")

    for i, part in enumerate(parts, 1):
        print(f"  推送第 {i}/{len(parts)} 則（{len(part)} 字）...")
        push_line(part)
        if i < len(parts):
            time.sleep(1)

    # 更新已推送文章記錄
    sent = load_sent_urls()
    sent.update(a["url"] for a in articles if a.get("url"))
    save_sent_urls(sent)
    print(f"已記錄 {len(articles)} 篇，累計 {len(sent)} 篇。")


if __name__ == "__main__":
    main()
