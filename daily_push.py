#!/usr/bin/env python3
"""
週一至週五 09:00 TWN 執行。
讀取 daily_data/week.json，格式化當日日報後推送至 LINE 群組。
若單則訊息超過 4800 字，自動接力拆分。
"""

import json
import os
import random
import re
import time
import xml.etree.ElementTree as ET
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

MIN_TOP_SCORE = 5  # 當日最高分低於此值就只推清單，不做摘要（避免無材料硬湊）

# PMC Open Access 全文（實測約 5 篇有 1 篇拿得到；其餘只有結構化摘要）
PMC_MAX_CHARS       = 15000  # 單篇全文最多送給模型的字元數（約 3.7k tokens）
PMC_TOTAL_MAX_CHARS = 45000  # 單日全文總量上限，避免 token 成本失控
NCBI_UA = {"User-Agent": "anesthesia-digest-bot/1.0 (mailto:jennawang123@gmail.com)"}


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


# ── 2. Daily Quote ────────────────────────────────────────────────────────────

QUOTE_PROMPT = """Write one short quote for an anesthesia resident at the start of their workday.

Tone: like a confident senior speaking to a junior — direct, grounded, no drama.
Theme: curiosity, learning, growth as a clinician. NOT about surviving hardship or enduring pain.
Style: actionable or specific mindset shift. NOT generic affirmation.

Language: randomly alternate between English and Traditional Chinese (繁體中文). Some days English, some days Chinese — vary it naturally, not by any fixed pattern.

Good examples (English):
- "You're not expected to know everything — you're expected to grow."
- "Don't be afraid to ask 'why' or 'what if.' Senior residents and attendings respect curiosity."
- "Every case you haven't seen before is the point — not the problem."

Good examples (Chinese):
- 「不懂就問，這才是住院醫師該做的事。」
- 「今天遇到的陌生情況，就是你來這裡的原因。」
- 「問出好問題，比答對所有問題更難，也更值得。」

Bad examples (do not write like this):
- "Every tired night is proof of your growth." (dramatic, vague)
- "You're stronger than you think." (generic affirmation)
- 「每個疲憊都是成長的印記。」(雞湯，空洞)

Output only the quote. No title, no explanation, no quote marks."""

# 心情小語只是裝飾，API 失敗時退回本地清單，不可讓整份日報開天窗
QUOTE_FALLBACKS = [
    "不懂就問，這才是住院醫師該做的事。",
    "今天遇到的陌生情況，就是你來這裡的原因。",
    "問出好問題，比答對所有問題更難，也更值得。",
    "You're not expected to know everything — you're expected to grow.",
    "Every case you haven't seen before is the point — not the problem.",
    "Don't be afraid to ask 'why' or 'what if.' Curiosity is the job.",
]


def get_daily_quote() -> str:
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=100,
            messages=[{"role": "user", "content": QUOTE_PROMPT}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"  ⚠️ 心情小語 API 失敗（{type(e).__name__}: {e}），改用本地語錄")
        return random.choice(QUOTE_FALLBACKS)


# ── 2.5 全文（PMC Open Access）─────────────────────────────────────────────────

def _article_pmid(article: dict) -> str | None:
    if article.get("pmid"):
        return str(article["pmid"])
    m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", article.get("url", ""))
    return m.group(1) if m else None


def _pmids_to_pmcids(pmids: list[str]) -> dict[str, str]:
    """NCBI ID Converter：PMID → PMCID。沒有 PMCID 的就不會出現在回傳值裡。"""
    if not pmids:
        return {}
    resp = requests.get(
        "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/",
        params={
            "ids": ",".join(pmids),
            "format": "json",
            "tool": "anesthesia-digest-bot",
            "email": "jennawang123@gmail.com",
        },
        headers=NCBI_UA,
        timeout=30,
    )
    resp.raise_for_status()
    # 注意：這支 API 的 pmid 有時回整數、有時回字串，一律轉成字串才對得上
    return {
        str(rec["pmid"]): rec["pmcid"]
        for rec in resp.json().get("records", [])
        if rec.get("pmid") and rec.get("pmcid")
    }


def _fetch_pmc_body(pmcid: str) -> str | None:
    """有 PMCID 不等於拿得到全文——只有 OA 子集的 efetch 才會回 <body>。"""
    resp = requests.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
        params={"db": "pmc", "id": pmcid, "retmode": "xml"},
        headers=NCBI_UA,
        timeout=60,
    )
    resp.raise_for_status()
    body = ET.fromstring(resp.content).find(".//body")
    if body is None:
        return None
    text = re.sub(r"\s+", " ", " ".join(body.itertext())).strip()
    return text or None


def attach_fulltext(articles: list[dict]) -> int:
    """就地為文章補上 a['fulltext']。任何失敗都只是少了全文，不影響推送。"""
    pmid_map = {p: a for a in articles if (p := _article_pmid(a))}
    if not pmid_map:
        return 0

    try:
        pmcids = _pmids_to_pmcids(list(pmid_map))
    except Exception as e:
        print(f"  ⚠️ PMCID 查詢失敗（{type(e).__name__}: {e}），本次全部只用摘要")
        return 0

    used, hits = 0, 0
    # 以文章為主迴圈：ID Converter 可能回傳我們沒問過的 pmid（改版／合併紀錄）
    for pmid, article in pmid_map.items():
        pmcid = pmcids.get(pmid)
        if not pmcid:
            continue
        if used >= PMC_TOTAL_MAX_CHARS:
            print("  ℹ️ 已達單日全文總量上限，其餘文章只用摘要")
            break
        try:
            body = _fetch_pmc_body(pmcid)
        except Exception as e:
            print(f"    ⚠️ {pmcid} 全文抓取失敗（{type(e).__name__}）")
            continue
        if not body:
            continue
        excerpt = body[:PMC_MAX_CHARS]
        article["fulltext"] = excerpt
        used += len(excerpt)
        hits += 1
        time.sleep(0.4)  # NCBI 無金鑰時的節流

    print(f"  全文取得：{hits}/{len(pmid_map)} 篇（{len(pmcids)} 篇有 PMCID）")
    return hits


# ── 3. Format ─────────────────────────────────────────────────────────────────

def build_prompt(articles: list[dict], topic: dict, date_str: str, hot_theme: str | None = None) -> str:
    blocks = []
    for i, a in enumerate(articles):
        block = (
            f"[{i+1}] 《{a['journal']}》\n"
            f"標題：{a['title']}\n"
            f"發表日期：{a.get('pub_date') or '未知'}\n"
            f"摘要：{a['abstract']}\n"
            f"連結：{a['url']}"
        )
        if a.get("fulltext"):
            block += f"\n【本篇有 PMC 全文，以下為全文內容，請優先根據它抓數據】\n{a['fulltext']}"
        blocks.append(block)
    article_block = "\n\n".join(blocks)

    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    n = len(articles)

    # 熱點是「本週該主題跨期刊」層級的訊號，當日入選文章未必涵蓋它，
    # 因此交給模型判斷是否輸出，避免出現熱點與內文無關的情況
    hot_line = (
        f"\n🔥 本週熱點：{hot_theme}"
        "（僅當下方入選文章至少一篇確實屬於此主題時才輸出這一行，否則整行省略）"
        if hot_theme else ""
    )

    return f"""你是麻醉科日報編輯，請將以下文章整理成 LINE 推播日報。

開頭固定格式：
🩺 麻醉科日報 {date_str}（{topic['day']}）
主題：{topic['name']}{hot_line}
━━━━━━━━━━━━━━━━━━━━

每篇文章格式（依序用 {" ".join(number_emojis[:n])} 編號，嚴格照此結構，不可有 ### 或 > 符號）：

[數字emoji] [完整英文標題]

📍 [期刊名] | [發表年月，直接用資料中的發表日期，格式：YYYY年Mon，若未知則寫「-」，絕對不可自行推測] | [研究設計] | [⭐星級] | [資料來源：有附全文的寫「全文」，只有摘要的寫「摘要」]

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
- 專有名詞若非全科通識（如 NephroCheck、MAKE、TEG 等），首次出現時括號補充一句中文解釋，例如：NephroCheck（尿液 TIMP-2×IGFBP7 biomarker 用於 AKI 預測）
- 📊 bullet points 用 • 開頭，必須列出具體數值（p value、OR、HR、NNT、%、n 數等）或具體介入內容（例：限制術中 IV fluid ≤3 mL/kg/hr、使用 goal-directed therapy protocol）；禁止使用空洞描述如「有效改善」、「結果顯著」、「策略有效」
- 附有全文的文章：必須從全文的 Methods / Results 段抓出實際數據（樣本數、主要終點數值、效果量、信賴區間、p value），這種情況下絕對不可以寫「需查閱全文」；guideline 有全文時要直接列出具體建議條文（例：建議 X 情況下使用 Y，證據等級 Z）
- 只有摘要、且摘要本身沒有具體數據或條文（常見於 guideline update、editorial、correspondence），就**只寫摘要真的講了什麼**，並在最後一點明寫「摘要未列出具體建議條文，需查閱全文」。寧可只有 1 點，也不可以把標題換句話說來湊成 3 點——例如「針對 X 提出更新建議」「強調標準化流程」這種只是複述標題、沒有任何新資訊的句子，一律不准出現
- 同理，💡 臨床意義若摘要不足以支撐具體建議，就寫清楚「需取得全文才能判斷實務調整方向」，不要生出看似有指引性但其實空洞的句子
- 🔑 一句話核心發現必須說清楚：誰、做了什麼、結果如何（含數字或方向），例：「HES vs crystalloid 在腹部手術 meta-analysis 中顯示術後 AKI 風險無顯著差異（OR 1.08, 95%CI 0.91–1.28）」
- 💡 臨床意義必須直接說出結論或建議，不可寫「提供依據」、「有助於重新評估」、「為臨床醫師提供參考」等後設評論；要說清楚：應該怎麼做、用或不用、改變什麼
- 直接輸出訊息本體，不加任何說明文字

文章資料：
{article_block}"""


def plain_message(
    articles: list[dict],
    topic: dict,
    date_str: str,
    hot_theme: str | None = None,
    note: str = "（摘要生成暫時無法使用，先附上原文連結）",
) -> str:
    """不經 LLM 的精簡版本：標題＋期刊＋連結。用於 API 失敗，或當日文獻不值得做完整摘要。"""
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    hot_line = f"\n🔥 本週熱點：{hot_theme}" if hot_theme else ""

    header = (
        f"🩺 麻醉科日報 {date_str}（{topic['day']}）\n"
        f"主題：{topic['name']}{hot_line}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    blocks = [
        f"{number_emojis[i]} {a['title']}\n\n"
        f"📍 {a['journal']} | {a.get('pub_date') or '-'}\n\n"
        f"🔗 {a['url']}"
        for i, a in enumerate(articles[:len(number_emojis)])
    ]
    footer = f"━━━━━━━━━━━━━━━━━━━━\n共 {len(articles)} 篇｜{date_str}\n{note}"

    return "\n\n".join([header, *blocks, footer])


def format_message(articles: list[dict], topic: dict, date_str: str, hot_theme: str | None = None) -> str:
    if not articles:
        return (
            f"🩺 麻醉科日報 {date_str}（{topic['day']}）\n"
            f"主題：{topic['name']}\n\n"
            "本週此領域尚無新文章。"
        )

    # 當日候選全是低分文獻（常見於候選池被已推送文章耗盡時），
    # 與其讓模型從沒有數據的 abstract 硬擠出摘要，不如誠實給清單
    top_score = max((a.get("score", 0) for a in articles), default=0)
    if top_score < MIN_TOP_SCORE:
        print(f"  ℹ️ 當日最高分僅 {top_score}（門檻 {MIN_TOP_SCORE}），改推精簡清單，不做摘要")
        # 這條路徑沒有模型可判斷熱點是否切題，直接不印，免得又出現熱點與內文無關
        return plain_message(
            articles, topic, date_str, hot_theme=None,
            note="（今日無達到報導門檻的新文獻，僅列標題與連結供快速掃描）",
        )

    try:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=3500,
            thinking={"type": "disabled"},
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": build_prompt(articles, topic, date_str, hot_theme)}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"  ⚠️ 日報格式化 API 失敗（{type(e).__name__}: {e}），改推純文字清單")
        return plain_message(articles, topic, date_str, hot_theme)


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
    weekday  = int(os.environ.get("FORCE_WEEKDAY") or now_twn.isoweekday())
    date_str = now_twn.strftime("%Y/%m/%d")

    if weekday not in TOPICS:
        print(f"今日為週末（{weekday}），不推送。")
        return

    topic = TOPICS[weekday]
    print(f"{date_str} {topic['day']} | 主題：{topic['name']}")

    articles, hot_theme = load_articles(weekday)
    print(f"文章數：{len(articles)} | 熱點：{hot_theme or '-'}")

    if articles:
        try:
            attach_fulltext(articles)
        except Exception as e:
            print(f"  ⚠️ 全文補抓整體失敗（{type(e).__name__}: {e}），改用摘要")

    quote = get_daily_quote()
    print(f"心情小語：{quote}")

    message = format_message(articles, topic, date_str, hot_theme)
    message = f"💬 {quote}\n\n{message}"
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
