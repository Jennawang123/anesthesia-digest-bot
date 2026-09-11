"""各來源的 HTML → Event 抽取。

每個 parser 只做「HTML 字串 → list[Event]」，不碰網路、不碰狀態、不碰通知，
因此可對離線 fixture 完整測試。
"""
import html as htmllib
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

# 該站的「詳細」是 onclick 不是 href。逐則 endpoint 其實存在
# （cal_listview_click_func → educlass_page1_content 同源的 cedunolog_page_content_view/{id}），
# 但它回的是要塞進 BootstrapDialog 的裸片段，沒有版面、不適合直接給人點，
# 因此一律連列表頁。
# 網址尾段的 34 是導覽狀態、不影響內容：實測 /33/1/8/34 載入的正是我們抓的
# fragment /33/1/8/0；而看似更乾淨的 /33/ 反而不含載入器，換過去會更糟。
PAIN_LIST_URL = "https://pain.org.tw/index.php/educlass_page/index/33/1/8/34"

TWECCM_DOWNLOAD_BASE = "https://www.tweccm.org.tw/download/"

TSCCM_NEWS_BASE = "https://www.tsccm.org.tw/news/"


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


def parse_pain(html: str) -> list[Event]:
    """疼痛醫學會學術教育活動列表（AJAX fragment）。

    日期欄是三個 span 疊出來的（2026 / 八月 / 23），原樣以空白串接。
    """
    soup = BeautifulSoup(html, "html.parser")
    events = []
    for row in soup.select("table tbody tr"):
        # 沒有 uid 就無法去重，只有這種情形才丟棄整筆
        m = re.search(r"cal_listview_click_func\('(\d+)'\)", str(row))
        if not m:
            continue

        cells = row.select("td")

        # 日期靠「第一個 td 內的 span 串接」取得（2026 / 八月 / 23）。
        # 這是位置假設：該站若在最前面插一欄，date_text 會靜默變成錯的內容。
        # 只影響顯示、不影響去重，故接受。
        date_text = ""
        if cells:
            date_text = _clean(" ".join(
                s.get_text(strip=True) for s in cells[0].select("span")
            ))

        # text-info 是 Bootstrap 4 的 utility class，站方改版可能換掉。
        # 缺它時退回整格文字而非丟棄整筆——漏報才是本系統的失敗代價。
        title_el = row.select_one("span.text-info")
        if title_el:
            title = _clean(title_el.get_text(" ", strip=True))
        elif len(cells) > 1:
            title = _clean(cells[1].get_text(" ", strip=True))
        else:
            title = ""

        events.append(Event(
            source="PAIN",
            uid=m.group(1),
            title=title,
            date_text=date_text,
            url=PAIN_LIST_URL,
        ))
    return events


def parse_tweccm(html: str) -> list[Event]:
    """急重症聯合年會（SECC）的「其他公告」列表。

    每則是一組 <ul>：第一個 <li> 是標題，第二個 <li> 內的
    <a href="infoFiles.asp?/130.html"> 帶穩定 ID。該頁不提供日期，
    date_text 留空而不硬掰。
    """
    soup = BeautifulSoup(html, "html.parser")
    events = []
    for block in soup.select(".download-list ul"):
        items = block.select("li")
        link = block.select_one("a[href]")
        if not items or not link:
            continue
        m = re.search(r"/(\d+)\.html", link.get("href", ""))
        if not m:
            continue
        events.append(Event(
            source="TWECCM",
            uid=m.group(1),
            title=_clean(items[0].get_text(" ", strip=True)),
            date_text="",
            url=urljoin(TWECCM_DOWNLOAD_BASE, link["href"]),
        ))
    return events


def parse_tsccm(html: str) -> list[Event]:
    """中華民國重症醫學會最新資訊。

    每則是一個 ul.list_td：第一個 li.w15p_lg 是日期（原文含「日期：」標籤），
    li.w70p_lg 內的 <a href="news_info.asp?/983.html"> 帶穩定 ID。

    注意該站是混編碼的：這頁 meta 宣告 utf-8，而課程頁宣告 big5，
    兩頁的 HTTP 標頭都不帶 charset。解碼由 fetch._decode 的
    「標頭 → 頁面 meta → 統計推斷」順序處理，parser 這層不必管。
    """
    soup = BeautifulSoup(html, "html.parser")
    events = []
    for block in soup.select("ul.list_td"):
        link = block.select_one('a[href*="news_info.asp"]')
        if not link:
            continue
        m = re.search(r"/(\d+)\.html", link.get("href", ""))
        if not m:
            continue

        date_text = ""
        date_el = block.select_one("li.w15p_lg")
        if date_el:
            label = date_el.select_one("span")
            if label:
                label.extract()
            date_text = _clean(date_el.get_text(" ", strip=True))

        events.append(Event(
            source="TSCCM",
            uid=m.group(1),
            title=_clean(link.get_text(" ", strip=True)),
            date_text=date_text,
            url=urljoin(TSCCM_NEWS_BASE, link["href"]),
        ))
    return events


def page_lines(html: str) -> list[str]:
    """任意 HTML 頁面 → 可見純文字逐行。

    給沒有「則」的結構可言的來源用（AIRWAY 的 Wix 站、TWECCM 首頁），
    只能整頁取文字後與上次快照做 diff。與來源無關，勿在此加任何站別特例。
    """
    text = re.sub(r"(?is)<script.*?</script>", "", html)
    text = re.sub(r"(?is)<style.*?</style>", "", text)
    # 註解要在拔標籤之前先拔掉：內含 ">" 的註解會讓標籤 regex 提早收尾，
    # 把 "-->" 之類的殘骸留成可見行，混進 diff 觸發多餘的 LLM 呼叫。
    text = re.sub(r"(?s)<!--.*?-->", "", text)
    text = re.sub(r"(?s)<[^>]*>", "\n", text)
    # 反轉義要在拔完標籤之後：否則 &lt; 會還原成 < 再被當成標籤吃掉。
    # 不還原的話 &nbsp;／&zwj; 會原樣進 prompt，也可能被抄進 title 推到 LINE。
    text = htmllib.unescape(text)
    # &nbsp; 還原後是 \xa0，在標題裡是「看不見但不相等」的字元，
    # 正規化成一般空格。注意不可動 \u200d（ZWJ）——它是 👨\u200d⚕️ 這類
    # emoji 的一部分，拿掉會把一個字拆成兩個。
    text = text.replace("\xa0", " ")
    return [line.strip() for line in text.split("\n") if line.strip()]


def page_new_lines(current: list[str], previous: list[str]) -> list[str]:
    """回傳 current 中不存在於 previous 的行，保持原順序。

    用集合比對而非逐行位移比對：Wix 版面調整、首頁輪播順序變動都會使區塊
    順序改變，位移比對會把整頁誤判為新增。
    """
    seen = set(previous)
    return [line for line in current if line not in seen]
