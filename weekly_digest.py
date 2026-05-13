"""
麻醉科週報自動化腳本
每週從五大期刊抓取最新文章，透過 Claude API 整理成週報，存入 Notion

抓取策略：
- Anesthesiology / A&A：NCBI E-utilities（不受 Cloudflare 封鎖）
- BJA：ScienceDirect RSS
- NEJM / JAMA：各自官方 RSS
"""

import anthropic
import requests
import json
import feedparser
import xml.etree.ElementTree as ET
import time
from datetime import datetime, timedelta
import os
import sys

# ── 設定 ──────────────────────────────────────────────────────────────────────
CLAUDE_API_KEY = os.environ["CLAUDE_API_KEY"]
NOTION_API_KEY = os.environ["NOTION_API_KEY"]
NOTION_PARENT_ID = "32fe77f4-b1f0-8049-9ecc-eb6a1a5d6a0f"  # 「麻醉週報」頁面 ID
REPORTED_FILE = "reported_articles.json"

# 使用 RSS 的期刊
RSS_FEEDS = {
    "British Journal of Anaesthesia": "https://rss.sciencedirect.com/publication/science/00070912",
    "NEJM": "https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss",
    "JAMA": "https://jamanetwork.com/rss/site_3/67.xml",
}

# 使用 NCBI E-utilities 的期刊（官網有 Cloudflare 封鎖）
PUBMED_JOURNALS = {
    "Anesthesiology": '"Anesthesiology"[Journal]',
    "Anesthesia & Analgesia": '"Anesthesia and Analgesia"[Journal]',
}

NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_HEADERS = {"User-Agent": "AnesthesiaDigestBot/1.0 (educational; contact: anesthesia-digest)"}


# ── 工具函數 ───────────────────────────────────────────────────────────────────

def load_reported():
    if os.path.exists(REPORTED_FILE):
        with open(REPORTED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"articles": []}


def save_reported(data):
    with open(REPORTED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_pubmed_journal(journal_name, search_term, max_results=25):
    """用 NCBI E-utilities 抓期刊最新文章（含摘要）"""
    articles = []
    try:
        # Step 1: esearch 取得最新 PMIDs
        r = requests.get(
            f"{NCBI_EUTILS}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": f"{search_term} AND hasabstract",
                "retmax": max_results,
                "retmode": "json",
                "sort": "pub date",
                "datetype": "pdat",
                "reldate": 35,  # 過去 35 天，確保涵蓋一週新文章
            },
            timeout=20,
            headers=NCBI_HEADERS,
        )
        ids = r.json()["esearchresult"]["idlist"]
        if not ids:
            print(f"  ✓ {journal_name}: 0 篇（近 35 天無新文章）")
            return articles

        # NCBI rate limit: 3 requests/sec without API key → 加間隔避免 throttle
        time.sleep(1)

        # Step 2: efetch 取得完整 XML（含摘要），最多重試一次
        for attempt in range(2):
            r2 = requests.get(
                f"{NCBI_EUTILS}/efetch.fcgi",
                params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
                timeout=30,
                headers=NCBI_HEADERS,
            )
            if r2.text.strip().startswith("<?xml") or r2.text.strip().startswith("<PubmedArticleSet"):
                break
            # 非 XML 回應（通常是 throttle error page），等待後重試
            print(f"  ⚠ {journal_name} efetch 非 XML 回應，重試中...", file=sys.stderr)
            time.sleep(3)
        root = ET.fromstring(r2.text)

        for art in root.findall(".//PubmedArticle"):
            pmid = art.findtext(".//PMID", "")
            title_el = art.find(".//ArticleTitle")
            title = "".join(title_el.itertext()) if title_el is not None else ""
            title = title.strip()

            # 跳過 erratum / correction（無摘要、無實質內容）
            pub_types = [el.text for el in art.findall(".//PublicationType")]
            if any(t in ["Published Erratum", "Retraction of Publication"] for t in pub_types if t):
                continue

            abstract_parts = ["".join(el.itertext()) for el in art.findall(".//AbstractText")]
            abstract = " ".join(abstract_parts)[:600]

            pub_date = art.findtext(".//PubDate/Year", "") + "年" + art.findtext(".//PubDate/Month", "")
            doi = art.findtext('.//ELocationID[@EIdType="doi"]', "")
            url = f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

            if title:
                articles.append({
                    "journal": journal_name,
                    "title": title,
                    "abstract": abstract,
                    "url": url,
                    "published": pub_date,
                    "uid": pmid,
                })

        print(f"  ✓ {journal_name}: {len(articles)} 篇")
    except Exception as e:
        print(f"  ✗ {journal_name} 抓取失敗: {e}", file=sys.stderr)
    return articles


def fetch_rss_journal(journal_name, url, max_results=25):
    """用 RSS feed 抓期刊最新文章"""
    articles = []
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        feed = feedparser.parse(r.content)
        for entry in feed.entries[:max_results]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            articles.append({
                "journal": journal_name,
                "title": title,
                "abstract": entry.get("summary", entry.get("description", ""))[:600],
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
                "uid": entry.get("id", entry.get("link", "")),
            })
        print(f"  ✓ {journal_name}: {len(feed.entries)} 篇")
    except Exception as e:
        print(f"  ✗ {journal_name} 抓取失敗: {e}", file=sys.stderr)
    return articles


def fetch_articles():
    """從各期刊抓取文章"""
    all_articles = []

    for journal_name, search_term in PUBMED_JOURNALS.items():
        all_articles.extend(fetch_pubmed_journal(journal_name, search_term))
        time.sleep(1)  # 各期刊之間額外間隔

    for journal_name, url in RSS_FEEDS.items():
        all_articles.extend(fetch_rss_journal(journal_name, url))

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
- 例如：regional anesthesia, nerve block, propofol, TIVA, ICU, PONV, sugammadex, rocuronium, opioid, epidural, RSI, TAP block, ESPB, spinal anesthesia, dexmedetomidine 等

## 本週新文章（共 {len(new_articles)} 篇）
{articles_block}

## 過去已報導過的文章（供跨期比較參考）
{prev_summary}

## 格式規則（非常重要，請嚴格遵守）

每篇文章用以下固定格式，**絕對不要使用 Markdown 表格（| 符號）**：

### [英文完整標題]
📍 期刊名 | YYYY年MM月 | 研究類型 | ⭐⭐⭐（或⭐⭐或⭐）
🔑 一句話重點：（繁體中文，醫學名詞保留英文，限 30 字內）
📊 主要發現：
- 發現 1（含具體數據）
- 發現 2
- 發現 3（選填）
💡 臨床意義：（繁體中文，1–2 句）
🔗 連結：URL
（若與過去報導有關）🔁 跨期比較：一兩句說明異同，標明哪一週

---

## 評分標準
- ⭐⭐⭐ 改變臨床實務 → 加入「本週必讀」區
- ⭐⭐ 值得了解
- ⭐ 有趣但影響較小

## 輸出結構（請完整輸出，不要截斷任何文章）

# 🩺 麻醉科週報 — {today_str}

> 本週涵蓋：Anesthesiology、Anesthesia & Analgesia、BJA、NEJM、JAMA
> 🔍 本週主題：[主題名稱]

---

## 📋 本週快覽
（列出所有推薦文章，格式：- ⭐⭐⭐ **標題縮寫** — 期刊 — 一句話重點）
（每篇一行，不用表格）

---

## 🎯 本週主題：[主題名稱]
[2–3 段主題介紹：為何重要、各期刊角度、臨床意義]

---

## 📌 本週必讀（⭐⭐⭐）
[所有 ⭐⭐⭐ 文章，每篇用上述固定格式]

---

## 其他重要文章

### Anesthesiology
[Anesthesiology 的 ⭐⭐ 文章]

### Anesthesia & Analgesia
[A&A 的 ⭐⭐ 文章]

### BJA
[BJA 的 ⭐⭐ 文章]

### NEJM
[NEJM 的 ⭐⭐ 文章]

### JAMA
[JAMA 的 ⭐⭐ 文章]

---

## 📊 本週統計
- 搜尋日期：{datetime.now().strftime('%Y-%m-%d')}
- 涵蓋期刊：5 本
- 新增文章：{len(new_articles)} 篇
- 推薦閱讀：X 篇（必讀 X 篇）

---

只輸出週報內容，不要加其他說明。每篇文章都要完整輸出，不可截斷。"""

    print("呼叫 Claude API 分析文章...")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ── Notion 建立頁面 ────────────────────────────────────────────────────────────

def parse_inline(text):
    """把 **bold** 轉成 Notion rich_text 陣列，保留其他文字原樣"""
    import re
    parts = []
    for seg in re.split(r"(\*\*(?:[^*]|\*(?!\*))+\*\*)", text):
        if not seg:
            continue
        if seg.startswith("**") and seg.endswith("**") and len(seg) > 4:
            parts.append({
                "type": "text",
                "text": {"content": seg[2:-2][:1990]},
                "annotations": {"bold": True},
            })
        else:
            # 每個純文字段不超過 1990 字
            for i in range(0, len(seg), 1990):
                parts.append({"type": "text", "text": {"content": seg[i:i+1990]}})
    return parts or [{"type": "text", "text": {"content": text[:1990]}}]


def split_text_blocks(text, block_type, block_key):
    """長文字切分成多個相同類型的 block（Notion 單一 rich_text 上限 2000 字）"""
    blocks = []
    # 切成最多 1990 字的段落，優先在句號或逗號處斷行
    while text:
        if len(text) <= 1990:
            chunk, text = text, ""
        else:
            cut = 1990
            for punct in ["。", "；", "，", ". ", " "]:
                idx = text.rfind(punct, 0, 1990)
                if idx > 800:
                    cut = idx + len(punct)
                    break
            chunk, text = text[:cut], text[cut:].lstrip()
        blocks.append({
            "object": "block",
            "type": block_type,
            block_key: {"rich_text": parse_inline(chunk)},
        })
    return blocks


def md_to_blocks(text):
    """把 Markdown 文字轉換成 Notion block 格式"""
    blocks = []
    for line in text.split("\n"):
        s = line.rstrip()

        if s.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1",
                "heading_1": {"rich_text": parse_inline(s[2:])}})

        elif s.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                "heading_2": {"rich_text": parse_inline(s[3:])}})

        elif s.startswith("### "):
            title = s[4:]
            # ⭐⭐⭐ 文章或必讀 → callout（橘色背景，在 iPhone 上明顯）
            if "⭐⭐⭐" in title or title.startswith("📌"):
                blocks.append({"object": "block", "type": "callout",
                    "callout": {
                        "rich_text": parse_inline(title),
                        "icon": {"type": "emoji", "emoji": "📌"},
                        "color": "orange_background",
                    }})
            else:
                blocks.append({"object": "block", "type": "heading_3",
                    "heading_3": {"rich_text": parse_inline(title)}})

        elif s.startswith("- ") or s.startswith("* "):
            content = s[2:]
            # 以 emoji 開頭的 label 行（🔑/📊/💡/🔗/🔁/📍）→ 特別標示
            if content and content[0] in "📍🔑📊💡🔗🔁⭐":
                blocks.extend(split_text_blocks(content, "bulleted_list_item", "bulleted_list_item"))
            else:
                blocks.extend(split_text_blocks(content, "bulleted_list_item", "bulleted_list_item"))

        elif s == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})

        elif s.startswith("> "):
            content = s[2:]
            blocks.extend(split_text_blocks(content, "quote", "quote"))

        elif s:
            # 以 emoji label 開頭的獨立行（📍/🔑/📊/💡/🔗）→ 用 quote block 突顯
            if s and s[0] in "📍🔑📊💡🔗🔁":
                blocks.extend(split_text_blocks(s, "quote", "quote"))
            else:
                blocks.extend(split_text_blocks(s, "paragraph", "paragraph"))

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
