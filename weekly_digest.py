"""
麻醉科週報自動化腳本
每週從五大期刊 RSS feed 抓取最新文章，透過 Claude API 整理成週報，存入 Notion
"""

import anthropic
import requests
import json
import feedparser
from datetime import datetime, timedelta
import os
import sys

# ── 設定 ──────────────────────────────────────────────────────────────────────
CLAUDE_API_KEY = os.environ["CLAUDE_API_KEY"]
NOTION_API_KEY = os.environ["NOTION_API_KEY"]
NOTION_PARENT_ID = "32fe77f4-b1f0-8049-9ecc-eb6a1a5d6a0f"  # 「麻醉週報」頁面 ID
REPORTED_FILE = "reported_articles.json"

JOURNAL_FEEDS = {
    "Anesthesiology": "https://pubs.asahq.org/rss/site_1/1.xml",
    "Anesthesia & Analgesia": "https://journals.lww.com/anesthesia-analgesia/rss/current",
    "British Journal of Anaesthesia": "https://www.bjanaesthesia.org/feed/rss",
    "NEJM": "https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss",
    "JAMA": "https://jamanetwork.com/rss/site_3/67.xml",
}


# ── 工具函數 ───────────────────────────────────────────────────────────────────

def load_reported():
    if os.path.exists(REPORTED_FILE):
        with open(REPORTED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"articles": []}


def save_reported(data):
    with open(REPORTED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_articles():
    """從各期刊 RSS feed 抓取文章"""
    all_articles = []
    for journal, url in JOURNAL_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:25]:
                all_articles.append({
                    "journal": journal,
                    "title": entry.get("title", "").strip(),
                    "abstract": entry.get("summary", entry.get("description", ""))[:600],
                    "url": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "uid": entry.get("id", entry.get("link", "")),
                })
            print(f"  ✓ {journal}: {len(feed.entries)} 篇")
        except Exception as e:
            print(f"  ✗ {journal} 抓取失敗: {e}", file=sys.stderr)
    return all_articles


def deduplicate(articles, reported_data):
    """過濾掉已報導過的文章"""
    reported_titles = {a["title"].lower() for a in reported_data.get("articles", [])}
    reported_urls = {a.get("url", "").lower() for a in reported_data.get("articles", [])}
    new = [
        a for a in articles
        if a["title"].lower() not in reported_titles
        and a["url"].lower() not in reported_urls
        and a["title"]  # 排除空標題
    ]
    print(f"去重後剩 {len(new)} 篇（排除 {len(articles) - len(new)} 篇重複）")
    return new


def previous_titles_summary(reported_data):
    """把近期報導過的標題整理成一段文字，讓 Claude 做跨期比較"""
    recent = reported_data.get("articles", [])[-30:]
    if not recent:
        return "（第一期，無過去紀錄）"
    lines = [f"- {a['title']} ({a['journal']}, {a.get('reported_date', '')})" for a in recent]
    return "\n".join(lines)


# ── Claude 分析 ────────────────────────────────────────────────────────────────

def analyze_with_claude(new_articles, prev_summary):
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    today_str = datetime.now().strftime("%Y年%m月%d日")

    articles_block = ""
    for i, a in enumerate(new_articles, 1):
        articles_block += (
            f"\n[{i}] {a['journal']} | {a['published']}\n"
            f"Title: {a['title']}\n"
            f"Abstract: {a['abstract'] or 'N/A'}\n"
            f"URL: {a['url']}\n"
        )

    prompt = f"""你是幫麻醉科住院醫師整理最新文獻的助理，今天要產出 {today_str} 的週報。

## 語言規則
- 說明文字用繁體中文
- 醫學術語、藥名、術式、期刊名稱一律保留英文，不翻譯
- 例如：regional anesthesia, nerve block, propofol, TIVA, ICU, PONV, sugammadex, rocuronium, opioid, epidural, RSI, TAP block, ESPB, fascial plane block, laryngoscopy, spinal anesthesia, dexmedetomidine 等

## 本週新文章（共 {len(new_articles)} 篇）
{articles_block}

## 過去已報導過的文章（供跨期比較參考）
{prev_summary}

## 任務

1. **找出本週主題**：從這批文章找 1–2 個核心熱點（多本期刊同時關注、重要 RCT/meta-analysis、新 guideline、或某本期刊的主打文章）

2. **選出 6–12 篇最重要的文章寫摘要**，格式：
   **[英文標題]**
   - **期刊**：Journal | 發表時間：YYYY年MM月 | 研究類型 | ⭐⭐⭐
   - **一句話重點**：（繁體中文，醫學名詞保留英文）
   - **主要發現**：2–3 點（繁體中文）
   - **臨床意義**：1–2 句（繁體中文）
   - **連結**：URL
   （若與過去報導有關，加上）🔁 **與過去報導比較**：一兩句說明異同，標明哪一週

3. **評分**：⭐⭐⭐ 改變臨床實務 / ⭐⭐ 值得了解 / ⭐ 有趣但影響較小。⭐⭐⭐ 標記「必讀」

4. 輸出完整週報，結構如下：

---
# 🩺 麻醉科週報 — {today_str}

> 本週涵蓋：Anesthesiology、Anesthesia & Analgesia、BJA、NEJM、JAMA
> 🔍 本週主題：[主題名稱]

---

## 📌 本週必讀（⭐⭐⭐）
[必讀文章：標題、期刊、發表時間、一句話重點]

---

## 🎯 本週主題：[主題名稱]
[2–3 段主題介紹：為何這個主題現在重要、各期刊的角度、對臨床的意義]

### 主題相關文章
[相關文章摘要]

---

## 其他重要文章
[其餘文章，依期刊分組]

---

## 📊 本週統計
- 搜尋日期：{datetime.now().strftime('%Y-%m-%d')}
- 涵蓋期刊：5 本
- 新增文章：{len(new_articles)} 篇
- 推薦閱讀：X 篇（其中必讀 X 篇）
---

只輸出週報內容，不要加其他說明。"""

    print("呼叫 Claude API 分析文章...")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ── Notion 建立頁面 ────────────────────────────────────────────────────────────

def md_to_blocks(text):
    """把 Markdown 文字轉換成 Notion block 格式"""
    blocks = []
    for line in text.split("\n"):
        stripped = line.rstrip()
        if stripped.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1",
                           "heading_1": {"rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]}})
        elif stripped.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": [{"type": "text", "text": {"content": stripped[3:]}}]}})
        elif stripped.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                           "heading_3": {"rich_text": [{"type": "text", "text": {"content": stripped[4:]}}]}})
        elif stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]}})
        elif stripped == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif stripped.startswith("> "):
            blocks.append({"object": "block", "type": "quote",
                           "quote": {"rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]}})
        elif stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": [{"type": "text", "text": {"content": stripped},
                                                        "annotations": {"bold": True}}]}})
        elif stripped:
            # 截斷過長的段落（Notion 單一 rich_text 上限 2000 字）
            content = stripped[:1990]
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]}})
    return blocks


def create_notion_page(title, markdown_content):
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    blocks = md_to_blocks(markdown_content)
    first_100 = blocks[:100]
    rest = blocks[100:]

    payload = {
        "parent": {"page_id": NOTION_PARENT_ID},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": title}}]}
        },
        "children": first_100,
    }

    resp = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"建立 Notion 頁面失敗 ({resp.status_code}): {resp.text}")

    page_id = resp.json()["id"]
    page_url = resp.json().get("url", "")

    # 分批附加剩餘 block
    for i in range(0, len(rest), 100):
        batch = rest[i : i + 100]
        requests.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=headers,
            json={"children": batch},
        )

    return page_url


# ── 主程式 ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n🩺 麻醉科週報開始執行 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    reported = load_reported()

    print("\n📡 抓取期刊 RSS...")
    all_articles = fetch_articles()
    print(f"共抓到 {len(all_articles)} 篇")

    new_articles = deduplicate(all_articles, reported)
    if len(new_articles) < 3:
        print("新文章不足 3 篇，本週跳過。")
        return

    prev_summary = previous_titles_summary(reported)
    digest = analyze_with_claude(new_articles, prev_summary)

    today = datetime.now()
    page_title = f"📋 {today.strftime('%Y年%m月%d日')} 週報"
    print(f"\n📝 建立 Notion 頁面：{page_title}")
    page_url = create_notion_page(page_title, digest)
    print(f"✅ 完成！{page_url}")

    # 更新已報導清單
    for a in new_articles:
        reported["articles"].append({
            "title": a["title"],
            "url": a["url"],
            "journal": a["journal"],
            "reported_date": today.strftime("%Y-%m-%d"),
        })

    # 只保留最近 180 天，避免檔案無限增大
    cutoff = (today - timedelta(days=180)).strftime("%Y-%m-%d")
    reported["articles"] = [
        a for a in reported["articles"]
        if a.get("reported_date", "2000-01-01") >= cutoff
    ]
    save_reported(reported)
    print("📁 reported_articles.json 已更新")


if __name__ == "__main__":
    main()
