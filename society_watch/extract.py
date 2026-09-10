"""五個學會的 HTML → Event 抽取。

每個 parser 只做「HTML 字串 → list[Event]」，不碰網路、不碰狀態、不碰通知，
因此可對離線 fixture 完整測試。
"""
import re

from bs4 import BeautifulSoup

from .models import Event

TSA_BASE = "https://www.anesth.org.tw/events/"


def _clean(text: str) -> str:
    """壓平連續空白。RAPM 的標題含大量換行與樣板註解。"""
    return re.sub(r"\s+", " ", text).strip()


def parse_tsa(html: str) -> list[Event]:
    """台灣麻醉醫學會活動列表。無分頁，15 筆滾動視窗，含已過期活動。"""
    soup = BeautifulSoup(html, "html.parser")
    events = []
    for item in soup.select(".event-item"):
        link = item.select_one("a.e-link")
        if not link:
            continue
        m = re.search(r"ID=(\d+)", link.get("href", ""))
        if not m:
            continue

        place_el = item.select_one(".e-place")
        place = None
        if place_el:
            label = place_el.select_one(".e-label")
            if label:
                label.extract()
            place = _clean(place_el.get_text(" ", strip=True))

        kind_el = item.select_one(".e-type")
        date_el = item.select_one(".e-date")
        title_el = item.select_one("h4.e-title")

        events.append(Event(
            source="TSA",
            uid=m.group(1),
            title=_clean(title_el.get_text(" ", strip=True)) if title_el else "",
            # 跨日活動的 .e-date 內含 .e-date-end，取整段文字即 "115/09/26 ~ 115/09/27"
            date_text=_clean(date_el.get_text(" ", strip=True)) if date_el else "",
            url=TSA_BASE + link["href"],
            kind=_clean(kind_el.get_text(strip=True)) if kind_el else None,
            place=place,
        ))
    return events
