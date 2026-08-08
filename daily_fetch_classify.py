#!/usr/bin/env python3
"""
週一 08:45 TWN 執行。
從五大麻醉期刊抓最新文章，用 Claude Haiku 批次分類後存入 daily_data/week.json。
"""

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import feedparser
import requests
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])

TOPICS = {
    "1": {"name": "重症醫學",       "day": "週一"},
    "2": {"name": "疼痛與區域麻醉", "day": "週二"},
    "3": {"name": "一般麻醉與神經麻醉", "day": "週三"},
    "4": {"name": "小兒與產科麻醉", "day": "週四"},
    "5": {"name": "心臟麻醉",       "day": "週五"},
}

ERRATA_KEYWORDS = ("erratum", "correction", "retraction", "corrigendum")

MIN_ARTICLES = 20  # 有來源失敗時，低於此數就不覆蓋既有 week.json


# ── 1. Fetch ──────────────────────────────────────────────────────────────────

def _get_with_retry(url: str, params: dict, timeout: int, attempts: int = 3):
    """NCBI 偶爾會在傳輸中途斷線（ChunkedEncodingError），重試兩次再放棄。"""
    for i in range(attempts):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if i == attempts - 1:
                raise
            wait = 2 ** i
            print(f"    ⚠️ 連線失敗（{type(e).__name__}），{wait}s 後重試（{i + 2}/{attempts}）")
            time.sleep(wait)


def fetch_ncbi(query_term: str, journal_label: str, days_back: int = 30) -> list[dict]:
    today = datetime.now(timezone.utc)
    start = (today - timedelta(days=days_back)).strftime("%Y/%m/%d")
    end   = today.strftime("%Y/%m/%d")

    search = _get_with_retry(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={
            "db": "pubmed",
            "term": f'{query_term} AND ("{start}"[PDAT]:"{end}"[PDAT])',
            "retmax": 30,
            "retmode": "json",
            "sort": "pub date",
        },
        timeout=30,
    )
    pmids = search.json().get("esearchresult", {}).get("idlist", [])
    print(f"    [{journal_label}] PMIDs found: {len(pmids)}")
    if not pmids:
        return []

    time.sleep(0.4)

    fetch = _get_with_retry(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
        params={
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "abstract",
            "retmode": "xml",
        },
        timeout=60,
    )

    articles = []
    root = ET.fromstring(fetch.content)
    for art in root.findall(".//PubmedArticle"):
        title = art.findtext(".//ArticleTitle") or ""
        if any(kw in title.lower() for kw in ERRATA_KEYWORDS):
            continue

        # 結構化摘要在 XML 裡是多個 AbstractText（PURPOSE / METHODS / RESULTS /
        # CONCLUSION），只取 find() 的第一個等於丟掉所有數據，只留下研究動機。
        # 另外 .text 會漏掉巢狀標記（如 <i>），必須用 itertext()。
        parts = []
        for el in art.findall(".//AbstractText"):
            text = "".join(el.itertext()).strip()
            if not text:
                continue
            label = el.get("Label") or el.get("NlmCategory")
            parts.append(f"{label}: {text}" if label else text)
        abstract = " ".join(parts)
        if not abstract:
            continue

        pmid = art.findtext(".//PMID") or ""

        year  = art.findtext(".//PubDate/Year") or art.findtext(".//PubDate/MedlineDate", "")[:4] or ""
        month = art.findtext(".//PubDate/Month") or ""
        pub_date = f"{year}/{month}" if month else year

        articles.append({
            "title":    title,
            "abstract": abstract[:2500],   # 結構化摘要含 RESULTS 段，500 字會攔腰截斷
            "pmid":     pmid,
            "journal":  journal_label,
            "pub_date": pub_date,
            "url":      f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        })

    return articles


def fetch_rss(url: str, journal: str) -> list[dict]:
    feed = feedparser.parse(url)
    articles = []
    for entry in feed.entries[:20]:
        title = entry.get("title", "")
        if any(kw in title.lower() for kw in ERRATA_KEYWORDS):
            continue

        raw = ""
        if hasattr(entry, "summary"):
            raw = entry.summary
        elif hasattr(entry, "content") and entry.content:
            raw = entry.content[0].value

        abstract = re.sub(r"<[^>]+>", " ", raw).strip()
        if len(abstract) < 50:
            continue

        pub_date = ""
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            import time as _time
            t = entry.published_parsed
            pub_date = f"{t.tm_year}/{_time.strftime('%b', t)}"

        articles.append({
            "title":    title,
            "abstract": abstract[:500],
            "journal":  journal,
            "pub_date": pub_date,
            "url":      entry.get("link", ""),
        })

    return articles[:15]


# ── 2. Classify ───────────────────────────────────────────────────────────────

BATCH_SIZE = 60  # max articles per Haiku call


def _call1_batch(articles: list[dict], offset: int) -> tuple[dict[str, list[int]], dict[int, int]]:
    """對單一批次（最多 BATCH_SIZE 篇）執行分類+評分，回傳全域 1-based index。"""
    numbered = "\n".join(
        f"{offset+i+1}. [{a['journal']}] {a['title']} | {a['abstract'][:200]}"
        for i, a in enumerate(articles)
    )
    start_idx = offset + 1
    end_idx   = offset + len(articles)

    prompt = f"""You are an anesthesia research classifier.

Fixed topics:
1: Critical care / ICU / vasopressor / ARDS / sepsis / mechanical ventilation / hemodynamics
2: Pain / Regional anesthesia / nerve block / opioid / epidural / spinal / CRPS / analgesic
3: General anesthesia / Airway / PONV / propofol / volatile / neuromuscular / Neuroanesthesia / ICP / TBI / craniotomy
4: Pediatric anesthesia / Obstetric anesthesia / neonatal / infant / labor / cesarean / maternal
5: Cardiac anesthesia / cardiac surgery / CPB / TAVI / TAVR / ECMO / valve / coronary / aortic

Evidence hierarchy score (1–10):
10: RCT, Phase 3 trial
8–9: Meta-analysis, systematic review
7–8: Clinical practice guideline or consensus statement from a major society
     (ASA, ESAIC, Association of Anaesthetists, DAS, SCA, SOAP, ESRA, ATS/SCCM …)
     — these change practice directly and are high-value for residents
7: Phase 2 RCT, large prospective cohort (n>500)
5–6: Retrospective cohort, registry study, prospective cohort (n<500)
3–4: Cross-sectional, case-control, genetic association
1–2: Case series, case report, narrative review, expert opinion, editorial, correspondence

Articles (indices {start_idx}–{end_idx}):
{numbered}

Return ONLY valid JSON:
{{
  "assignments": {{"1":[indices],"2":[indices],"3":[indices],"4":[indices],"5":[indices]}},
  "scores": {{"index": score, ...}}
}}
Rules:
- assignments: use the exact indices shown above ({start_idx}–{end_idx}); article may appear in multiple topics; omit if no topic fits
- scores: keys are string indices ("{start_idx}"–"{end_idx}"); value is integer 1–10"""

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw   = resp.content[0].text.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {k: [] for k in "12345"}, {}

    parsed     = json.loads(match.group())
    assignment = parsed.get("assignments", {})
    scores_raw = parsed.get("scores", {})
    scores     = {int(k): int(v) for k, v in scores_raw.items() if str(k).isdigit()}
    return assignment, scores


def _call1_classify_and_score(articles: list[dict]) -> tuple[dict[str, list[int]], dict[int, int]]:
    """Call 1：分類 + 重要性評分，超過 BATCH_SIZE 自動分批合併。"""
    merged_assign: dict[str, list[int]] = {k: [] for k in "12345"}
    merged_scores: dict[int, int] = {}

    for batch_start in range(0, len(articles), BATCH_SIZE):
        batch = articles[batch_start:batch_start + BATCH_SIZE]
        print(f"  Classifying batch {batch_start+1}–{batch_start+len(batch)} / {len(articles)} ...")
        assign, scores = _call1_batch(batch, offset=batch_start)
        for tid in "12345":
            merged_assign[tid].extend(assign.get(tid, []))
        merged_scores.update(scores)
        if batch_start + BATCH_SIZE < len(articles):
            time.sleep(1)

    return merged_assign, merged_scores


def _call2_hot_themes(classified: dict[str, list[dict]]) -> dict[str, str | None]:
    """Call 2：在已分類結果中，偵測跨期刊熱點"""
    topic_blocks = []
    for tid, items in classified.items():
        if not items:
            continue
        lines = [f"Topic {tid}:"]
        for a in items:
            lines.append(f"  [{a['journal']}] {a['title']}")
        topic_blocks.append("\n".join(lines))

    if not topic_blocks:
        return {k: None for k in "12345"}

    prompt = f"""You are a medical literature analyst.

Below are this week's anesthesia articles grouped by topic. For each topic, identify if there is a prominent hot theme — a specific clinical question or intervention where 2+ DIFFERENT journals published relevant articles this week.

{chr(10).join(topic_blocks)}

Return ONLY valid JSON:
{{"1":"hot theme or null","2":"hot theme or null","3":"hot theme or null","4":"hot theme or null","5":"hot theme or null"}}

Rules:
- Hot theme: concise English phrase (≤6 words), e.g. "Remimazolam vs Propofol Sedation"
- Must appear in 2+ different journals within that topic; otherwise null
- null if topic has 0 articles"""

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw   = resp.content[0].text.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {k: None for k in "12345"}

    parsed = json.loads(match.group())
    return {k: parsed.get(k) or None for k in "12345"}


def classify_articles(articles: list[dict]) -> dict[str, dict]:
    # Call 1：分類 + 評分
    assignment, scores = _call1_classify_and_score(articles)

    # 組裝各主題文章（附 score 欄位）
    classified_items: dict[str, list[dict]] = {}
    for tid in "12345":
        items = []
        for i in assignment.get(tid, []):
            if 1 <= i <= len(articles):
                art = dict(articles[i - 1])
                art["score"] = scores.get(i, 5)
                items.append(art)
        # 依重要性分數排序
        items.sort(key=lambda x: x["score"], reverse=True)
        classified_items[tid] = items

    # Call 2：熱點偵測
    hot_themes = _call2_hot_themes(classified_items)

    return {
        tid: {
            "hot_theme": hot_themes.get(tid),
            "items":     classified_items[tid],
        }
        for tid in "12345"
    }


# ── 3. Main ───────────────────────────────────────────────────────────────────

def main():
    where = "GitHub Actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "本機"
    print(f"執行環境：{where}")
    print("Fetching articles...")
    all_articles: list[dict] = []

    # PubMed journal names（用 ISSN 避免縮寫差異）
    ncbi_journals = [
        ("Anesthesiology",  "0003-3022"),
        ("Anaesthesia",     "0003-2409 OR 1365-2044"),   # Anaesthesia (print + eISSN)
        ("PAIN",            "0304-3959 OR 1872-6623"),   # PAIN (IASP)
        ("Lancet Resp Med", "2213-2600 OR 2213-2619"),   # Lancet Respiratory Medicine
        ("Intensive Care",  "0342-4642 OR 1432-1238"),   # Intensive Care Medicine
        ("AJRCCM",          "1073-449X OR 1535-4970"),   # Am J Respir Crit Care Med
        # 2026-08-05 補進來的來源：週三（一般麻醉／神經麻醉）與週五（心臟麻醉）
        # 候選池長期見底，這四本直接補這兩個主題
        ("Anesth Analg",    "0003-2999 OR 1526-7598"),   # Anesthesia & Analgesia
        ("Eur J Anaesth",   "0265-0215 OR 1365-2346"),   # European Journal of Anaesthesiology
        ("J Neurosurg Anes","0898-4921 OR 1537-1921"),   # J Neurosurgical Anesthesiology
        ("J Cardiothor Vasc Anes", "1053-0770 OR 1532-8422"),  # J Cardiothoracic & Vascular Anesthesia
    ]
    failed_sources: list[str] = []

    for journal, issns in ncbi_journals:
        # 多個 ISSN 用 OR 串接
        issn_query = " OR ".join(f"{i.strip()}[ISSN]" for i in issns.split(" OR "))
        try:
            arts = fetch_ncbi(f"({issn_query})", journal)
        except Exception as e:
            # 單一來源掛掉不該讓整週的抓取全毀，記下來繼續跑
            print(f"  ❌ {journal} 抓取失敗（{type(e).__name__}: {e}）")
            failed_sources.append(journal)
            continue
        print(f"  {journal}: {len(arts)}")
        all_articles.extend(arts)
        time.sleep(0.5)

    rss_sources = [
        ("https://rss.sciencedirect.com/publication/science/00070912",             "BJA"),
        ("https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss",        "NEJM"),
        ("https://jamanetwork.com/rss/site_3/67.xml",                              "JAMA"),
    ]
    for url, name in rss_sources:
        try:
            arts = fetch_rss(url, name)
        except Exception as e:
            print(f"  ❌ {name} 抓取失敗（{type(e).__name__}: {e}）")
            failed_sources.append(name)
            continue
        print(f"  {name}: {len(arts)}")
        all_articles.extend(arts)

    # Deduplicate by normalised title
    seen, unique = set(), []
    for a in all_articles:
        key = re.sub(r"\s+", " ", a["title"].lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append(a)

    print(f"Unique articles: {len(unique)}")
    if failed_sources:
        print(f"⚠️ 本次有 {len(failed_sources)} 個來源失敗：{', '.join(failed_sources)}")
    if not unique:
        print("No articles found. Exiting.")
        return

    # 有來源掛掉且文章數明顯偏低時，不要用殘缺結果覆蓋掉上週的 week.json
    if failed_sources and len(unique) < MIN_ARTICLES:
        raise SystemExit(
            f"❌ 只抓到 {len(unique)} 篇（低於 {MIN_ARTICLES} 篇門檻）且有來源失敗，"
            "不覆蓋 week.json，請稍後重跑 workflow。"
        )

    print("Classifying with Haiku...")
    classified = classify_articles(unique)
    for tid, val in classified.items():
        hot = val["hot_theme"] or "-"
        print(f"  Topic {tid} ({TOPICS[tid]['name']}): {len(val['items'])} articles | hot: {hot}")

    now = datetime.now(timezone.utc)
    data = {
        "week":       f"{now.year}-W{now.isocalendar()[1]:02d}",
        "fetched_at": now.isoformat(),
        "articles":   classified,
    }

    os.makedirs("daily_data", exist_ok=True)
    with open("daily_data/week.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # GitHub Actions 環境：用 Contents API 直接寫入，不靠 git push
    gh_token = os.environ.get("GITHUB_TOKEN")
    gh_repo  = os.environ.get("GITHUB_REPOSITORY")
    if gh_token and gh_repo:
        _upload_to_github(data, gh_token, gh_repo)
    else:
        print("Saved → daily_data/week.json (local only)")


def commit_identity() -> tuple[dict, str]:
    """本機執行也會用 Contents API 寫檔，過去一律掛 github-actions[bot]，
    導致 commit 紀錄裡分不出是排程跑的還是有人在本機手動跑的。"""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return (
            {"name": "github-actions[bot]", "email": "github-actions[bot]@users.noreply.github.com"},
            "",
        )
    return (
        {"name": "anesthesia-digest-bot (local)", "email": "local-run@users.noreply.github.com"},
        " (local run)",
    )


def _upload_to_github(data: dict, token: str, repo: str) -> None:
    import base64
    content_b64 = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode()
    ).decode()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{repo}/contents/daily_data/week.json"

    # 取現有檔案的 SHA（更新時必須帶入）
    get = requests.get(url, headers=headers)
    sha = get.json().get("sha") if get.status_code == 200 else None

    committer, suffix = commit_identity()
    payload: dict = {
        "message": f"chore: weekly classified articles{suffix} [skip ci]",
        "content": content_b64,
        "committer": committer,
    }
    if sha:
        payload["sha"] = sha

    put = requests.put(url, headers=headers, json=payload)
    put.raise_for_status()
    new_sha = put.json().get("content", {}).get("sha", "")[:7]
    print(f"Saved → daily_data/week.json (GitHub API, sha={new_sha})")


if __name__ == "__main__":
    main()
