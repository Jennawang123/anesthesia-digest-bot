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
    "PAIN": '0304-3959[ISSN] OR 1872-6623[ISSN]',
    "Anaesthesia": '"Anaesthesia"[Journal]',
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


def fetch_pubmed_journal(journal_name, search_term, max_results=60):
    """用 NCBI E-utilities 抓期刊最新文章（含摘要）"""
    articles = []
    try:
        # 用月份範圍而非 reldate：捕捉 epub-ahead 文章（可能 epub 早幾個月但本月才出刊）
        # 查當月 + 前兩個月；deduplication 會過濾已報導過的文章
        today = datetime.now()
        two_months_ago = today.replace(day=1)
        for _ in range(2):
            two_months_ago = (two_months_ago - timedelta(days=1)).replace(day=1)
        mindate = two_months_ago.strftime("%Y/%m")
        maxdate = today.strftime("%Y/%m")

        # Step 1: esearch 取得最新 PMIDs
        r = requests.get(
            f"{NCBI_EUTILS}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": f"{search_term} AND hasabstract AND (\"{mindate}\"[pdat]:\"{maxdate}\"[pdat])",
                "retmax": max_results,
                "retmode": "json",
                "sort": "pub date",
            },
            timeout=20,
            headers=NCBI_HEADERS,
        )
        ids = r.json()["esearchresult"]["idlist"]
        if not ids:
            print(f"  ✓ {journal_name}: 0 篇（{mindate}–{maxdate} 無新文章）")
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

## ⚠️ 格式規則（違反即重做）

禁止事項：
- 禁止使用 Markdown 表格（含 `|` 符號的任何格式）
- 禁止使用 `**欄位名稱**：` 的 bold label 格式
- 禁止截斷文章

每篇文章必須嚴格使用以下格式（以下是一個完整範例，請照抄結構）：

---範例開始---
### Remimazolam versus Propofol for Sedation of Mechanically Ventilated Patients
📍 Anesthesiology | 2026年04月 | Phase 3 RCT | ⭐⭐⭐
🔑 Remimazolam tosylate 在 ICU 機械通氣鎮靜的療效與安全性不劣於 propofol
📊 主要發現：
- Sedation success rate：remimazolam 87.3% vs propofol 84.1%（非劣效達標）
- 低血壓發生率顯著較低（23% vs 41%，p<0.001）
- 嗜伊紅球增多症（eosinophilia）為 remimazolam 特有副作用，發生率 8%
💡 臨床意義：對低血壓高風險病患（septic shock、心衰）提供 propofol 以外的選擇；eosinophilia 需納入監測。
🔗 https://doi.org/10.1097/ALN.0000000000006000
---範例結束---

每個欄位（📍🔑📊💡🔗）都是獨立一行，不用 bullet point 前置，不用 **bold**。
📊 下面的發現用 bullet（`- `）列出。

## 評分標準
- ⭐⭐⭐ 改變臨床實務 → 加入「本週必讀」區
- ⭐⭐ 值得了解
- ⭐ 有趣但影響較小

## 跨期刊熱點偵測（重要）
閱讀完所有文章後，判斷本週是否有 **同一主題在 2 本以上期刊各有文章**。
常見熱點主題例如：opioid-sparing anesthesia、PONV、regional anesthesia、airway management、perioperative cardiac risk、neuraxial anesthesia、dexmedetomidine、sugammadex、multimodal analgesia 等。
- 若有：在輸出中加入「🔥 跨期刊熱點」section（格式見下方輸出結構）
- 若無：完全省略該 section，不留空白標題

## 詳細摘要數量限制（重要）
- ⭐⭐⭐ 文章：**全部**寫詳細摘要（預計 3–5 篇）
- ⭐⭐ 文章：精選最重要的 **4–6 篇**寫詳細摘要，其餘只列在快覽
- ⭐ 文章：**只出現在快覽**，不寫詳細摘要
- 詳細摘要總數：**最多 10 篇**

## 輸出結構（請完整輸出每篇選定的詳細摘要）

# 🩺 麻醉科週報 — {today_str}

> 本週涵蓋：Anesthesiology、Anesthesia & Analgesia、Anaesthesia、BJA、NEJM、JAMA
> 🔍 本週主題：[主題名稱]

---

## 📋 本週快覽
（所有推薦文章，每篇一行：`- ⭐⭐⭐ 標題縮寫 — 期刊 — 一句話重點`）
（⭐ 文章也列在此，但不寫詳細摘要）

---

## 🎯 本週主題：[主題名稱]
[2–3 段主題介紹]

---

## 📌 本週必讀（⭐⭐⭐）
[所有 ⭐⭐⭐ 文章，每篇照範例格式，完整輸出]

---

## 其他重要文章

### Anesthesiology
[精選 ⭐⭐ 文章，照範例格式，完整輸出]

### Anesthesia & Analgesia
[精選 ⭐⭐ 文章，照範例格式，完整輸出]

### Anaesthesia
[精選 ⭐⭐ 文章，照範例格式，完整輸出]

### BJA
[精選 ⭐⭐ 文章，照範例格式，完整輸出]

### NEJM
[精選 ⭐⭐ 文章，照範例格式，完整輸出]

### JAMA
[精選 ⭐⭐ 文章，照範例格式，完整輸出]

---

## 🔥 跨期刊熱點（若本週有符合條件則輸出，否則省略整個 section）
主題：[e.g. Opioid-sparing anesthesia]
[一段話說明為何這個主題本週跨期刊出現、臨床背景]
各期刊觀點：
- [期刊名]：[研究設計] — [一句話結論]
- [期刊名]：[研究設計] — [一句話結論]
💬 比較：[各期刊研究設計差異、結論是否一致、對臨床實務的綜合啟示]

---

## 📊 本週統計
- 搜尋日期：{datetime.now().strftime('%Y-%m-%d')}
- 涵蓋期刊：5 本
- 新增文章：{len(new_articles)} 篇
- 詳細摘要：X 篇（必讀 X 篇）

---

只輸出週報，不加說明。選定的每篇文章必須完整輸出，不可截斷。"""

    print("呼叫 Claude API 分析文章...")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
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
