# 學會活動監測推播（society-watch）實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每日輪詢五個麻醉相關學會的活動公告頁，把沒通知過的新項目推播到使用者個人 LINE。

**Architecture:** GitHub Actions cron 每日 02:00 UTC 觸發 → `fetch.py` 逐站抓 HTML（失敗互不影響）→ `extract.py` 逐站 parser 轉成 `Event` → `state.py` 比對 `seen.json` 濾出新項目 → `notify.py` 格式化推 LINE → 狀態檔 commit 回 repo。四個結構化站用 BeautifulSoup 硬解析，只有 Wix 那站走「純文字 diff → 有新增才呼叫 Haiku」。

**Tech Stack:** Python 3.11（GitHub Actions；本機實測為 3.12.5，`str | None` 語法兩者皆支援，無相容問題）、requests、beautifulsoup4、anthropic（僅 Airway 用）、pytest、GitHub Actions

**設計依據：** `docs/superpowers/specs/2026-09-10-society-event-watcher-design.md`

**「確認失敗」該長什麼樣：** 各 Step 的 `Expected` 只保證**例外型別**，不保證 pytest 把它歸類成 `failed` 還是 `error`。三種情形都算通過 TDD 的「先確認失敗」：

| 情形 | pytest 標籤 | 例外 |
|---|---|---|
| 模組還不存在（Task 2、7、8、9、10、11、13） | collection `error` | `ImportError: cannot import name '<模組>' from 'society_watch'` |
| 模組存在但缺函式，且函式在 **pytest fixture 內**被呼叫（Task 3、5） | `error at setup` | `AttributeError: module ... has no attribute ...` |
| 模組存在但缺函式，函式在**測試函式本體內**被呼叫（Task 4、6、12） | `failed` | `AttributeError: module ... has no attribute ...` |

只要例外型別對得上就繼續往下走，不需要為了讓標籤變成 `failed` 而改測試寫法。

**測試原則：** 所有 parser 對著 `tests/fixtures/society_watch/` 的 2026-09-10 實抓樣本測，**不打真實網路**。斷言值皆為該日實測值。既有 repo 慣例：測試函式名用繁體中文（見 `tests/test_fx_rate.py`），需連外的測試標 `@pytest.mark.live`。

---

## 檔案結構

| 檔案 | 職責 |
|---|---|
| `society_watch/__init__.py` | 空檔，標記為 package |
| `society_watch/models.py` | `Event` dataclass 與 `key` 屬性。無相依。 |
| `society_watch/extract.py` | 五個 parser：HTML → `list[Event]`。不碰網路、不碰狀態、不碰通知。 |
| `society_watch/llm.py` | Airway 專用：新增段落 → Haiku → `list[Event]` |
| `society_watch/state.py` | `seen.json` 與 `airway_snapshot.txt` 讀寫、bootstrap、去重 |
| `society_watch/fetch.py` | HTTP 抓取：UA、timeout、retry×3 |
| `society_watch/sources.py` | 來源設定表；PAIN 跨年 URL 產生 |
| `society_watch/notify.py` | 訊息格式化、4800 字拆分、LINE 推播、告警節流 |
| `society_watch/main.py` | 串接全流程、`--bootstrap` 旗標 |
| `.github/workflows/society-watch.yml` | cron 排程 |
| `tests/test_society_extract.py` | 五個 parser 的測試 |
| `tests/test_society_state.py` | 狀態層測試 |
| `tests/test_society_notify.py` | 格式化與拆分測試 |

---

## Task 1: 專案骨架與 Event 模型

**Files:**
- Create: `society_watch/__init__.py`
- Create: `society_watch/models.py`
- Create: `tests/test_society_models.py`
- Modify: `requirements.txt`

- [ ] **Step 1: 新增相依套件**

在 `requirements.txt` 末尾**追加一行**（不要重排既有內容）：

```
beautifulsoup4>=4.12.0
```

- [ ] **Step 2: 寫失敗測試**

建立 `tests/test_society_models.py`：

```python
"""Event 模型測試。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch.models import Event  # noqa: E402


def test_key_為來源加站方ID():
    e = Event(source="TSA", uid="3105", title="鎮靜課程",
              date_text="115/11/08", url="https://example.com")
    assert e.key == "TSA:3105"


def test_選填欄位預設值():
    e = Event(source="TSA", uid="3105", title="鎮靜課程",
              date_text="115/11/08", url="https://example.com")
    assert e.kind is None
    assert e.place is None
    assert e.minor is False
```

- [ ] **Step 3: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_society_models.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'society_watch'`

- [ ] **Step 4: 實作**

建立空的 `society_watch/__init__.py`，以及 `society_watch/models.py`：

```python
"""學會活動的最小資料結構。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    """一則學會活動或公告。

    date_text 刻意保持各站原樣字串不做正規化：五站格式各異
    （民國年 115/11/08、ISO 2026-08-26、中文 2026 八月 23），
    系統既不排序也不比較日期，只原樣顯示，不轉換就不會轉錯。
    """

    source: str      # 來源代號：TSA / TSCVA / RAPM / PAIN / AIRWAY
    uid: str         # 站方穩定 ID（AIRWAY 例外，為標題 hash）
    title: str
    date_text: str
    url: str
    kind: str | None = None    # 站方分類
    place: str | None = None   # 活動地點，僅 TSA 有
    minor: bool = False        # True = 降級到通知的「其他公告」區

    @property
    def key(self) -> str:
        """去重用的唯一鍵。"""
        return f"{self.source}:{self.uid}"
```

- [ ] **Step 5: 執行測試確認通過**

Run: `python3 -m pytest tests/test_society_models.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add society_watch/__init__.py society_watch/models.py tests/test_society_models.py requirements.txt
git commit -m "feat(society-watch): Event 資料模型"
```

---

## Task 2: TSA parser（台灣麻醉醫學會）

**Files:**
- Create: `society_watch/extract.py`
- Create: `tests/test_society_extract.py`
- Fixture: `tests/fixtures/society_watch/tsa_events_20260910.html`（已存在）

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_society_extract.py`：

```python
"""各學會 parser 測試。全部對 2026-09-10 實抓 fixture 離線測試。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch import extract  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "society_watch"


def _fx(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ── TSA ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def tsa_events():
    return extract.parse_tsa(_fx("tsa_events_20260910.html"))


def test_tsa_抽出十五筆(tsa_events):
    assert len(tsa_events) == 15


def test_tsa_首筆欄位(tsa_events):
    e = tsa_events[0]
    assert e.source == "TSA"
    assert e.uid == "3105"
    assert e.date_text == "115/11/08"
    assert e.kind == "鎮靜活動"
    assert e.title == "台灣麻醉醫學會2026年健康台灣深耕計畫暨特管法輕中度鎮靜課程_1108高醫場"
    assert e.place == "高雄醫學大學國際學術研究大樓三樓臨床技能中心"
    assert e.url == "https://www.anesth.org.tw/events/content.asp?ID=3105&EduType=4"


def test_tsa_跨日活動日期保留起訖(tsa_events):
    e = next(x for x in tsa_events if x.uid == "3091")
    assert e.date_text == "115/09/26 ~ 115/09/27"


def test_tsa_民國年不做轉換(tsa_events):
    # 115 年即 2026 年，但一律不轉換：不轉換就不會轉錯
    assert all(not x.date_text.startswith("20") for x in tsa_events)


def test_tsa_全部不降級(tsa_events):
    assert all(x.minor is False for x in tsa_events)
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_society_extract.py -v`
Expected: **collection error**（不是 test failed）——`ImportError: cannot import name 'extract' from 'society_watch'`，pytest 顯示 `1 error` 與 `Interrupted: 1 error during collection`

- [ ] **Step 3: 實作**

建立 `society_watch/extract.py`：

```python
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
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_society_extract.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add society_watch/extract.py tests/test_society_extract.py
git commit -m "feat(society-watch): TSA 活動列表 parser"
```

---

## Task 3: TSCVA parser（心臟胸腔暨血管麻醉，含 minor 降級）

**Files:**
- Modify: `society_watch/extract.py`
- Modify: `tests/test_society_extract.py`
- Fixture: `tests/fixtures/society_watch/tscva_news_20260910.html`（已存在）

**注意：** `/news` 列表頁與首頁用**不同 class**。首頁是 `a.index_news--item`／`._date`／`._title`，`/news` 是 `a.news_card`／`time.news_card_time`／`p.news_card_title`。此處以 `/news` 為準。

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_society_extract.py` 末尾追加：

```python
# ── TSCVA ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def tscva_events():
    return extract.parse_tscva(_fx("tscva_news_20260910.html"))


def test_tscva_抽出六筆(tscva_events):
    assert len(tscva_events) == 6


def test_tscva_首筆欄位(tscva_events):
    e = tscva_events[0]
    assert e.source == "TSCVA"
    assert e.uid == "e9003f5d-1793-4fc4-babe-d031dd36b18b"
    assert e.date_text == "2026-09-01"
    assert e.title == "【恭賀通過名單】2026 年度 TSCVA 專科醫師甄審通過名單"
    assert e.url == "https://congress.tscva.org.tw/news/e9003f5d-1793-4fc4-babe-d031dd36b18b"
    assert e.minor is True


def test_tscva_降級命中三筆(tscva_events):
    # 「恭賀通過名單」「獲獎名單」「甄審條件及資格」命中；
    # 「報告順序」「甄選辦法」不含關鍵字，刻意不追加規則去攔（over-fitting）
    assert sum(1 for x in tscva_events if x.minor) == 3


def test_tscva_即將辦理活動不降級(tscva_events):
    e = next(x for x in tscva_events if x.title.startswith("[即將辦理活動]"))
    assert e.minor is False
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_society_extract.py -k tscva -v`
Expected: FAIL，`AttributeError: module 'society_watch.extract' has no attribute 'parse_tscva'`

- [ ] **Step 3: 實作**

在 `society_watch/extract.py` 的 `TSA_BASE` 下方追加常數，並在 `parse_tsa` 之後追加函式：

`extract.py` 頂端的 import 區加入 `from urllib.parse import urljoin`，並追加常數：

```python
TSCVA_BASE = "https://congress.tscva.org.tw"

# 非活動類公告的降級關鍵字。刻意保守：只攔明確的名單／獎項／資格公告，
# 不為個案追加規則（over-fitting），判不出來一律不降級。
TSCVA_MINOR_KEYWORDS = ("名單", "恭賀", "獲獎", "甄審條件")

RAPM_BASE = "https://rapm.org.tw/"
```

```python
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
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_society_extract.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add society_watch/extract.py tests/test_society_extract.py
git commit -m "feat(society-watch): TSCVA parser 與非活動公告降級"
```

---

## Task 4: RAPM parser（區域麻醉，學會活動＋友會活動）

**Files:**
- Modify: `society_watch/extract.py`
- Modify: `tests/test_society_extract.py`
- Fixtures: `rapm_newslist2_20260910.html`、`rapm_newslist5_20260910.html`（已存在）

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_society_extract.py` 末尾追加：

```python
# ── RAPM ──────────────────────────────────────────────────────────────────────

def test_rapm_學會活動抽出十六筆():
    events = extract.parse_rapm(_fx("rapm_newslist2_20260910.html"), kind="學會活動")
    assert len(events) == 16


def test_rapm_首筆欄位():
    events = extract.parse_rapm(_fx("rapm_newslist2_20260910.html"), kind="學會活動")
    e = events[0]
    assert e.source == "RAPM"
    assert e.uid == "32"
    assert e.date_text == "2026-08-26"
    assert e.kind == "學會活動"
    assert e.url == "https://rapm.org.tw/news-detail/32"
    # 活動日只在標題裡（＠November 1），不嘗試抽出
    assert e.title == "疼痛擂台 8：真實病人工作坊-全脊守護，從頸到骶 ＠November 1"


def test_rapm_標題壓平樣板空白():
    events = extract.parse_rapm(_fx("rapm_newslist2_20260910.html"), kind="學會活動")
    assert all("\n" not in x.title and "  " not in x.title for x in events)


def test_rapm_友會活動抽出十一筆():
    events = extract.parse_rapm(_fx("rapm_newslist5_20260910.html"), kind="友會活動")
    assert len(events) == 11
    assert events[0].uid == "23"
    assert events[0].kind == "友會活動"


def test_rapm_兩分類編號不重疊():
    a = extract.parse_rapm(_fx("rapm_newslist2_20260910.html"), kind="學會活動")
    b = extract.parse_rapm(_fx("rapm_newslist5_20260910.html"), kind="友會活動")
    assert not ({x.uid for x in a} & {x.uid for x in b})


def test_rapm_相對路徑連結會補成絕對網址():
    # 該站目前給絕對網址，但改版成相對路徑時不可靜默產出無效連結
    html = """<div class="service_item">
      <div class="service_title"><a href="/news-detail/99">測試公告</a></div>
      <div class="service_date">2026-09-01</div>
    </div>"""
    e = extract.parse_rapm(html, kind="學會活動")[0]
    assert e.url == "https://rapm.org.tw/news-detail/99"


def test_rapm_缺日期節點仍收錄不漏報():
    # 漏報是本系統最該避免的失效，缺欄位給空字串而非整筆丟棄
    html = """<div class="service_item">
      <div class="service_title"><a href="https://rapm.org.tw/news-detail/98">沒有日期的公告</a></div>
    </div>"""
    events = extract.parse_rapm(html, kind="學會活動")
    assert len(events) == 1
    assert events[0].uid == "98"
    assert events[0].date_text == ""
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_society_extract.py -k rapm -v`
Expected: FAIL，`AttributeError: ... has no attribute 'parse_rapm'`

- [ ] **Step 3: 實作**

在 `society_watch/extract.py` 追加：

```python
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
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_society_extract.py -v`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add society_watch/extract.py tests/test_society_extract.py
git commit -m "feat(society-watch): RAPM 學會活動與友會活動 parser"
```

---

## Task 5: PAIN parser（疼痛醫學會）

**Files:**
- Modify: `society_watch/extract.py`
- Modify: `tests/test_society_extract.py`
- Fixture: `tests/fixtures/society_watch/pain_fragment_20260910.html`（已存在）

**注意：** 該站「詳細」是 `onclick="cal_listview_click_func('3142')"` 而非 `href`，**沒有逐則網址**，所有項目一律連到列表頁。

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_society_extract.py` 末尾追加：

```python
# ── PAIN ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def pain_events():
    return extract.parse_pain(_fx("pain_fragment_20260910.html"))


def test_pain_抽出十筆(pain_events):
    assert len(pain_events) == 10


def test_pain_首筆欄位(pain_events):
    e = pain_events[0]
    assert e.source == "PAIN"
    assert e.uid == "3142"
    assert e.date_text == "2026 八月 23"
    assert e.title.startswith("2026 台灣疼痛醫學會 全人整合醫學教育 系列工作坊")


def test_pain_全部連到列表頁(pain_events):
    # 該站無逐則網址（詳細是 onclick 不是 href）
    assert all(
        x.url == "https://pain.org.tw/index.php/educlass_page/index/33/1/8/34"
        for x in pain_events
    )


def test_pain_空表回傳空list():
    # 明年度尚無活動時，該 endpoint 回的是只有表頭的空表
    assert extract.parse_pain("<table class='table'><tbody></tbody></table>") == []


def test_pain_缺text_info時退回整格文字不漏報():
    # text-info 是 Bootstrap utility class，站方改版可能換掉，
    # 缺它不可讓整筆無聲消失
    html = """<table><tbody><tr>
      <td><span>2026</span><span>九月</span><span>15</span></td>
      <td>沒有包在 text-info 裡的活動名稱</td>
      <td><a onclick="cal_listview_click_func('9001')">詳細</a></td>
    </tr></tbody></table>"""
    events = extract.parse_pain(html)
    assert len(events) == 1
    assert events[0].uid == "9001"
    assert events[0].title == "沒有包在 text-info 裡的活動名稱"
    assert events[0].date_text == "2026 九月 15"
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_society_extract.py -k pain -v`
Expected: FAIL，`AttributeError: ... has no attribute 'parse_pain'`

- [ ] **Step 3: 實作**

在 `society_watch/extract.py` 追加常數與函式：

```python
# 該站的「詳細」是 onclick 不是 href。逐則 endpoint 其實存在
# （cal_listview_click_func → educlass_page1_content 同源的 cedunolog_page_content_view/{id}），
# 但它回的是要塞進 BootstrapDialog 的裸片段，沒有版面、不適合直接給人點，
# 因此一律連列表頁。
# 網址尾段的 34 是導覽狀態、不影響內容：實測 /33/1/8/34 載入的正是我們抓的
# fragment /33/1/8/0；而看似更乾淨的 /33/ 反而不含載入器，換過去會更糟。
PAIN_LIST_URL = "https://pain.org.tw/index.php/educlass_page/index/33/1/8/34"
```

```python
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
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_society_extract.py -v`
Expected: 21 passed

- [ ] **Step 5: Commit**

```bash
git add society_watch/extract.py tests/test_society_extract.py
git commit -m "feat(society-watch): PAIN 學術教育列表 parser"
```

---

## Task 6: AIRWAY 純文字抽取與 diff（不含 LLM）

**Files:**
- Modify: `society_watch/extract.py`
- Modify: `tests/test_society_extract.py`
- Fixture: `tests/fixtures/society_watch/airway_text_20260910.txt`（已存在，124 行）

**背景：** 該站是 Wix，SSR 有吐出可見文字但**完全無結構**——整頁是一片連續富文本，沒有逐則邊界、沒有逐則日期、沒有逐則連結。唯一可行做法是純文字 diff。

**fixture 說明：** 原始 Wix HTML 為 1.1 MB，不放進 public repo，只保留抽取後的純文字。因此 `airway_lines()`（去 script/style 的通用邏輯）用小段手寫 HTML 測，`airway_new_lines()`（真正的業務邏輯）用真實 124 行文字測。

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_society_extract.py` 末尾追加：

```python
# ── AIRWAY ────────────────────────────────────────────────────────────────────

def test_airway_去除script與style():
    html = """
    <html><head><style>.a{color:red}</style></head>
    <body><script>var x=1;</script>
    <div>  📣 主辦單位： 台灣呼吸道處理醫學會  </div>
    <div></div>
    <div>🗓️ 上課時間： 2026年6月13日</div>
    </body></html>
    """
    lines = extract.airway_lines(html)
    assert lines == ["📣 主辦單位： 台灣呼吸道處理醫學會", "🗓️ 上課時間： 2026年6月13日"]
    assert not any("var x" in l or "color:red" in l for l in lines)


def test_airway_真實wix頁抽取結果與快照一致():
    # 用真實 Wix 頁（僅去掉 script/style 以控制體積，註解與 entity 都保留）
    # 端到端驗證 airway_lines，而非只斷言快照檔自己的行數
    lines = extract.airway_lines(_fx("airway_page_20260910.html"))
    expected = [l for l in _fx("airway_text_20260910.txt").split("\n") if l.strip()]
    assert lines == expected
    assert len(lines) == 117


def test_airway_去除html註解殘骸():
    # 內含 ">" 的註解會讓標籤 regex 提早收尾，把 "-->" 留成可見行。
    # 真實頁面的第一行原本就是這個殘骸。
    lines = extract.airway_lines("<!-- 內含 > 符號的註解 --><div>正文</div>")
    assert lines == ["正文"]


def test_airway_還原html_entity並正規化nbsp():
    lines = extract.airway_lines("<div>課程名稱&nbsp;A&amp;B</div><div>&nbsp;</div>")
    assert lines == ["課程名稱 A&B"]   # 純 &nbsp; 的填充行會被濾掉


def test_airway_無新增時回空list():
    old = ["A", "B", "C"]
    assert extract.airway_new_lines(old, old) == []


def test_airway_只回新增的行():
    old = ["A", "B"]
    new = ["A", "B", "C 新公告", "D"]
    assert extract.airway_new_lines(new, old) == ["C 新公告", "D"]


def test_airway_行順序改變不算新增():
    # Wix 版面調整常導致區塊順序變動，不應誤判為新公告
    assert extract.airway_new_lines(["B", "A"], ["A", "B"]) == []


def test_airway_首次執行時舊快照為空則全部算新增():
    assert extract.airway_new_lines(["A", "B"], []) == ["A", "B"]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_society_extract.py -k airway -v`
Expected: FAIL，`AttributeError: ... has no attribute 'airway_lines'`

- [ ] **Step 3: 實作**

`extract.py` 頂端 import 區加入 `import html as htmllib`，並追加：

```python
AIRWAY_URL = "https://www.tsamairway.org.tw/最新資訊"


def airway_lines(html: str) -> list[str]:
    """Wix 頁面 → 可見純文字逐行。

    該站無「則」的結構可言，只能整頁取文字後與上次快照做 diff。
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


def airway_new_lines(current: list[str], previous: list[str]) -> list[str]:
    """回傳 current 中不存在於 previous 的行，保持原順序。

    用集合比對而非逐行位移比對：Wix 版面調整常使區塊順序變動，
    位移比對會把整頁誤判為新增。
    """
    seen = set(previous)
    return [line for line in current if line not in seen]
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_society_extract.py -v`
Expected: 29 passed

- [ ] **Step 5: Commit**

```bash
git add society_watch/extract.py tests/test_society_extract.py
git commit -m "feat(society-watch): Wix 站純文字抽取與 diff"
```

---

## Task 7: AIRWAY 的 Haiku 抽取

**Files:**
- Create: `society_watch/llm.py`
- Create: `tests/test_society_llm.py`

**成本控制：** 只有 diff 有新增行時才呼叫，沒新增就完全不呼叫。判不出來時一律當成活動（不降級），符合 spec §5「不確定偏向通知」。

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_society_llm.py`：

```python
"""Airway LLM 抽取測試。只測 prompt 組裝與回應解析，不打 API。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from society_watch import llm  # noqa: E402


def test_prompt_含全部新增行():
    prompt = llm.build_prompt(["📣 北區麻醉月會", "📅 時間：115年2月7日"])
    assert "📣 北區麻醉月會" in prompt
    assert "📅 時間：115年2月7日" in prompt


def test_解析回應為Event():
    raw = '[{"title": "115年2月份北區麻醉月會", "date_text": "115年2月7日", "is_event": true}]'
    events = llm.parse_response(raw)
    assert len(events) == 1
    e = events[0]
    assert e.source == "AIRWAY"
    assert e.title == "115年2月份北區麻醉月會"
    assert e.date_text == "115年2月7日"
    assert e.url == "https://www.tsamairway.org.tw/最新資訊"
    assert e.minor is False


def test_uid為標題hash且穩定():
    raw = '[{"title": "北區麻醉月會", "date_text": "", "is_event": true}]'
    a = llm.parse_response(raw)[0]
    b = llm.parse_response(raw)[0]
    assert a.uid == b.uid
    assert len(a.uid) == 12


def test_非活動者標為minor():
    raw = '[{"title": "賀呂忠和主任榮任理事長", "date_text": "", "is_event": false}]'
    assert llm.parse_response(raw)[0].minor is True


def test_回應含程式碼圍籬也能解析():
    raw = '```json\n[{"title": "工作坊", "date_text": "", "is_event": true}]\n```'
    assert len(llm.parse_response(raw)) == 1


def test_回應無法解析時回空list():
    # parse_response 維持既有契約：解析不出來回空 list，不拋例外
    assert llm.parse_response("模型今天話很多但沒給 JSON") == []


def test_checked_版本能分辨垃圾與合法空陣列():
    # 兩者都產出空清單，只有 ok 這個旗標分得出來——
    # 丟掉它就等於讓「模型回垃圾」偽裝成「今天沒有活動」
    assert llm.parse_response_checked("[]") == ([], True)
    assert llm.parse_response_checked("模型今天話很多但沒給 JSON") == ([], False)


def test_陣列後面接散文也能解析():
    raw = '[{"title": "工作坊", "date_text": "", "is_event": true}] 以上是我找到的[全部]內容'
    events, ok = llm.parse_response_checked(raw)
    assert ok is True
    assert len(events) == 1


def test_元素不是物件時跳過而不拋例外():
    events, ok = llm.parse_response_checked('["工作坊A", {"title": "工作坊B", "is_event": true}]')
    assert ok is True
    assert [e.title for e in events] == ["工作坊B"]


def test_新增行數超過上限時拋例外():
    # 整頁改版時不送一大包進去燒錢，改成拋例外讓 collect 記成失敗並告警
    with pytest.raises(llm.LLMResponseError, match="疑似整頁改版"):
        llm.classify([f"第 {i} 行" for i in range(llm.MAX_NEW_LINES + 1)])


def test_沒有新增行時不建立client也不呼叫api():
    # CLAUDE_API_KEY 不存在時仍須正常回空 list
    assert llm.classify([]) == []
```json\n[{"title": "工作坊", "date_text": "", "is_event": true}]\n```'
    assert len(llm.parse_response(raw)) == 1


def test_回應無法解析時回空list():
    # 寧可漏這一輪也不要讓整支程式炸掉；Task 13 會另外送告警
    assert llm.parse_response("模型今天話很多但沒給 JSON") == []
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_society_llm.py -v`
Expected: **collection error**（不是 test failed）——`ImportError: cannot import name 'llm' from 'society_watch'`，pytest 顯示 `1 error`

- [ ] **Step 3: 實作**

建立 `society_watch/llm.py`：

```python
"""Airway（Wix 無結構站）專用的 Haiku 抽取。

只有 diff 出現新增行時才呼叫，沒新增就完全不呼叫，成本趨近於零。
"""
import hashlib
import json
import os
import re

from anthropic import Anthropic

from .extract import AIRWAY_URL
from .models import Event

MODEL = "claude-haiku-4-5"   # 完整 model id，不加日期後綴

# 單次送給模型的新增行上限。整頁被判為新增（改版、頁面搬家）時，
# 與其花錢送一大包進去、還可能被 max_tokens 截斷成半截 JSON，
# 不如當成異常拋出去告警——快照不會前進，人看過再說。
MAX_NEW_LINES = 60

class LLMResponseError(RuntimeError):
    """Haiku 回應無法解析，或新增量異常。

    刻意拋出而非回空 list：呼叫端（main.collect）的 except 會把它記成
    AIRWAY 失敗 → 送告警 → **不更新快照** → 下一輪重試。
    若改回空 list，「模型回垃圾」與「模型判定沒有活動」在呼叫端完全同形，
    快照照樣前進，那批公告就永久漏掉且無人知曉。
    """


PROMPT_TEMPLATE = """以下是台灣呼吸道處理醫學會網站「最新資訊」頁新增的內容片段。
請判斷其中包含哪些「活動、課程或工作坊」公告。

請只輸出 JSON 陣列，每個元素包含：
- title：活動名稱（字串）
- date_text：活動日期。**只取日期本身**，不要含時間、星期、時區，也不要含
  「時間：」這類標籤與 emoji。年份原樣照抄，不要在民國年與西元年之間換算。
  找不到就給空字串。
  例：「📅 時間：115年2月7日（星期六）08:30-12:30」→「115年2月7日」
  例：「🗓️ 上課時間： 2026年6月13日（六）10:00 - 11:00 (GMT+8)」→「2026年6月13日」
- is_event：是否為活動／課程／工作坊公告（布林值）。人事賀詞、得獎名單、宣傳影片請給 false。

不確定是不是活動時，一律給 is_event: true。

新增內容：
---
{content}
---
"""


def build_prompt(new_lines: list[str]) -> str:
    return PROMPT_TEMPLATE.format(content="\n".join(new_lines))


def parse_response_checked(raw: str) -> tuple[list[Event], bool]:
    """回傳（事件清單, 是否成功解析出 JSON 陣列）。

    第二個值是關鍵：合法的空陣列與垃圾回應都會產出空清單，
    只有這裡分得出來，不能把這個資訊丟掉。
    """
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()

    start = text.find("[")
    if start == -1:
        return [], False
    try:
        # 用 raw_decode 而非貪婪 regex：模型若在陣列後又寫了含 [ ] 的散文，
        # 貪婪比對會抓到過寬的區間而整包解析失敗。
        items, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return [], False
    if not isinstance(items, list):
        return [], False

    events = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        events.append(Event(
            source="AIRWAY",
            # 該站無站方 ID，只能用標題 hash。已知限制：主辦方改標題會重推。
            uid=hashlib.sha1(title.encode("utf-8")).hexdigest()[:12],
            title=title,
            date_text=str(item.get("date_text", "")).strip(),
            url=AIRWAY_URL,
            minor=not item.get("is_event", True),
        ))
    return events, True


def parse_response(raw: str) -> list[Event]:
    """薄包裝，維持「解析不出來回空 list」的既有契約。"""
    return parse_response_checked(raw)[0]


def classify(new_lines: list[str]) -> list[Event]:
    """呼叫 Haiku 判斷新增段落。沒有新增行就不呼叫 API。"""
    if not new_lines:
        return []
    if len(new_lines) > MAX_NEW_LINES:
        raise LLMResponseError(
            f"新增 {len(new_lines)} 行超過上限 {MAX_NEW_LINES}，疑似整頁改版"
        )

    client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": build_prompt(new_lines)}],
    )
    # 取第一個 text block，不假設 content[0] 就是文字
    # （日後若換成預設開 thinking 的模型，content[0] 會是 thinking block）
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")

    events, ok = parse_response_checked(text)
    if not ok:
        raise LLMResponseError("Haiku 回應無法解析為 JSON 陣列")
    return events
```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()

    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

    events = []
    for item in items:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        events.append(Event(
            source="AIRWAY",
            # 該站無站方 ID，只能用標題 hash。已知限制：主辦方改標題會重推。
            uid=hashlib.sha1(title.encode("utf-8")).hexdigest()[:12],
            title=title,
            date_text=str(item.get("date_text", "")).strip(),
            url=AIRWAY_URL,
            minor=not item.get("is_event", True),
        ))
    return events


def classify(new_lines: list[str]) -> list[Event]:
    """呼叫 Haiku 判斷新增段落。沒有新增行就不呼叫 API。"""
    if not new_lines:
        return []
    client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": build_prompt(new_lines)}],
    )
    return parse_response(resp.content[0].text)
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_society_llm.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add society_watch/llm.py tests/test_society_llm.py
git commit -m "feat(society-watch): Wix 站新增段落的 Haiku 抽取"
```

---

## Task 8: 狀態層（seen.json 與 snapshot）

**Files:**
- Create: `society_watch/state.py`
- Create: `tests/test_society_state.py`

**格式要求：** `seen.json` 排序後 pretty-print、**一則一行**、保留結尾換行，沿用 `daily_data/sent_articles.json` 慣例。每日 commit 的 diff 才會只有真正新增的那幾行。

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_society_state.py`：

```python
"""狀態層測試。"""
import json
import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch import state  # noqa: E402
from society_watch.models import Event  # noqa: E402


def _ev(source, uid):
    return Event(source=source, uid=uid, title="t", date_text="d", url="u")


def test_檔案不存在時回空set(tmp_path):
    assert state.load_seen(tmp_path / "nope.json") == set()


def test_寫入後讀得回來(tmp_path):
    p = tmp_path / "seen.json"
    state.save_seen(p, {"TSA:3105", "PAIN:3142"})
    assert state.load_seen(p) == {"TSA:3105", "PAIN:3142"}


def test_寫出格式為排序且一則一行(tmp_path):
    p = tmp_path / "seen.json"
    state.save_seen(p, {"TSA:3105", "PAIN:3142", "RAPM:32"})
    text = p.read_text(encoding="utf-8")
    assert text.endswith("\n")           # 保留結尾換行，避免整檔 diff
    assert json.loads(text)["seen"] == ["PAIN:3142", "RAPM:32", "TSA:3105"]
    assert text.count('"PAIN:3142"') == 1
    # 每則各佔一行
    assert '"PAIN:3142",\n' in text


def test_只回未見過的項目():
    events = [_ev("TSA", "3105"), _ev("TSA", "3106")]
    assert [e.uid for e in state.filter_new(events, {"TSA:3105"})] == ["3106"]


def test_同一輪內重複的項目只留一筆():
    events = [_ev("TSA", "3105"), _ev("TSA", "3105")]
    assert len(state.filter_new(events, set())) == 1


def test_不同來源相同uid不互相影響():
    events = [_ev("TSA", "32"), _ev("RAPM", "32")]
    assert len(state.filter_new(events, {"TSA:32"})) == 1


def test_快照讀寫(tmp_path):
    p = tmp_path / "snap.txt"
    assert state.load_snapshot(p) == []
    state.save_snapshot(p, ["A", "B"])
    assert state.load_snapshot(p) == ["A", "B"]


def test_寫入失敗不會留下半截檔案(tmp_path, monkeypatch):
    # 直接 write_text 是先截斷再寫，中途被砍會留下壞檔，
    # 下一輪 json.loads 會炸掉且連告警都送不出去
    p = tmp_path / "seen.json"
    state.save_seen(p, {"TSA:1"})

    def boom(*args, **kwargs):
        raise KeyboardInterrupt("模擬 Actions 取消")

    monkeypatch.setattr(state.os, "replace", boom)
    with pytest.raises(KeyboardInterrupt):
        state.save_seen(p, {"TSA:1", "TSA:2"})

    assert state.load_seen(p) == {"TSA:1"}          # 舊內容完好
    assert not list(tmp_path.glob("*.tmp"))         # 暫存檔已清掉
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_society_state.py -v`
Expected: **collection error**（不是 test failed）——`ImportError: cannot import name 'state' from 'society_watch'`，pytest 顯示 `1 error`

- [ ] **Step 3: 實作**

建立 `society_watch/state.py`：

```python
"""去重狀態與 Wix 快照的讀寫。

seen.json 只增不減：TSA 是 15 筆滾動視窗，舊活動會掉出列表，
若為省空間裁剪，該筆日後重新出現就會重推。一則 uid 數十 bytes，
跑十年不過數百 KB，不值得為此冒重推風險。
"""
import json
import os
import tempfile
from pathlib import Path
from typing import Iterable

from .models import Event


def _atomic_write(path: Path, text: str) -> None:
    """先寫暫存檔再 os.replace 換上去。

    直接 write_text 是先截斷再寫：程序在寫入中途被砍（Actions 逾時或
    取消）會留下半截檔案，下一輪 json.loads 直接拋例外，整個 run 在
    collect() 之前就死掉——連告警都送不出去，唯一訊號是 Actions 紅燈。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_seen(path: Path) -> set[str]:
    if not Path(path).exists():
        return set()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return set(data.get("seen", []))


def save_seen(path: Path, keys: Iterable[str]) -> None:
    """排序後 pretty-print、一則一行、保留結尾換行。

    格式沿用 daily_data/sent_articles.json，讓每日 commit 的 diff
    只有真正新增的那幾行。
    """
    payload = {"seen": sorted(keys)}
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def filter_new(events: Iterable[Event], seen: set[str]) -> list[Event]:
    """濾出未通知過的項目，並去掉同一輪內的重複（保持原順序）。"""
    result = []
    batch_seen = set()
    for event in events:
        if event.key in seen or event.key in batch_seen:
            continue
        batch_seen.add(event.key)
        result.append(event)
    return result


def load_snapshot(path: Path) -> list[str]:
    if not Path(path).exists():
        return []
    text = Path(path).read_text(encoding="utf-8")
    return [line for line in text.split("\n") if line.strip()]


def save_snapshot(path: Path, lines: list[str]) -> None:
    _atomic_write(path, "\n".join(lines) + "\n")
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_society_state.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add society_watch/state.py tests/test_society_state.py
git commit -m "feat(society-watch): 去重狀態層與 Wix 快照讀寫"
```

---

## Task 9: 抓取層（含編碼修正）

**Files:**
- Create: `society_watch/fetch.py`
- Create: `tests/test_society_fetch.py`

**已實測的坑：** `https://www.anesth.org.tw/events/index.asp` 回應的 `Content-Type` 是 `text/html`，**不帶 charset**。`requests` 此時會退回猜 `ISO-8859-1`，`resp.text` 直接是亂碼（實測 `"鎮靜活動" in resp.text` 為 `False`）。必須在標頭沒有 charset 時改用 `apparent_encoding`。

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_society_fetch.py`：

```python
"""抓取層測試。離線測編碼與重試，另有 --live 測試打真實網站。"""
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch import fetch  # noqa: E402


class FakeResponse:
    def __init__(self, body: bytes, content_type: str):
        self.content = body
        self.headers = {"Content-Type": content_type}
        self.encoding = "ISO-8859-1"   # requests 無 charset 時的預設猜測
        self.apparent_encoding = "utf-8"
        self.status_code = 200
        self.url = "https://example.com"

    @property
    def text(self):
        return self.content.decode(self.encoding)

    def raise_for_status(self):
        pass


def test_標頭無charset時改用apparent_encoding(monkeypatch):
    body = "鎮靜活動".encode("utf-8")
    monkeypatch.setattr(
        fetch.requests, "get",
        lambda *a, **k: FakeResponse(body, "text/html"),
    )
    assert fetch.get("https://example.com") == "鎮靜活動"


def test_標頭無charset時優先看頁面自己的meta(monkeypatch):
    # anesth.org.tw 就是這種：Content-Type 裸 text/html，但頁面寫了
    # <meta charset="utf-8">。能問頁面就別用統計猜。
    body = '<meta charset="utf-8"><h4>鎮靜活動</h4>'.encode("utf-8")
    resp = FakeResponse(body, "text/html")
    resp.apparent_encoding = "big5"      # 猜錯的話會解成亂碼
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: resp)
    assert "鎮靜活動" in fetch.get("https://example.com")


def test_標頭有charset時尊重標頭(monkeypatch):
    # apparent_encoding 刻意設成不同值：兩者相同的話，就算實作誤把標頭
    # 無條件覆寫掉，這個測試也照樣會過（mutation 實測確認過）
    resp = FakeResponse("鎮靜活動".encode("utf-8"), "text/html; charset=utf-8")
    resp.apparent_encoding = "big5"
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: resp)
    assert fetch.get("https://example.com") == "鎮靜活動"


def test_失敗會重試三次後放棄(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise requests.ConnectionError("斷線")

    monkeypatch.setattr(fetch.requests, "get", boom)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    with pytest.raises(requests.ConnectionError):
        fetch.get("https://example.com")
    assert len(calls) == 3


def test_第二次就成功則不再重試(monkeypatch):
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise requests.ConnectionError("斷線")
        return FakeResponse("OK".encode("utf-8"), "text/html; charset=utf-8")

    monkeypatch.setattr(fetch.requests, "get", flaky)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    fetch.get("https://example.com")
    assert len(calls) == 2


@pytest.mark.live
def test_實際抓TSA不亂碼():
    html = fetch.get("https://www.anesth.org.tw/events/index.asp")
    assert "鎮靜" in html or "工作坊" in html


def _http_error(status: int) -> requests.HTTPError:
    resp = FakeResponse(b"", "text/html; charset=utf-8")
    resp.status_code = status
    return requests.HTTPError(f"{status}", response=resp)


def test_永久性失敗不重試(monkeypatch):
    # raise_for_status 拋的 HTTPError 也是 RequestException，一律重試的話
    # 站方改網址(404)或擋爬蟲(403)會白白多打兩次
    calls = []

    def gone(*a, **k):
        calls.append(1)
        raise _http_error(404)

    monkeypatch.setattr(fetch.requests, "get", gone)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    with pytest.raises(requests.HTTPError):
        fetch.get("https://example.com")
    assert len(calls) == 1


def test_伺服器錯誤仍會重試(monkeypatch):
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        raise _http_error(503)

    monkeypatch.setattr(fetch.requests, "get", flaky)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    with pytest.raises(requests.HTTPError):
        fetch.get("https://example.com")
    assert len(calls) == 3


def test_attempts為零時明確報錯():
    with pytest.raises(ValueError):
        fetch.get("https://example.com", attempts=0)
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_society_fetch.py -v -m "not live"`
Expected: **collection error**（不是 test failed）——`ImportError: cannot import name 'fetch' from 'society_watch'`，pytest 顯示 `1 error`

- [ ] **Step 3: 實作**

建立 `society_watch/fetch.py`：

```python
"""HTTP 抓取層：UA、timeout、重試、編碼決定。"""
import re
import time

import requests

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# 只在前段找，避免整頁掃描；meta charset 依規範就該在 head 前面
_META_CHARSET = re.compile(
    rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.I
)


def _header_charset(resp: requests.Response) -> str | None:
    ctype = resp.headers.get("Content-Type", "")
    m = re.search(r"charset\s*=\s*([^\s;]+)", ctype, re.I)
    return m.group(1).strip('"\'') if m else None


def _meta_charset(content: bytes) -> str | None:
    m = _META_CHARSET.search(content[:4096])
    return m.group(1).decode("ascii", "ignore") if m else None


def _decode(resp: requests.Response) -> str:
    """決定編碼並解碼。

    順序：HTTP 標頭 → 頁面自己的 <meta charset> → apparent_encoding。

    為什麼要有中間那一層：anesth.org.tw 的 Content-Type 是裸 text/html，
    requests 會退回猜 ISO-8859-1，整頁中文變亂碼；但那一頁其實有寫
    <meta charset="utf-8">，requests 完全不看。落到 apparent_encoding 是
    純統計推斷，而 CJK 編碼互相誤判時解出來的是「合法但錯誤的漢字」，
    不會拋例外、不會有 U+FFFD，任何下游檢查都攔不到——parser 照樣吐出
    N 筆亂碼標題推到 LINE。能問頁面就別用猜的。
    """
    encoding = _header_charset(resp)
    if not encoding:
        encoding = _meta_charset(resp.content)
    if not encoding:
        encoding = resp.apparent_encoding or "utf-8"
        # 推斷是最後手段，留一行紀錄讓 Actions log 看得到用了什麼
        print(f"    ℹ️ {getattr(resp, 'url', '?')} 未宣告編碼，推斷為 {encoding}")

    resp.encoding = encoding
    return resp.text


def _should_retry(error: requests.RequestException) -> bool:
    """只重試「等一下可能會好」的失敗。

    raise_for_status 拋的 HTTPError 也是 RequestException，若一律重試，
    站方改網址（404）或擋爬蟲（403）這種永久性失敗會白白多打兩次。
    """
    if isinstance(error, requests.HTTPError):
        resp = error.response
        if resp is None:
            return False
        return resp.status_code == 429 or resp.status_code >= 500
    return True   # 連線、逾時、DNS 等傳輸類一律重試


def get(url: str, timeout: int = 30, attempts: int = 3) -> str:
    """抓一個頁面回傳解碼後的 HTML 字串。"""
    if attempts < 1:
        raise ValueError("attempts 至少要 1")

    last_error = None
    for i in range(attempts):
        try:
            resp = requests.get(url, headers=UA, timeout=timeout)
            resp.raise_for_status()
            return _decode(resp)
        except requests.RequestException as e:
            last_error = e
            if not _should_retry(e):
                break
            if i == attempts - 1:
                break
            wait = 2 ** i
            print(f"    ⚠️ 抓取失敗（{type(e).__name__}），{wait}s 後重試（{i + 2}/{attempts}）")
            time.sleep(wait)
    raise last_error
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_society_fetch.py -v -m "not live"`
Expected: 8 passed, 1 deselected

- [ ] **Step 5: 跑一次 live 測試確認真實站點沒問題**

Run: `python3 -m pytest tests/test_society_fetch.py -v -m live`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add society_watch/fetch.py tests/test_society_fetch.py
git commit -m "feat(society-watch): 抓取層與無 charset 站的編碼修正"
```

---

## Task 10: 來源設定表（含 PAIN 跨年）

**Files:**
- Create: `society_watch/sources.py`
- Create: `tests/test_society_sources.py`

**已實測的漏報陷阱：** pain.org.tw 的列表是「年份 × 分類」scoped，預設只回當年。實抓 2026 年 10 筆全部已過期（最新 8/23，抓取日 9/10），代表明年度活動一旦公告**不會出現在預設頁面**。必須抓今年＋明年兩次。

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_society_sources.py`：

```python
"""來源設定表測試。"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch import sources  # noqa: E402


def test_五個來源代號齊全():
    assert {s["source"] for s in sources.SOURCES} == {
        "TSA", "TSCVA", "RAPM", "PAIN", "AIRWAY"
    }


def test_pain同時抓今年與明年():
    urls = sources.pain_urls(date(2026, 9, 10))
    assert len(urls) == 2
    assert "yy=2026" in urls[0]
    assert "yy=2027" in urls[1]


def test_pain跨年時自動往後推():
    urls = sources.pain_urls(date(2027, 1, 5))
    assert "yy=2027" in urls[0]
    assert "yy=2028" in urls[1]


def test_rapm有兩個分類():
    rapm = [s for s in sources.SOURCES if s["source"] == "RAPM"]
    assert len(rapm) == 2
    assert {s["kind"] for s in rapm} == {"學會活動", "友會活動"}


def test_每個來源都有網址與parser名稱():
    for s in sources.SOURCES:
        assert s["url"].startswith("https://")
        assert s["parser"]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_society_sources.py -v`
Expected: **collection error**（不是 test failed）——`ImportError: cannot import name 'sources' from 'society_watch'`，pytest 顯示 `1 error`

- [ ] **Step 3: 實作**

建立 `society_watch/sources.py`：

```python
"""監測來源設定表。全部經 2026-09-10 實抓驗證。"""
from datetime import date

# 疼痛醫學會的 AJAX fragment endpoint（從頁面 JS 的 $("#main_content").load(...) 挖出，
# 實測免 cookie、免 session 可直接抓）。非公開 API，改版風險高於其他四站。
PAIN_ENDPOINT = (
    "https://pain.org.tw/index.php/educlass_page/educlass_page1_content/33/1/8/0"
)

SOURCES = [
    {
        "source": "TSA",
        "label": "台灣麻醉醫學會",
        "url": "https://www.anesth.org.tw/events/index.asp",
        "parser": "tsa",
    },
    {
        "source": "TSCVA",
        "label": "心臟胸腔暨血管麻醉醫學會",
        # 用 /news 完整列表，不用首頁摘要（兩者 class 不同，詳見 extract.parse_tscva）
        "url": "https://congress.tscva.org.tw/news",
        "parser": "tscva",
    },
    {
        "source": "RAPM",
        "label": "區域麻醉暨疼痛醫學會",
        "url": "https://rapm.org.tw/news-list/2",
        "parser": "rapm",
        "kind": "學會活動",
    },
    {
        "source": "RAPM",
        "label": "區域麻醉暨疼痛醫學會",
        "url": "https://rapm.org.tw/news-list/5",
        "parser": "rapm",
        "kind": "友會活動",
    },
    {
        "source": "PAIN",
        "label": "台灣疼痛醫學會",
        "url": PAIN_ENDPOINT,     # 實際抓取時由 pain_urls() 補上 ?yy=
        "parser": "pain",
    },
    {
        "source": "AIRWAY",
        "label": "台灣呼吸道處理醫學會",
        "url": "https://www.tsamairway.org.tw/最新資訊",
        "parser": "airway",
    },
]

# 通知訊息裡的分組順序與顯示名稱
LABELS = {s["source"]: s["label"] for s in SOURCES}


def pain_urls(today: date) -> list[str]:
    """疼痛醫學會要抓今年＋明年兩份。

    該列表是「年份 scoped」且預設只回當年，明年度活動一旦公告
    不會出現在預設頁面，只抓當年會造成漏報。
    """
    return [f"{PAIN_ENDPOINT}?yy={today.year + n}" for n in (0, 1)]
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_society_sources.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add society_watch/sources.py tests/test_society_sources.py
git commit -m "feat(society-watch): 來源設定表與 PAIN 跨年漏報防護"
```

---

## Task 11: 訊息格式化與拆分

**Files:**
- Create: `society_watch/notify.py`
- Create: `tests/test_society_notify.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_society_notify.py`：

```python
"""通知格式化測試。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch import notify  # noqa: E402
from society_watch.models import Event  # noqa: E402

TSA_EVENT = Event(
    source="TSA", uid="3105",
    title="2026年特管法輕中度鎮靜課程_1108高醫場",
    date_text="115/11/08",
    url="https://www.anesth.org.tw/events/content.asp?ID=3105&EduType=4",
    kind="鎮靜活動",
    place="高雄醫學大學臨床技能中心",
)
MINOR_EVENT = Event(
    source="TSCVA", uid="abc",
    title="2026 年度專科醫師甄審通過名單",
    date_text="2026-09-01",
    url="https://congress.tscva.org.tw/news/abc",
    minor=True,
)


def test_標題顯示則數():
    msg = notify.format_message([TSA_EVENT, MINOR_EVENT])
    assert msg.startswith("🔔 學會新活動 2 則")


def test_依學會分組並顯示日期與地點():
    msg = notify.format_message([TSA_EVENT])
    assert "【台灣麻醉醫學會】" in msg
    assert "115/11/08｜高雄醫學大學臨床技能中心" in msg
    assert "https://www.anesth.org.tw/events/content.asp?ID=3105&EduType=4" in msg


def test_minor項目排在其他公告區():
    msg = notify.format_message([MINOR_EVENT, TSA_EVENT])
    assert "── 其他公告 ──" in msg
    assert msg.index("鎮靜課程") < msg.index("── 其他公告 ──")
    assert msg.index("── 其他公告 ──") < msg.index("甄審通過名單")


def test_全部都是minor時仍有其他公告區():
    msg = notify.format_message([MINOR_EVENT])
    assert "── 其他公告 ──" in msg


def test_沒有minor時不出現其他公告區():
    assert "── 其他公告 ──" not in notify.format_message([TSA_EVENT])


def test_無地點時只顯示日期():
    e = Event(source="PAIN", uid="1", title="工作坊", date_text="2026 八月 23",
              url="https://pain.org.tw/x")
    assert "2026 八月 23\n" in notify.format_message([e])


def test_短訊息不拆分():
    assert notify.split_message("短訊息") == ["短訊息"]


def test_長訊息在學會邊界拆分():
    body = "\n\n".join(f"【學會{i}】\n" + "・活動\n" * 100 for i in range(6))
    parts = notify.split_message(body, max_chars=1000)
    assert len(parts) > 1
    assert all(len(p) <= 1000 for p in parts)
    # 六個學會區塊都完整保留，沒有被切掉
    # （不能斷言每段開頭都是「【」：最後一段開頭是「⬆️ 接上頁」標記）
    assert sum(p.count("【學會") for p in parts) == 6


def test_單一區塊超長時硬切():
    parts = notify.split_message("【學會】\n" + "字" * 3000, max_chars=1000)
    assert all(len(p) <= 1000 for p in parts)


def test_告警訊息列出失敗站別():
    msg = notify.format_alert([("TSA", "解析出 0 筆，疑似改版"), ("PAIN", "HTTP 500")])
    assert "TSA" in msg and "疑似改版" in msg
    assert "PAIN" in msg and "HTTP 500" in msg
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_society_notify.py -v`
Expected: **collection error**（不是 test failed）——`ImportError: cannot import name 'notify' from 'society_watch'`，pytest 顯示 `1 error`

- [ ] **Step 3: 實作**

建立 `society_watch/notify.py`：

```python
"""訊息格式化、拆分與 LINE 推播。"""
import os

import requests

from .models import Event
from .sources import LABELS, SOURCES

MAX_CHARS = 4800       # LINE 上限 5000，留 200 buffer（同 daily_push.py）
MARKER_RESERVE = 40    # 接頁標記「⬇️ 接下頁（1/3）」的空間，先扣掉才不會加完超標

# 分組顯示順序，依 SOURCES 出現順序去重
SOURCE_ORDER = list(dict.fromkeys(s["source"] for s in SOURCES))


def _format_one(event: Event) -> str:
    parts = [f"・{event.title}"]
    detail = event.date_text
    if event.place:
        detail = f"{detail}｜{event.place}" if detail else event.place
    if detail:
        parts.append(f"  {detail}")
    parts.append(f"  {event.url}")
    return "\n".join(parts)


def format_message(events: list[Event]) -> str:
    """依學會分組；非活動類公告降到底部「其他公告」區。"""
    main = [e for e in events if not e.minor]
    minor = [e for e in events if e.minor]

    blocks = [f"🔔 學會新活動 {len(events)} 則"]

    for source in SOURCE_ORDER:
        group = [e for e in main if e.source == source]
        if not group:
            continue
        lines = [f"【{LABELS.get(source, source)}】"]
        lines.extend(_format_one(e) for e in group)
        blocks.append("\n".join(lines))

    if minor:
        lines = ["── 其他公告 ──"]
        for e in minor:
            lines.append(f"・【{LABELS.get(e.source, e.source)}】{e.title}")
            lines.append(f"  {e.url}")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def split_message(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """在學會區塊邊界（空行）切割，確保每則 ≤ max_chars。"""
    if len(text) <= max_chars:
        return [text]

    # 先扣掉接頁標記的空間，否則加上標記後每則反而會超過 LINE 上限
    budget = max_chars - MARKER_RESERVE
    chunks = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= budget:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        # 單一區塊本身就超長，只能硬切
        while len(block) > budget:
            chunks.append(block[:budget])
            block = block[budget:]
        current = block
    if current:
        chunks.append(current)

    total = len(chunks)
    if total == 1:
        return chunks
    return [
        c + f"\n\n⬇️ 接下頁（{i + 1}/{total}）" if i < total - 1
        else f"⬆️ 接上頁（{i + 1}/{total}）\n\n" + c
        for i, c in enumerate(chunks)
    ]


def format_alert(failures: list[tuple[str, str]]) -> str:
    lines = ["⚠️ 學會監測異常", ""]
    lines.extend(f"・{source}：{reason}" for source, reason in failures)
    lines.append("")
    lines.append("請確認該站是否改版或搬家。")
    return "\n".join(lines)


def push_line(text: str) -> None:
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {os.environ['LINE_CHANNEL_ACCESS_TOKEN']}",
            "Content-Type": "application/json",
        },
        json={
            "to": os.environ["LINE_USER_ID"],
            "messages": [{"type": "text", "text": text}],
        },
        timeout=30,
    )
    resp.raise_for_status()
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_society_notify.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add society_watch/notify.py tests/test_society_notify.py
git commit -m "feat(society-watch): 通知格式化、區塊邊界拆分與 LINE 推播"
```

---

## Task 12: 告警節流

**Files:**
- Modify: `society_watch/state.py`
- Modify: `tests/test_society_state.py`

**規則：** 同一站 7 天內最多告警一次，避免站掛掉時天天吵。

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_society_state.py` 末尾追加：

先把測試檔頂端的 import 區改成（新增 `from datetime import date` 一行）：

```python
import json
import sys
from datetime import date
from pathlib import Path
```

再於檔案末尾追加：

```python
def test_首次失敗就告警():
    assert state.should_alert({}, "TSA", date(2026, 9, 10)) is True


def test_七天內重複失敗不再告警():
    alerts = {"TSA": "2026-09-10"}
    assert state.should_alert(alerts, "TSA", date(2026, 9, 14)) is False


def test_滿七天後再次告警():
    alerts = {"TSA": "2026-09-10"}
    assert state.should_alert(alerts, "TSA", date(2026, 9, 17)) is True


def test_不同站各自計算節流():
    alerts = {"TSA": "2026-09-10"}
    assert state.should_alert(alerts, "PAIN", date(2026, 9, 11)) is True


def test_告警紀錄讀寫(tmp_path):
    p = tmp_path / "alerts.json"
    assert state.load_alerts(p) == {}
    state.save_alerts(p, {"TSA": "2026-09-10"})
    assert state.load_alerts(p) == {"TSA": "2026-09-10"}
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_society_state.py -k alert -v`
Expected: FAIL，`AttributeError: module 'society_watch.state' has no attribute 'should_alert'`

- [ ] **Step 3: 實作**

在 `society_watch/state.py` 頂端 import 區追加 `from datetime import date, timedelta`，並在檔案末尾追加：

```python
ALERT_COOLDOWN_DAYS = 7


def load_alerts(path: Path) -> dict[str, str]:
    if not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_alerts(path: Path, alerts: dict[str, str]) -> None:
    Path(path).write_text(
        json.dumps(alerts, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def should_alert(alerts: dict[str, str], source: str, today: date) -> bool:
    """同一站 7 天內最多告警一次，避免站掛掉時天天吵。"""
    last = alerts.get(source)
    if not last:
        return True
    return today - date.fromisoformat(last) >= timedelta(days=ALERT_COOLDOWN_DAYS)
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_society_state.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add society_watch/state.py tests/test_society_state.py
git commit -m "feat(society-watch): 告警節流，同站七天最多一次"
```

---

## Task 13: 主流程串接

**Files:**
- Create: `society_watch/main.py`
- Create: `tests/test_society_main.py`

**三個必要行為：**
1. 單站失敗**不中斷其他站**
2. HTTP 200 但解析出 0 筆 → 視為疑似改版並告警
3. `--bootstrap` 只寫狀態檔不推播（否則首次執行會把約 50 則一次推出洗版）

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_society_main.py`：

```python
"""主流程測試。以假的抓取函式取代網路。"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch import main  # noqa: E402
from society_watch.models import Event  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "society_watch"

EMPTY_TABLE = "<table class='table'><tbody></tbody></table>"


def _fake_fetch(mapping, failures=None):
    failures = failures or {}

    def _get(url, **kwargs):
        for key, exc in failures.items():
            if key in url:
                raise exc
        # PAIN 會被抓兩次（今年＋明年）；明年度實際上是空表，
        # 若不分開處理會把同一份 fixture 回兩次，筆數多算 10 筆
        if "educlass_page1_content" in url and "yy=2027" in url:
            return EMPTY_TABLE
        for key, name in mapping.items():
            if key in url:
                return (FIXTURES / name).read_text(encoding="utf-8")
        return "<html></html>"

    return _get


ALL_OK = {
    "anesth.org.tw": "tsa_events_20260910.html",
    "congress.tscva.org.tw": "tscva_news_20260910.html",
    "news-list/2": "rapm_newslist2_20260910.html",
    "news-list/5": "rapm_newslist5_20260910.html",
    "educlass_page1_content": "pain_fragment_20260910.html",
}

# TSA 15 + TSCVA 6 + RAPM 16 + RAPM 11 + PAIN 10（今年）+ 0（明年空表）
TOTAL_EVENTS = 58


@pytest.fixture
def env(tmp_path, monkeypatch):
    """把狀態檔導到 tmp、攔截推播、AIRWAY 預設成功但無新增。"""
    pushed = []
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main.fetch, "get", _fake_fetch(ALL_OK))
    monkeypatch.setattr(main, "collect_airway", lambda: ([], ["A", "B"], None))
    monkeypatch.setattr(main.notify, "push_line", lambda text: pushed.append(text))
    return tmp_path, pushed, monkeypatch


def test_收集五站事件(env):
    events, failures, airway_lines = main.collect(date(2026, 9, 10))
    assert failures == []
    assert len(events) == TOTAL_EVENTS
    assert airway_lines == ["A", "B"]


def test_單站失敗不中斷其他站(env, monkeypatch):
    import requests
    monkeypatch.setattr(
        main.fetch, "get",
        _fake_fetch(ALL_OK, failures={"congress.tscva.org.tw": requests.ConnectionError("斷線")}),
    )
    events, failures, _ = main.collect(date(2026, 9, 10))
    assert [f[0] for f in failures] == ["TSCVA"]
    assert any(e.source == "TSA" for e in events)
    assert not any(e.source == "TSCVA" for e in events)


def test_解析出零筆視為疑似改版(env, monkeypatch):
    # 拿掉 TSA 的對應，讓它抓到一個 HTTP 200 但沒有活動的空頁
    without_tsa = {k: v for k, v in ALL_OK.items() if "anesth" not in k}
    monkeypatch.setattr(main.fetch, "get", _fake_fetch(without_tsa))
    events, failures, _ = main.collect(date(2026, 9, 10))
    assert ("TSA", "解析出 0 筆，疑似改版") in failures
    assert any(e.source == "RAPM" for e in events)   # 其他站不受影響


def test_airway失敗時不回傳快照行(env, monkeypatch):
    monkeypatch.setattr(main, "collect_airway", lambda: ([], ["半截"], "行數暴跌"))
    _, failures, airway_lines = main.collect(date(2026, 9, 10))
    assert ("AIRWAY", "行數暴跌") in failures
    assert airway_lines is None


def test_bootstrap只寫狀態不推播(env):
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    assert pushed == []
    assert len(main.state.load_seen(tmp_path / "seen.json")) == TOTAL_EVENTS
    assert main.state.load_snapshot(tmp_path / "airway_snapshot.txt") == ["A", "B"]


def test_第二次執行沒有新項目就不推播(env):
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    main.run(bootstrap=False, today=date(2026, 9, 11))
    assert pushed == []


def test_有新項目就推播(env):
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    seen = main.state.load_seen(tmp_path / "seen.json")
    seen.discard("TSA:3105")
    main.state.save_seen(tmp_path / "seen.json", seen)

    main.run(bootstrap=False, today=date(2026, 9, 11))
    assert len(pushed) == 1
    assert "3105" in pushed[0]


def test_推播失敗時狀態不前進(env, monkeypatch):
    # 寫檔成功但推播失敗會造成永久漏報，所以狀態必須排在推播之後
    tmp_path, _, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    seen_before = main.state.load_seen(tmp_path / "seen.json")
    seen_before.discard("TSA:3105")
    main.state.save_seen(tmp_path / "seen.json", seen_before)
    monkeypatch.setattr(main, "collect_airway", lambda: ([], ["A", "B", "C 新公告"], None))

    def boom(text):
        raise RuntimeError("LINE 掛了")

    monkeypatch.setattr(main.notify, "push_line", boom)
    with pytest.raises(RuntimeError):
        main.run(bootstrap=False, today=date(2026, 9, 11))

    # seen 沒補回 3105、快照也沒吃掉那行新公告 → 下一輪還會重推
    assert "TSA:3105" not in main.state.load_seen(tmp_path / "seen.json")
    assert main.state.load_snapshot(tmp_path / "airway_snapshot.txt") == ["A", "B"]


def test_事件推播失敗時告警仍已送出(env, monkeypatch):
    # 告警排在事件推播之前，否則推播一炸，當天的異常告警也一起消失
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))

    import requests
    monkeypatch.setattr(
        main.fetch, "get",
        _fake_fetch(ALL_OK, failures={"congress.tscva.org.tw": requests.ConnectionError("斷線")}),
    )
    sent = []

    def push(text):
        sent.append(text)
        if not text.startswith("⚠️"):
            raise RuntimeError("LINE 掛了")

    monkeypatch.setattr(main.notify, "push_line", push)
    monkeypatch.setattr(main, "collect_airway", lambda: ([], ["A", "B", "新的一行"], None))
    with pytest.raises(RuntimeError):
        main.run(bootstrap=False, today=date(2026, 9, 11))

    assert any(t.startswith("⚠️") for t in sent)


def test_bootstrap遇到失敗站會提醒重跑(env, monkeypatch, capsys):
    import requests
    monkeypatch.setattr(
        main.fetch, "get",
        _fake_fetch(ALL_OK, failures={"congress.tscva.org.tw": requests.ConnectionError("斷線")}),
    )
    main.run(bootstrap=True, today=date(2026, 9, 10))
    out = capsys.readouterr().out
    assert "TSCVA" in out and "再跑一次 bootstrap" in out
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_society_main.py -v`
Expected: **collection error**（不是 test failed）——`ImportError: cannot import name 'main' from 'society_watch'`，pytest 顯示 `1 error`

- [ ] **Step 3: 實作**

建立 `society_watch/main.py`：

```python
"""學會活動監測主流程。

用法：
    python3 -m society_watch.main --bootstrap   # 首次執行：只寫狀態檔，不推播
    python3 -m society_watch.main               # 日常執行
"""
import argparse
import traceback
from datetime import date
from pathlib import Path

from . import extract, fetch, llm, notify, state
from .models import Event
from .sources import SOURCES, pain_urls

DATA_DIR = Path(__file__).resolve().parent

PARSERS = {
    "tsa": lambda html, cfg: extract.parse_tsa(html),
    "tscva": lambda html, cfg: extract.parse_tscva(html),
    "rapm": lambda html, cfg: extract.parse_rapm(html, kind=cfg["kind"]),
    "pain": lambda html, cfg: extract.parse_pain(html),
}


def collect_airway() -> tuple[list[Event], list[str], str | None]:
    """回傳（事件, 本次全文行, 失敗原因）。

    只有 diff 出現新增行時才呼叫 Haiku，沒新增就完全不呼叫。

    注意 llm.classify() 在「回應無法解析」與「新增量異常」時會拋
    LLMResponseError，由 collect() 的 except 接住 → 記成 AIRWAY 失敗 →
    告警 + 不更新快照 + 下輪重試。這條路徑是刻意的：若改成回空 list，
    模型回垃圾就會偽裝成「今天沒有活動」，快照照樣前進而永久漏報。
    """
    cfg = next(s for s in SOURCES if s["source"] == "AIRWAY")
    html = fetch.get(cfg["url"])
    lines = extract.airway_lines(html)

    previous = state.load_snapshot(DATA_DIR / "airway_snapshot.txt")
    if previous and len(lines) < len(previous) * 0.5:
        return [], lines, f"純文字行數自 {len(previous)} 暴跌至 {len(lines)}，疑似改版"

    new_lines = extract.airway_new_lines(lines, previous)
    if not previous:
        # 首次執行：只建立快照，不送 LLM
        return [], lines, None
    return llm.classify(new_lines), lines, None


def collect(today: date) -> tuple[list[Event], list[tuple[str, str]], list[str] | None]:
    """逐站抓取與解析。單站失敗不影響其他站。

    回傳（事件, 失敗清單, AIRWAY 本次全文行）。第三個值為 None 代表
    AIRWAY 這輪失敗，呼叫端就**不可以**推進快照——快照是 AIRWAY 對
    「什麼是新的」的唯一記憶，另外四站每輪重抓完整列表可自我修復，
    只有它沒有第二份備援。
    """
    events: list[Event] = []
    failures: list[tuple[str, str]] = []

    for cfg in SOURCES:
        source = cfg["source"]
        if cfg["parser"] == "airway":
            continue
        urls = pain_urls(today) if cfg["parser"] == "pain" else [cfg["url"]]
        try:
            found: list[Event] = []
            for url in urls:
                found.extend(PARSERS[cfg["parser"]](fetch.get(url), cfg))
        except Exception as e:
            print(f"  ❌ {source} 抓取失敗：{type(e).__name__}: {e}")
            failures.append((source, f"{type(e).__name__}: {e}"))
            continue

        # found 是該站所有 URL 的累加結果。PAIN 的明年度清單正常為空，
        # 但今年＋明年全空就確實異常，故此處統一判斷即可。
        if not found:
            failures.append((source, "解析出 0 筆，疑似改版"))
            print(f"  ⚠️ {source} 解析出 0 筆，疑似改版")
            continue

        print(f"  ✅ {source}（{cfg.get('kind', '-')}）{len(found)} 筆")
        events.extend(found)

    airway_lines_now: list[str] | None = None
    try:
        airway_events, lines, airway_error = collect_airway()
        if airway_error:
            failures.append(("AIRWAY", airway_error))
        else:
            events.extend(airway_events)
            airway_lines_now = lines
            print(f"  ✅ AIRWAY {len(airway_events)} 筆")
    except Exception as e:
        print(f"  ❌ AIRWAY 抓取失敗：{type(e).__name__}: {e}")
        traceback.print_exc()
        failures.append(("AIRWAY", f"{type(e).__name__}: {e}"))

    return events, failures, airway_lines_now


def run(bootstrap: bool = False, today: date | None = None) -> None:
    today = today or date.today()
    seen_path = DATA_DIR / "seen.json"
    snapshot_path = DATA_DIR / "airway_snapshot.txt"
    alerts_path = DATA_DIR / "alert_state.json"

    print(f"執行日期：{today}｜模式：{'bootstrap' if bootstrap else '日常'}")
    events, failures, airway_lines_now = collect(today)

    seen = state.load_seen(seen_path)
    fresh = state.filter_new(events, seen)
    print(f"抓到 {len(events)} 筆，其中新項目 {len(fresh)} 筆")

    def advance_state() -> None:
        """把狀態推進到「已通知」。只在推播成功後呼叫。"""
        state.save_seen(seen_path, seen | {e.key for e in events})
        if airway_lines_now is not None:
            state.save_snapshot(snapshot_path, airway_lines_now)

    if bootstrap:
        advance_state()
        print("bootstrap 模式：只寫狀態檔，不推播。")
        if failures:
            names = "、".join(source for source, _ in failures)
            print(
                f"⚠️ {names} 本次失敗，未種進狀態檔。"
                "修好後請再跑一次 bootstrap，否則下次成功時會把該站現存項目一次推出。"
            )
        return

    # 告警先送：事件推播若拋例外，當天的異常告警才不會跟著一起消失
    if failures:
        alerts = state.load_alerts(alerts_path)
        due = [f for f in failures if state.should_alert(alerts, f[0], today)]
        if due:
            notify.push_line(notify.format_alert(due))
            for source, _ in due:
                alerts[source] = today.isoformat()
            state.save_alerts(alerts_path, alerts)
            print(f"已送出 {len(due)} 則告警。")
        else:
            print("有失敗但都在告警冷卻期內，不重複告警。")

    if fresh:
        for part in notify.split_message(notify.format_message(fresh)):
            notify.push_line(part)
        print(f"已推播 {len(fresh)} 則。")
    else:
        print("沒有新項目，不推播。")

    # 推播成功才推進狀態。push_line 內的 raise_for_status 會讓失敗穿出去，
    # 於是這行到不了，下一輪重推——重複優於漏報。
    advance_state()


def main() -> None:
    parser = argparse.ArgumentParser(description="學會活動監測與推播")
    parser.add_argument(
        "--bootstrap", action="store_true",
        help="首次執行：只建立狀態檔，不推播（避免把現存約 50 則一次推出）",
    )
    args = parser.parse_args()
    run(bootstrap=args.bootstrap)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_society_main.py -v`
Expected: 11 passed

- [ ] **Step 5: 全套測試回歸**

Run: `python3 -m pytest tests/ -v -m "not live"`
Expected: 全數 passed，且既有的 `test_fx_rate` 等測試不受影響

- [ ] **Step 6: Commit**

```bash
git add society_watch/main.py tests/test_society_main.py
git commit -m "feat(society-watch): 主流程串接、逐站錯誤隔離與 bootstrap 模式"
```

---

## Task 14: GitHub Actions 排程與首次上線

**Files:**
- Create: `.github/workflows/society-watch.yml`

- [ ] **Step 1: 建立 workflow**

建立 `.github/workflows/society-watch.yml`：

```yaml
name: 學會活動監測

on:
  schedule:
    # 每日 02:00 UTC = 10:00 台灣時間，與日報的 08:45／09:05 錯開
    - cron: '0 2 * * *'
  workflow_dispatch:
    inputs:
      bootstrap:
        description: '首次執行：只建立狀態檔不推播（填 true）'
        required: false
        default: ''

permissions:
  contents: write

jobs:
  watch:
    runs-on: ubuntu-latest
    # 最壞情況實測約 11 分鐘（7 個 URL × 重試 3 次 × timeout 30s ＋ 退避）。
    # Actions 預設是 360 分鐘，遇到慢速滴水的伺服器會空轉數小時佔住額度，
    # 不如快死快重試——狀態檔只在推播成功後才寫，被砍不會漏報，只會重推。
    timeout-minutes: 20

    steps:
      - uses: actions/checkout@v4
        with:
          ref: main

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install anthropic requests beautifulsoup4

      - name: Run society watch
        env:
          CLAUDE_API_KEY: ${{ secrets.CLAUDE_API_KEY }}
          LINE_CHANNEL_ACCESS_TOKEN: ${{ secrets.LINE_CHANNEL_ACCESS_TOKEN }}
          LINE_USER_ID: ${{ secrets.LINE_USER_ID }}
        run: |
          if [ "${{ github.event.inputs.bootstrap }}" = "true" ]; then
            python3 -m society_watch.main --bootstrap
          else
            python3 -m society_watch.main
          fi

      - name: Commit state
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add society_watch/seen.json society_watch/airway_snapshot.txt society_watch/alert_state.json
          if git diff --cached --quiet; then
            echo "狀態無變化，不 commit。"
          else
            git commit -m "chore: update society watch state [skip ci]"
            git push
          fi
```

- [ ] **Step 2: 本機乾跑一次確認能抓到真實資料**

Run:
```bash
LINE_CHANNEL_ACCESS_TOKEN=dummy LINE_USER_ID=dummy python3 -m society_watch.main --bootstrap
```
Expected: 印出六列 `✅`（TSA/TSCVA/RAPM×2/PAIN/AIRWAY），總筆數約 55–60，末行為 `bootstrap 模式：只寫狀態檔，不推播。`，且產生 `society_watch/seen.json` 與 `society_watch/airway_snapshot.txt`。

- [ ] **Step 3: 檢查狀態檔格式**

Run: `head -5 society_watch/seen.json && tail -c 20 society_watch/seen.json | xxd | tail -1`
Expected: 一則一行、排序、結尾有換行（`0a`）

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/society-watch.yml society_watch/seen.json society_watch/airway_snapshot.txt
git commit -m "feat(society-watch): GitHub Actions 每日排程"
git push
```

- [ ] **Step 5: 設定 GitHub Secrets（需使用者操作）**

在 repo 的 Settings → Secrets and variables → Actions 新增：

- `LINE_USER_ID`：使用者個人 LINE userId

> ⚠️ **userId 綁定 bot channel**：麻醉日報那支 bot 取得的 userId，與 MCP plugin 那支 bot 的 userId **不同、不可互用**。必須用實際推播的那支 bot（即 `LINE_CHANNEL_ACCESS_TOKEN` 所屬的 channel）取得：把該 bot 加為好友後傳一則訊息，從 webhook log 撈 `events[0].source.userId`。
>
> `CLAUDE_API_KEY` 與 `LINE_CHANNEL_ACCESS_TOKEN` 已存在，沿用即可。

- [ ] **Step 6: 手動觸發驗證**

在 Actions 頁面手動觸發「學會活動監測」，**input 留空**（非 bootstrap）。因為 Step 4 已把 bootstrap 產生的 `seen.json` commit 進去，這次應該是 `沒有新項目，不推播。`

接著為了驗證推播真的會動，暫時從 `society_watch/seen.json` 刪掉一則（例如 `"TSA:3105"`）後 push，再手動觸發一次，確認 LINE 收得到訊息。驗證完把該筆補回或讓它自然留在 seen 裡即可。

---

## 完成後的驗收標準

- [ ] `python3 -m pytest tests/ -m "not live"` 全數通過
- [ ] `python3 -m pytest tests/ -m live` 通過（實際連 TSA 不亂碼）
- [ ] 本機 bootstrap 跑得出六列 `✅`，總筆數 55–60
- [ ] `society_watch/seen.json` 為排序、一則一行、結尾有換行
- [ ] GitHub Actions 手動觸發成功，LINE 收得到測試推播
- [ ] 既有的日報 workflow 未受影響（`daily-fetch-classify` / `daily-push` 照常）
