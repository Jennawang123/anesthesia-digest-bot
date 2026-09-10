"""五個學會的 HTML → Event 抽取。

每個 parser 只做「HTML 字串 → list[Event]」，不碰網路、不碰狀態、不碰通知，
因此可對離線 fixture 完整測試。
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import Event

TSA_BASE = "https://www.anesth.org.tw/events/"

TSCVA_BASE = "https://congress.tscva.org.tw"
RAPM_BASE = "https://rapm.org.tw/"

# 非活動類公告的降級關鍵字。刻意保守：只攔明確的名單／獎項／資格公告，
# 不為個案追加規則（over-fitting），判不出來一律不降級。
TSCVA_MINOR_KEYWORDS = ("名單", "恭賀", "獲獎", "甄審條件")


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


def parse_tscva(html: str) -> list[Event]:
    """心臟胸腔暨血管麻醉醫學會最新消息（/news 完整列表，非首頁摘要）。"""
    soup = BeautifulSoup(html, "html.parser")
    events = []
    for card in soup.select("a.news_card"):
        href = card.get("href", "")
        if "/news/" not in href:
            continue
        uid = href.rsplit("/", 1)[1]

        title_el = card.select_one("p.news_card_title")
        time_el = card.select_one("time.news_card_time")
        title = _clean(title_el.get_text(" ", strip=True)) if title_el else ""

        events.append(Event(
            source="TSCVA",
            uid=uid,
            title=title,
            date_text=time_el.get("datetime", "") if time_el else "",
            url=TSCVA_BASE + href,
            minor=any(k in title for k in TSCVA_MINOR_KEYWORDS),
        ))
    return events


def parse_rapm(html: str, kind: str) -> list[Event]:
    """區域麻醉暨疼痛醫學會消息列表。

    kind 由呼叫端依來源 URL 指定：/news-list/2 為「學會活動」、/news-list/5 為「友會活動」。
    兩個分類共用同一組全域 news-detail/{id} 編號，故 uid 不需再加分類前綴。

    .service_date 是公告日不是活動日；活動日只存在於標題（例「＠November 1」）
    或海報圖上，不嘗試抽取。
    """
    soup = BeautifulSoup(html, "html.parser")
    events = []
    for item in soup.select(".service_item"):
        link = item.select_one(".service_title a")
        if not link:
            continue
        href = link.get("href", "")
        if "news-detail/" not in href:
            continue

        # 缺日期節點不丟棄整筆：本系統的失敗代價是漏報，
        # 寧可推一則沒有日期的公告，也不要讓它靜默消失。
        date_el = item.select_one(".service_date")

        events.append(Event(
            source="RAPM",
            uid=href.rsplit("/", 1)[1],
            title=_clean(link.get_text(" ", strip=True)),
            date_text=_clean(date_el.get_text(strip=True)) if date_el else "",
            # 該站目前給的是絕對網址，但改版改成相對路徑時，
            # 直接沿用 href 會靜默產出無效連結，故一律經 urljoin 正規化。
            url=urljoin(RAPM_BASE, href),
            kind=kind,
        ))
    return events
