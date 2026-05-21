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


# ── 1. Fetch ──────────────────────────────────────────────────────────────────

def fetch_ncbi(query_term: str, journal_label: str, days_back: int = 30) -> list[dict]:
    today = datetime.now(timezone.utc)
    start = (today - timedelta(days=days_back)).strftime("%Y/%m/%d")
    end   = today.strftime("%Y/%m/%d")

    search = requests.get(
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

    fetch = requests.get(
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

        abstract_el = art.find(".//AbstractText")
        abstract = (abstract_el.text or "") if abstract_el is not None else ""
        if not abstract:
            continue

        pmid = art.findtext(".//PMID") or ""
        articles.append({
            "title":    title,
            "abstract": abstract[:500],
            "journal":  journal_label,
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

        articles.append({
            "title":    title,
            "abstract": abstract[:500],
            "journal":  journal,
            "url":      entry.get("link", ""),
        })

    return articles[:15]


# ── 2. Classify ───────────────────────────────────────────────────────────────

def classify_articles(articles: list[dict]) -> dict[str, list[dict]]:
    numbered = "\n".join(
        f"{i+1}. [{a['journal']}] {a['title']} | {a['abstract'][:200]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""You are an anesthesia research classifier.

Topics:
1: Critical care / ICU / vasopressor / ARDS / sepsis / mechanical ventilation / hemodynamics
2: Pain / Regional anesthesia / nerve block / opioid / epidural / spinal / CRPS / analgesic
3: General anesthesia / Airway / PONV / propofol / volatile / neuromuscular / Neuroanesthesia / ICP / TBI / craniotomy
4: Pediatric anesthesia / Obstetric anesthesia / neonatal / infant / labor / cesarean / maternal
5: Cardiac anesthesia / cardiac surgery / CPB / TAVI / TAVR / ECMO / valve / coronary / aortic

Articles (1-based index):
{numbered}

Return ONLY valid JSON with no explanation.
Format: {{"1":[indices],"2":[indices],"3":[indices],"4":[indices],"5":[indices]}}
Rules:
- Use 1-based indices matching the list above
- An article may appear in multiple topics if clearly relevant to both
- Omit articles that do not fit any topic"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {k: [] for k in "12345"}

    assignment = json.loads(match.group())
    return {
        tid: [articles[i - 1] for i in assignment.get(tid, []) if 1 <= i <= len(articles)]
        for tid in "12345"
    }


# ── 3. Main ───────────────────────────────────────────────────────────────────

def main():
    print("Fetching articles...")
    all_articles: list[dict] = []

    # PubMed journal names（用 ISSN 避免縮寫差異）
    ncbi_journals = [
        ("Anesthesiology",  "0003-3022"),
        ("Anesth Analg",    "0003-2999 OR 1526-7598"),  # Anesthesia & Analgesia (print + eISSN)
        ("Anaesthesia",     "0003-2409 OR 1365-2044"),  # Anaesthesia (print + eISSN)
    ]
    for journal, issns in ncbi_journals:
        # 多個 ISSN 用 OR 串接
        issn_query = " OR ".join(f"{i.strip()}[ISSN]" for i in issns.split(" OR "))
        arts = fetch_ncbi(f"({issn_query})", journal)
        print(f"  {journal}: {len(arts)}")
        all_articles.extend(arts)
        time.sleep(0.5)

    rss_sources = [
        ("https://rss.sciencedirect.com/publication/science/00070912",             "BJA"),
        ("https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss",        "NEJM"),
        ("https://jamanetwork.com/rss/site_3/67.xml",                              "JAMA"),
    ]
    for url, name in rss_sources:
        arts = fetch_rss(url, name)
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
    if not unique:
        print("No articles found. Exiting.")
        return

    print("Classifying with Haiku...")
    classified = classify_articles(unique)
    for tid, arts in classified.items():
        print(f"  Topic {tid} ({TOPICS[tid]['name']}): {len(arts)}")

    now = datetime.now(timezone.utc)
    data = {
        "week":       f"{now.year}-W{now.isocalendar()[1]:02d}",
        "fetched_at": now.isoformat(),
        "articles":   classified,
    }

    os.makedirs("daily_data", exist_ok=True)
    with open("daily_data/week.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("Saved → daily_data/week.json")


if __name__ == "__main__":
    main()
