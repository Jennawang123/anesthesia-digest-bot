# 點數促銷監測（points-watch）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每天檢查三個哩程部落格的 RSS，發現 9 個指定計畫的買點／買哩程促銷時，算出每點成本、對照歷史最佳價評等，把 🟢／🟡 推到使用者的 LINE。

**Architecture:** 新增 `points_watch/` 套件，形狀比照 `society_watch/`：GitHub Actions cron → 抓 RSS → 標題關鍵字篩選 → Haiku 抽成結構化 `Promo` → 純函式評等 → LINE push → 狀態檔 commit 回 repo。HTTP、LINE 推送、告警節流、心跳全部 import `society_watch` 既有函式，不複製。

**Tech Stack:** Python 3.11、`requests`、`anthropic`（`claude-haiku-4-5`）、標準函式庫 `xml.etree.ElementTree`、pytest、GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-10-09-points-promo-watch-design.md`

**本計畫不含國泰世華（`CUB`）。** 2026-10-09 實抓確認 `…/point-exchange/airmiles.model.json` 可取得靜態 JSON，但該頁目前只有常態兌換比率，無法驗證加贈活動上線時會出現在哪一頁。RSS 管線上線並驗收後另開計畫處理（spec §5）。

---

## 寫計畫前已實抓驗證的事實（2026-10-09）

實作者不需重新驗證，但所有解析邏輯都必須以這些事實為準：

1. 三個 feed 都是標準 WordPress RSS 2.0：`rss/channel/item` 下有 `title`、`link`、`pubDate`（RFC 822）、`description`（含 HTML 的短摘要）、`content:encoded`（全文，很大）。
2. 每頁篇數少：Loyalty Lobby 14 篇（約兩天份）、OMAAT 25 篇、Frequent Miler 20 篇。`?paged=2` 三家都可用。**只抓第一頁的話，Actions 延遲或單日失敗就會漏文，所以預設抓兩頁。**
3. Loyalty Lobby 的 `link` 帶 `?omhide=true`；同一篇文章的 URL 必須去掉 query 才能比對。
4. **OMAAT 每個計畫共用一個固定網址**（例 `/deals/buy-ihg-one-rewards-points/`），每次新促銷只更新內容與 `pubDate`。因此「看過的文章」不能只用 URL 當鍵，必須是 `URL|發布日`。
5. Loyalty Lobby 的 `/tag/…/feed/` 與 `?s=…&feed=rss2` 會被 Cloudflare 擋（回 403 與一頁 `<title>Just a moment...</title>` 的 HTML）。只能用主 feed。
6. 標題實例（測試的正反例取自這裡）：
   - 正例：`Buy IHG Points for as low as 0.5 cents each`（Frequent Miler）、`Buy Alaska Atmos Rewards Points With 100% Bonus (1.88 Cents Each): Worth It?`（OMAAT）
   - 命中關鍵字但不是買點促銷（要靠 Haiku 判否）：`Alaska Atmos Rewards’ Global Getaways Award Sale: Save Up To 50%`、`Last Chance Deals: IHG points sale, United portal promo, Hotels.com gift card discount, & more`
   - 關鍵字就該擋掉：`Hilton Honors Buy Points 120% Bonus Sale + Increased Limit October 7 – November 21, 2026`（非追蹤計畫）、`IHG One Rewards Premier Select Credit Card Review: Is The $350 Annual Fee Worth It?`（無購買字眼）、`100% transfer bonus from Wyndham Rewards to United MileagePlus`（轉點）、`(EXPIRED) Newegg: Buy $500 Hotels.com gift cards for $450`
7. 已佐證的價格：IHG 100% 加贈＝0.50¢；Choice 45% 折扣＝0.57¢、40% 折扣＝0.62¢；Alaska 100% 加贈＝1.88¢；United 100% 加贈＝1.88¢；LifeMiles 145% 加贈＝1.35¢；Aeroplan 100% 加贈＝1.35¢。

原始樣本已下載在 `tests/fixtures/points_watch/`（未 commit，Task 2 整理）。

## 檔案結構

| 檔案 | 職責 |
|---|---|
| `points_watch/__init__.py` | 空檔 |
| `points_watch/models.py` | `Article`、`Promo`、`Rated` 三個 dataclass |
| `points_watch/sources.py` | feed 清單、9 個計畫的標籤與關鍵字、`is_candidate()` |
| `points_watch/feeds.py` | RSS 文字 → `list[Article]`（純函式） |
| `points_watch/extract.py` | Haiku：`Article` → `Promo \| None`；回應解析與數值檢查 |
| `points_watch/rating.py` | `Promo` ＋ 基準 → `Rated`；基準檔讀取與最小幅度改寫 |
| `points_watch/baselines.json` | 各計畫原價與歷史最佳每點成本 |
| `points_watch/store.py` | `promos.json` 讀寫、截止提醒判定 |
| `points_watch/notify.py` | 四種訊息排版（純函式） |
| `points_watch/main.py` | 流程串接、CLI |
| `.github/workflows/points-watch.yml` | 排程 |
| `tests/test_points_*.py` | 每個模組一支 |

狀態檔（由 Actions commit）：`points_watch/seen_articles.json`、`promos.json`、`alert_state.json`、`heartbeat.json`。

所有指令都在 repo 根目錄執行。macOS 沒有 `python`，一律 `python3`。

---

### Task 1: 查證九家基準價並交使用者確認

**Files:**
- Create: `points_watch/__init__.py`
- Create: `points_watch/baselines.json`

這是整個系統最重要的資料：基準錯了，評等全錯。**本任務完成後必須停下來等使用者確認，才能做 Task 2。**

- [ ] **Step 1: 建立套件與已佐證的六家**

```bash
mkdir -p points_watch && touch points_watch/__init__.py
```

`points_watch/baselines.json`（**一個計畫一行**，`rating.update_best` 靠這個版面做單行取代）：

```json
{
  "IHG":        {"base_cpp": 1.00, "best_cpp": 0.50},
  "CHOICE":     {"base_cpp": 1.03, "best_cpp": 0.57},
  "LIFEMILES":  {"base_cpp": 3.30, "best_cpp": 1.35},
  "AEROPLAN":   {"base_cpp": 2.70, "best_cpp": 1.35},
  "UNITED":     {"base_cpp": 3.76, "best_cpp": 1.88},
  "ALASKA":     {"base_cpp": 3.76, "best_cpp": 1.88}
}
```

`base_cpp` 由已佐證的促銷反推：加贈時 `base = cpp × (1 + percent/100)`，折扣時 `base = cpp ÷ (1 − percent/100)`。例：IHG 0.50 × 2 = 1.00；Choice 0.57 ÷ 0.55 = 1.03。

- [ ] **Step 2: 逐家查證歷史最佳**

對九個計畫各做一次搜尋（WebSearch，mode `extended`），查詢字串：

```
"<計畫英文名>" buy points OR miles "best ever" OR "record" OR "lowest" bonus cents each site:onemileatatime.com OR site:frequentmiler.com OR site:loyaltylobby.com
```

計畫英文名：`IHG One Rewards`、`Choice Privileges`、`Avianca LifeMiles`、`Air Canada Aeroplan`、`United MileagePlus`、`Alaska Atmos Rewards`、`American AAdvantage`、`Flying Blue`、`Virgin Atlantic Flying Club`。

每家記下：歷史最佳每點成本（美分）、對應的加贈或折扣百分比、出處網址、該促銷是否限定對象（targeted）。規則：

- 只採用**公開促銷**的最佳價。限定對象的價格不當基準（否則公開促銷永遠拿不到 🟢），但要在回報中註明。
- 非美元計價的計畫（Flying Blue 歐元、Virgin 英鎊、Aeroplan 加幣）採用部落格換算後的美分報價。
- 找不到「歷史最佳」的明確說法時，取 2025–2026 年間報導過的最低價，並在回報中標「近兩年最低，非確認的歷史最佳」。
- 已知待釐清：Loyalty Lobby 2026-10-02 報導 Alaska「up to 120% bonus」，若為公開促銷，Alaska 的 `best_cpp` 應低於 1.88。

- [ ] **Step 3: 補齊九家並寫回檔案**

把 `AA`、`FLYINGBLUE`、`VIRGIN` 三行加進 `baselines.json`（同樣一家一行、欄位對齊），並依查證結果修正前六家。完成後檔案必須恰有九個鍵：`IHG`、`CHOICE`、`LIFEMILES`、`AEROPLAN`、`UNITED`、`ALASKA`、`AA`、`FLYINGBLUE`、`VIRGIN`。

- [ ] **Step 4: 驗證檔案**

```bash
python3 -c "
import json
d = json.load(open('points_watch/baselines.json'))
want = {'IHG','CHOICE','LIFEMILES','AEROPLAN','UNITED','ALASKA','AA','FLYINGBLUE','VIRGIN'}
assert set(d) == want, set(d) ^ want
for k, v in d.items():
    assert 0.3 <= v['best_cpp'] <= v['base_cpp'] <= 6, (k, v)
print('OK', len(d))
"
```

Expected: `OK 9`

- [ ] **Step 5: 回報使用者並等待確認**

以表格回報九家：計畫、歷史最佳（¢）、對應促銷、出處、備註（限定對象／近兩年最低）。**在使用者回覆確認或修正之前不要繼續。**

- [ ] **Step 6: Commit**

```bash
git add points_watch/__init__.py points_watch/baselines.json
git commit -m "feat(points-watch): 九個計畫的買點基準價"
```

---

### Task 2: 整理實抓樣本成 fixture

**Files:**
- Create: `tests/fixtures/points_watch/loyaltylobby.xml`、`omaat_search.xml`、`frequentmiler_search.xml`、`blocked.html`
- Delete: 該目錄其餘探測檔

原始檔含 `content:encoded` 全文，單檔數百 KB。去掉全文、其餘原樣保留，才是 parser 實際會讀到的欄位。

- [ ] **Step 1: 瘦身並改名**

```bash
python3 - <<'EOF'
import re
from pathlib import Path

d = Path("tests/fixtures/points_watch")
keep = {
    "loyaltylobby.xml": "loyaltylobby.xml",
    "omaat_search.xml": "omaat_search.xml",
    "fm_search.xml": "frequentmiler_search.xml",
}
out = {}
for src, dst in keep.items():
    raw = (d / src).read_bytes()
    raw = re.sub(rb"<content:encoded>.*?</content:encoded>", b"", raw, flags=re.S)
    out[dst] = raw
blocked = (d / "ll_search.xml").read_bytes()

for p in d.iterdir():
    p.unlink()
for name, raw in out.items():
    (d / name).write_bytes(raw)
(d / "blocked.html").write_bytes(blocked)
for p in sorted(d.iterdir()):
    print(p.name, p.stat().st_size)
EOF
```

Expected: 四個檔案，三個 `.xml` 各小於 60 KB，`blocked.html` 約 5–6 KB。

- [ ] **Step 2: 確認關鍵樣本還在**

```bash
grep -c "Buy IHG Points for as low as 0.5 cents each" tests/fixtures/points_watch/frequentmiler_search.xml
grep -c "Buy Alaska Atmos Rewards Points With 100% Bonus" tests/fixtures/points_watch/omaat_search.xml
grep -c "omhide=true" tests/fixtures/points_watch/loyaltylobby.xml
grep -c "Just a moment" tests/fixtures/points_watch/blocked.html
```

Expected: 四行都 ≥ 1。

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/points_watch
git commit -m "test(points-watch): 2026-10-09 實抓的 RSS 樣本"
```

---

### Task 3: 資料模型

**Files:**
- Create: `points_watch/models.py`
- Test: `tests/test_points_models.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/test_points_models.py`：

```python
"""資料模型測試：去重鍵的組成。"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch.models import Article, Promo  # noqa: E402


def _article(url="https://x.test/a", published=date(2026, 10, 2)):
    return Article(feed="omaat", title="t", url=url, published=published, summary="s")


def _promo(**over):
    base = dict(program="IHG", kind="bonus", percent=100, stated_cpp=0.5,
                end_date=date(2026, 10, 31), up_to=True, url="https://x.test/a")
    base.update(over)
    return Promo(**base)


def test_article_key_includes_publish_date():
    # OMAAT 每個計畫共用固定網址，只更新 pubDate；鍵只用 URL 的話，
    # 第一次促銷之後該計畫在 OMAAT 就永遠被當成「看過了」。
    a = _article(published=date(2026, 10, 2))
    b = _article(published=date(2026, 11, 20))
    assert a.key != b.key


def test_article_key_without_date():
    assert _article(published=None).key == "https://x.test/a|"


def test_promo_key_ignores_url_and_stated_cpp():
    # 同一促銷被兩家部落格報導，網址與報價寫法不同，仍是同一筆
    a = _promo(url="https://a.test/1", stated_cpp=0.5)
    b = _promo(url="https://b.test/2", stated_cpp=None)
    assert a.key == b.key == "IHG|bonus|100|2026-10-31"


def test_promo_key_differs_by_end_date():
    assert _promo().key != _promo(end_date=date(2026, 12, 5)).key


def test_promo_key_without_end_date():
    assert _promo(end_date=None).key == "IHG|bonus|100|"
```

- [ ] **Step 2: 確認測試失敗**

Run: `python3 -m pytest tests/test_points_models.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'points_watch.models'`

- [ ] **Step 3: 實作**

`points_watch/models.py`：

```python
"""點數促銷監測的資料結構。"""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Article:
    feed: str
    title: str
    url: str
    published: date | None
    summary: str

    @property
    def key(self) -> str:
        """「看過的文章」的鍵。

        必須含發布日：OMAAT 每個計畫共用一個固定網址，每次新促銷只改內容
        與 pubDate。只用 URL 的話，第一次之後就永遠被當成看過了。
        """
        return f"{self.url}|{self.published.isoformat() if self.published else ''}"


@dataclass(frozen=True)
class Promo:
    program: str            # sources.PROGRAMS 的代號
    kind: str               # "bonus"（加贈）| "discount"（折扣）
    percent: int            # 最高級距的百分比
    stated_cpp: float | None  # 文章寫的每點成本（美分）
    end_date: date | None
    up_to: bool             # 最高可達／分級／限定對象
    url: str

    @property
    def key(self) -> str:
        """「推過的促銷」的鍵。刻意不含 url 與 stated_cpp：
        同一促銷會被多家報導，也會以 last call 重發。"""
        end = self.end_date.isoformat() if self.end_date else ""
        return f"{self.program}|{self.kind}|{self.percent}|{end}"


@dataclass(frozen=True)
class Rated:
    promo: Promo
    cpp: float              # 採用的每點成本（美分，兩位小數）
    best_cpp: float         # 評等當下的歷史最佳
    grade: str              # "green" | "yellow" | "red"
    new_low: bool
    from_article: bool      # True＝採用文章報價而非公式計算值
```

- [ ] **Step 4: 確認測試通過**

Run: `python3 -m pytest tests/test_points_models.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add points_watch/models.py tests/test_points_models.py
git commit -m "feat(points-watch): Article／Promo／Rated 資料模型"
```

---

### Task 4: 來源設定與關鍵字篩選

**Files:**
- Create: `points_watch/sources.py`
- Test: `tests/test_points_sources.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/test_points_sources.py`（標題全部取自 2026-10-09 實抓的 feed）：

```python
"""關鍵字篩選測試。標題皆為實抓樣本。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import sources  # noqa: E402

PASS = [
    "Buy IHG Points for as low as 0.5 cents each",
    "Buy Alaska Atmos Rewards Points With 100% Bonus (1.88 Cents Each): Worth It?",
    "IHG Buy Points Buy Points 100% Bonus Sale Through February 5, 2026",
    "Alaska Airlines Buy Miles Up To 120% Bonus Sale Until October 19, 2026",
    "Buy Choice Privileges Points At 40% Off: 0.62 Cents Each, Worth It?",
    # 以下兩則不是買點促銷，但關鍵字層擋不掉，交給 Haiku 判否
    "Alaska Atmos Rewards’ Global Getaways Award Sale: Save Up To 50%",
    "Last Chance Deals: IHG points sale, United portal promo, Hotels.com gift card discount, & more",
]

BLOCK = [
    "Hilton Honors Buy Points 120% Bonus Sale + Increased Limit October 7 – November 21, 2026",
    "Buy Marriott points for as low as 0.81 cents each",
    "IHG One Rewards Premier Select Credit Card Review: Is The $350 Annual Fee Worth It?",
    "100% transfer bonus from Wyndham Rewards to United MileagePlus",
    "Marriott Bonvoy To Air Canada Aeroplan 15% Points Transfer Bonus: Worth It?",
    "(EXPIRED) Buy Choice Points, get 40% bonus (0.74c per point)",
    "Chase IHG One Rewards Credit Card Eligibility Rules Explained",
    "Southwest sale: Save up to 40% on cash & award flights",
]


@pytest.mark.parametrize("title", PASS)
def test_candidate(title):
    assert sources.is_candidate(title)


@pytest.mark.parametrize("title", BLOCK)
def test_not_candidate(title):
    assert not sources.is_candidate(title)


def test_nine_programs():
    assert set(sources.PROGRAMS) == {
        "IHG", "CHOICE", "LIFEMILES", "AEROPLAN", "UNITED",
        "ALASKA", "AA", "FLYINGBLUE", "VIRGIN",
    }


def test_feed_urls_paginate():
    feed = {"name": "x", "url": "https://x.test/feed/"}
    assert sources.feed_urls(feed, 2) == [
        "https://x.test/feed/", "https://x.test/feed/?paged=2",
    ]
```

- [ ] **Step 2: 確認測試失敗**

Run: `python3 -m pytest tests/test_points_sources.py -v`
Expected: FAIL，`ImportError: cannot import name 'sources'`

- [ ] **Step 3: 實作**

`points_watch/sources.py`：

```python
"""RSS 來源、追蹤的計畫、標題關鍵字篩選。

關鍵字層只求「不漏」：寧可多放幾篇給 Haiku 判否（一篇不到一分錢），
也不要在這層把真促銷擋掉——被擋掉的不會有任何訊號。
"""
import re

# 主 feed 才抓得到。Loyalty Lobby 的 /tag/…/feed/ 與 ?s=…&feed=rss2
# 會被 Cloudflare 回 403（2026-10-09 實測）。
FEEDS = [
    {"name": "loyaltylobby", "url": "https://loyaltylobby.com/feed/"},
    {"name": "omaat", "url": "https://onemileatatime.com/feed/"},
    {"name": "frequentmiler", "url": "https://frequentmiler.com/feed/"},
]

# 每個 feed 預設抓幾頁。Loyalty Lobby 一頁只有 14 篇約兩天份，
# 只抓一頁的話 Actions 延遲或單日失敗就會漏文。
DEFAULT_PAGES = 2

PROGRAMS = {
    "IHG":        {"label": "IHG", "unit": "點", "keywords": ["ihg"]},
    "CHOICE":     {"label": "Choice", "unit": "點", "keywords": ["choice privileges", "choice points", "choice hotels"]},
    "LIFEMILES":  {"label": "LifeMiles", "unit": "哩", "keywords": ["lifemiles"]},
    "AEROPLAN":   {"label": "Aeroplan", "unit": "哩", "keywords": ["aeroplan"]},
    "UNITED":     {"label": "United", "unit": "哩", "keywords": ["mileageplus", "united miles", "united mileage"]},
    "ALASKA":     {"label": "Alaska", "unit": "哩", "keywords": ["alaska", "atmos"]},
    "AA":         {"label": "AAdvantage", "unit": "哩", "keywords": ["aadvantage", "american airlines miles", "american miles"]},
    "FLYINGBLUE": {"label": "Flying Blue", "unit": "哩", "keywords": ["flying blue"]},
    "VIRGIN":     {"label": "Virgin Atlantic", "unit": "哩", "keywords": ["virgin atlantic", "virgin points", "flying club"]},
}

_BUY = re.compile(r"\b(buy|buying|purchase|purchased|purchasing|sale)\b", re.I)
# transfer：轉點加贈常同時出現計畫名與 bonus／sale，但不是買點
_SKIP = re.compile(r"\(expired\)|\btransfer\b", re.I)
_KEYWORDS = [k for p in PROGRAMS.values() for k in p["keywords"]]


def is_candidate(title: str) -> bool:
    """標題是否值得送給 Haiku：命中計畫名＋購買字眼，且不含排除字。"""
    if _SKIP.search(title) or not _BUY.search(title):
        return False
    lowered = title.lower()
    return any(k in lowered for k in _KEYWORDS)


def feed_urls(feed: dict, pages: int) -> list[str]:
    return [feed["url"]] + [f"{feed['url']}?paged={n}" for n in range(2, pages + 1)]
```

- [ ] **Step 4: 確認測試通過**

Run: `python3 -m pytest tests/test_points_sources.py -v`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add points_watch/sources.py tests/test_points_sources.py
git commit -m "feat(points-watch): feed 清單與標題關鍵字篩選"
```

---

### Task 5: RSS 解析

**Files:**
- Create: `points_watch/feeds.py`
- Test: `tests/test_points_feeds.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/test_points_feeds.py`：

```python
"""RSS 解析測試。對 2026-10-09 實抓樣本。"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import feeds  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "points_watch"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_item_counts():
    assert len(feeds.parse_feed(_load("loyaltylobby.xml"), "loyaltylobby")) == 14
    assert len(feeds.parse_feed(_load("omaat_search.xml"), "omaat")) == 25
    assert len(feeds.parse_feed(_load("frequentmiler_search.xml"), "frequentmiler")) == 20


def test_fields_of_ihg_article():
    articles = feeds.parse_feed(_load("frequentmiler_search.xml"), "frequentmiler")
    ihg = next(a for a in articles if a.title == "Buy IHG Points for as low as 0.5 cents each")
    assert ihg.feed == "frequentmiler"
    assert ihg.url == "https://frequentmiler.com/buy-ihg-points/"
    assert isinstance(ihg.published, date)
    assert "100% bonus" in ihg.summary
    assert "<" not in ihg.summary          # HTML 標籤已去除
    assert len(ihg.summary) <= feeds.SUMMARY_MAX


def test_url_query_stripped():
    # Loyalty Lobby 的 link 帶 ?omhide=true
    articles = feeds.parse_feed(_load("loyaltylobby.xml"), "loyaltylobby")
    assert all("?" not in a.url for a in articles)
    assert all(a.url.startswith("https://loyaltylobby.com/") for a in articles)


def test_html_entities_decoded():
    articles = feeds.parse_feed(_load("omaat_search.xml"), "omaat")
    assert not any("&#" in a.title for a in articles)


def test_cloudflare_block_page_raises():
    # 被擋時回的是 HTML。必須拋例外讓 main 記成該 feed 失敗，
    # 不可回空 list——那會跟「今天沒文章」分不出來。
    with pytest.raises(feeds.FeedError):
        feeds.parse_feed(_load("blocked.html"), "loyaltylobby")


def test_non_rss_xml_raises():
    with pytest.raises(feeds.FeedError):
        feeds.parse_feed("<?xml version='1.0'?><html><body/></html>", "x")


def test_item_without_link_skipped():
    xml = ("<rss><channel>"
           "<item><title>no link</title></item>"
           "<item><title>ok</title><link>https://x.test/a?b=1#c</link>"
           "<pubDate>garbage</pubDate></item>"
           "</channel></rss>")
    articles = feeds.parse_feed(xml, "x")
    assert [(a.title, a.url, a.published) for a in articles] == [("ok", "https://x.test/a", None)]
```

- [ ] **Step 2: 確認測試失敗**

Run: `python3 -m pytest tests/test_points_feeds.py -v`
Expected: FAIL，`ImportError: cannot import name 'feeds'`

- [ ] **Step 3: 實作**

`points_watch/feeds.py`：

```python
"""RSS 2.0 文字 → Article。純解析，不碰網路。"""
import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit

from .models import Article

SUMMARY_MAX = 600   # 送給 Haiku 的摘要上限；實測 description 多在 300 字內

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


class FeedError(ValueError):
    """內容不是 RSS（被 Cloudflare 擋、站方改版、回了錯誤頁）。"""


def _clean(text: str | None) -> str:
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", text or ""))).strip()


def _strip_query(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _published(text: str | None):
    try:
        return parsedate_to_datetime(text or "").date()
    except (TypeError, ValueError):
        return None


def parse_feed(xml_text: str, feed: str) -> list[Article]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError as e:
        raise FeedError("RSS 無法解析，可能被擋或改版") from e
    if root.tag != "rss":
        raise FeedError("RSS 無法解析，可能被擋或改版")

    articles = []
    for item in root.findall("./channel/item"):
        link = item.findtext("link")
        title = _clean(item.findtext("title"))
        if not link or not title:
            continue
        articles.append(Article(
            feed=feed,
            title=title,
            url=_strip_query(link),
            published=_published(item.findtext("pubDate")),
            summary=_clean(item.findtext("description"))[:SUMMARY_MAX],
        ))
    return articles
```

- [ ] **Step 4: 確認測試通過**

Run: `python3 -m pytest tests/test_points_feeds.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add points_watch/feeds.py tests/test_points_feeds.py
git commit -m "feat(points-watch): RSS 解析"
```

---

### Task 6: 評等與基準檔

**Files:**
- Create: `points_watch/rating.py`
- Test: `tests/test_points_rating.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/test_points_rating.py`：

```python
"""評等測試：公式、三個等級的邊界、文章報價覆寫、新低、基準檔改寫。"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import rating  # noqa: E402
from points_watch.models import Promo  # noqa: E402

IHG = {"base_cpp": 1.00, "best_cpp": 0.50}


def _promo(kind="bonus", percent=100, stated_cpp=None, program="IHG"):
    return Promo(program=program, kind=kind, percent=percent, stated_cpp=stated_cpp,
                 end_date=date(2026, 10, 31), up_to=False, url="https://x.test/a")


def test_bonus_formula():
    assert rating.rate(_promo(percent=100), IHG).cpp == 0.50
    assert rating.rate(_promo(percent=80), IHG).cpp == 0.56     # 1/1.8=0.5556


def test_discount_formula():
    choice = {"base_cpp": 1.03, "best_cpp": 0.57}
    assert rating.rate(_promo(kind="discount", percent=45), choice).cpp == 0.57
    assert rating.rate(_promo(kind="discount", percent=40), choice).cpp == 0.62


@pytest.mark.parametrize("percent, grade", [
    (100, "green"),    # 0.50，平最佳
    (95, "green"),     # 0.51，在 3% 內（0.515）
    (90, "yellow"),    # 0.53
    (75, "yellow"),    # 0.57，在 15% 內（0.575）
    (70, "red"),       # 0.59
    (50, "red"),       # 0.67
])
def test_grade_boundaries(percent, grade):
    assert rating.rate(_promo(percent=percent), IHG).grade == grade


def test_stated_cpp_overrides_when_far_from_formula():
    # 公式算 0.50，文章寫 0.60（原價調漲或非單純加贈）→ 採文章報價
    r = rating.rate(_promo(percent=100, stated_cpp=0.60), IHG)
    assert (r.cpp, r.from_article, r.grade) == (0.60, True, "red")


def test_stated_cpp_ignored_when_close():
    r = rating.rate(_promo(percent=100, stated_cpp=0.51), IHG)
    assert (r.cpp, r.from_article) == (0.50, False)


def test_new_low():
    r = rating.rate(_promo(percent=110), IHG)     # 1/2.1=0.476 → 0.48
    assert (r.cpp, r.new_low, r.grade, r.best_cpp) == (0.48, True, "green", 0.50)


def test_equal_to_best_is_not_new_low():
    assert rating.rate(_promo(percent=100), IHG).new_low is False


def test_suspiciously_low_price_raises():
    # 比歷史最佳便宜三成以上，幾乎必是抽錯（把點數量當百分比之類）。
    # 放行的話會被標 🏆 並把基準永久改壞，之後真正的好價全變 🔴。
    with pytest.raises(rating.SuspiciousPrice):
        rating.rate(_promo(percent=250), IHG)      # 0.29 < 0.35


BASELINES_TEXT = (
    '{\n'
    '  "IHG":        {"base_cpp": 1.00, "best_cpp": 0.50},\n'
    '  "CHOICE":     {"base_cpp": 1.03, "best_cpp": 0.57}\n'
    '}\n'
)


def test_update_best_changes_only_one_number():
    out = rating.update_best(BASELINES_TEXT, "IHG", 0.48)
    assert out == BASELINES_TEXT.replace('"best_cpp": 0.50', '"best_cpp": 0.48')


def test_update_best_targets_the_right_program():
    out = rating.update_best(BASELINES_TEXT, "CHOICE", 0.5)
    assert '"IHG":        {"base_cpp": 1.00, "best_cpp": 0.50}' in out
    assert '"CHOICE":     {"base_cpp": 1.03, "best_cpp": 0.50}' in out


def test_update_best_unknown_program_raises():
    with pytest.raises(KeyError):
        rating.update_best(BASELINES_TEXT, "NOPE", 0.4)


def test_load_baselines(tmp_path):
    p = tmp_path / "baselines.json"
    p.write_text(BASELINES_TEXT, encoding="utf-8")
    assert rating.load_baselines(p)["CHOICE"] == {"base_cpp": 1.03, "best_cpp": 0.57}
```

- [ ] **Step 2: 確認測試失敗**

Run: `python3 -m pytest tests/test_points_rating.py -v`
Expected: FAIL，`ImportError: cannot import name 'rating'`

- [ ] **Step 3: 實作**

`points_watch/rating.py`：

```python
"""Promo ＋ 基準 → 每點成本與評等。純函式，另含基準檔的讀取與改寫。"""
import json
import re
from pathlib import Path

from .models import Promo, Rated

GREEN_RATIO = 1.03      # 平或破歷史最佳（3% 內）
YELLOW_RATIO = 1.15     # 比歷史最佳貴 15% 以內
DIVERGE = 0.10          # 公式值與文章報價差距超過這個比例就採文章報價
SUSPICIOUS_RATIO = 0.70  # 低於歷史最佳的七成＝幾乎必是抽錯
_EPS = 1e-9             # 浮點誤差容忍，讓「剛好在門檻上」穩定落在門檻內


class SuspiciousPrice(ValueError):
    """算出的價格低得不合理。拋出去由 main 記成失敗並告警，不推播、不改基準。"""


def _formula(kind: str, percent: int, base_cpp: float) -> float:
    if kind == "discount":
        return base_cpp * (1 - percent / 100)
    return base_cpp / (1 + percent / 100)


def rate(promo: Promo, baseline: dict) -> Rated:
    best = baseline["best_cpp"]
    cpp = round(_formula(promo.kind, promo.percent, baseline["base_cpp"]), 2)
    from_article = False
    stated = promo.stated_cpp
    if stated is not None and abs(cpp - stated) / stated > DIVERGE:
        cpp, from_article = round(stated, 2), True

    if cpp < best * SUSPICIOUS_RATIO:
        raise SuspiciousPrice("每點成本低於歷史最佳的七成，疑似抽取錯誤")

    if cpp <= best * GREEN_RATIO + _EPS:
        grade = "green"
    elif cpp <= best * YELLOW_RATIO + _EPS:
        grade = "yellow"
    else:
        grade = "red"
    return Rated(promo=promo, cpp=cpp, best_cpp=best, grade=grade,
                 new_low=cpp < best - _EPS, from_article=from_article)


def load_baselines(path: Path) -> dict[str, dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def update_best(text: str, program: str, new_best: float) -> str:
    """把某計畫的 best_cpp 換成新值，其餘一個字元都不動。

    刻意不用 json.load＋json.dump：整檔重寫會重排版面，把一個數字的變更
    放大成整檔 diff（CLAUDE.md 開發流程第二條）。baselines.json 一個計畫
    一行，這裡靠該版面做單行內取代。
    """
    pattern = re.compile(
        r'("' + re.escape(program) + r'":\s*\{[^}\n]*"best_cpp":\s*)[0-9.]+'
    )
    out, n = pattern.subn(lambda m: f"{m.group(1)}{new_best:.2f}", text, count=1)
    if n != 1:
        raise KeyError(program)
    return out
```

- [ ] **Step 4: 確認測試通過**

Run: `python3 -m pytest tests/test_points_rating.py -v`
Expected: 17 passed

- [ ] **Step 5: 對真實基準檔跑一次改寫，確認 diff 只有一行**

```bash
python3 -c "
from pathlib import Path
from points_watch import rating
p = Path('points_watch/baselines.json')
p.write_text(rating.update_best(p.read_text(encoding='utf-8'), 'IHG', 0.49), encoding='utf-8')
"
git diff --stat points_watch/baselines.json
git checkout points_watch/baselines.json
```

Expected: `1 file changed, 1 insertion(+), 1 deletion(-)`，之後檔案還原。

- [ ] **Step 6: Commit**

```bash
git add points_watch/rating.py tests/test_points_rating.py
git commit -m "feat(points-watch): 每點成本計算、評等與基準檔改寫"
```

---

### Task 7: Haiku 抽取

**Files:**
- Create: `points_watch/extract.py`
- Test: `tests/test_points_extract.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/test_points_extract.py`：

```python
"""Haiku 抽取測試。只測 prompt 組裝與回應解析，不打 API。"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import extract  # noqa: E402
from points_watch.models import Article  # noqa: E402

TODAY = date(2026, 10, 9)
ARTICLE = Article(
    feed="frequentmiler",
    title="Buy IHG Points for as low as 0.5 cents each",
    url="https://frequentmiler.com/buy-ihg-points/",
    published=date(2026, 10, 8),
    summary="IHG has returned with another sale, offering a 100% bonus when buying points.",
)
GOOD = {"is_promo": True, "program": "IHG", "kind": "bonus", "percent": 100,
        "stated_cpp": 0.5, "end_date": "2026-10-31", "up_to": True}


def _parse(payload) -> object:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return extract.parse_response(raw, ARTICLE, TODAY)


def test_prompt_contains_article_and_dates():
    prompt = extract.build_prompt(ARTICLE, TODAY)
    assert ARTICLE.title in prompt and ARTICLE.summary in prompt
    assert "2026-10-09" in prompt and "2026-10-08" in prompt
    assert "FLYINGBLUE" in prompt          # 九個代號都要列給模型


def test_good_response():
    promo = _parse(GOOD)
    assert (promo.program, promo.kind, promo.percent, promo.stated_cpp, promo.up_to) == \
        ("IHG", "bonus", 100, 0.5, True)
    assert promo.end_date == date(2026, 10, 31)
    assert promo.url == ARTICLE.url


def test_json_wrapped_in_prose_or_fence():
    promo = _parse("好的，結果如下：\n```json\n" + json.dumps(GOOD) + "\n```")
    assert promo.program == "IHG"


def test_not_a_promo_returns_none():
    assert _parse({"is_promo": False}) is None


def test_nulls_allowed_for_cpp_and_end_date():
    promo = _parse({**GOOD, "stated_cpp": None, "end_date": None})
    assert promo.stated_cpp is None and promo.end_date is None


def test_end_date_today_is_ok():
    # last call 文章在截止當天發出，仍是有效促銷
    assert _parse({**GOOD, "end_date": "2026-10-09"}).end_date == TODAY


@pytest.mark.parametrize("bad", [
    "抱歉，我無法判斷。",                       # 沒有 JSON
    "{not json}",
    {"program": "IHG"},                          # 缺 is_promo
    {**GOOD, "program": "HILTON"},               # 不在追蹤清單
    {**GOOD, "kind": "cashback"},
    {**GOOD, "percent": 0},
    {**GOOD, "percent": 301},
    {**GOOD, "percent": "100%"},
    {**GOOD, "stated_cpp": 0.05},
    {**GOOD, "stated_cpp": 12},
    {**GOOD, "end_date": "October 31"},
    {**GOOD, "end_date": "2026-10-08"},          # 早於今天
    {**GOOD, "up_to": "yes"},
])
def test_bad_response_raises(bad):
    # 一律拋例外而非回 None：None 的語意是「模型判定不是促銷」，
    # 兩者混在一起的話，模型回垃圾會被當成「沒事」而永久漏報。
    with pytest.raises(extract.ExtractError):
        _parse(bad)
```

- [ ] **Step 2: 確認測試失敗**

Run: `python3 -m pytest tests/test_points_extract.py -v`
Expected: FAIL，`ImportError: cannot import name 'extract'`

- [ ] **Step 3: 實作**

`points_watch/extract.py`：

```python
"""Haiku 把一篇文章的標題與摘要抽成結構化促銷。

回傳 None＝模型判定「不是買點促銷」（正常結果，文章記為已看過）。
拋 ExtractError＝回應壞掉或數值不合理（異常，文章不記為已看過、隔天重試、送告警）。
這兩者絕不可合併。
"""
import json
import os
import re
from datetime import date

from anthropic import Anthropic

from society_watch.llm import MODEL

from .models import Article, Promo
from .sources import PROGRAMS

PROMPT_TEMPLATE = """你是飯店與航空點數促銷的資料抽取器。以下是一篇部落格文章的標題與摘要。

判斷它是否在報導「單一計畫的官方買點／買哩程促銷（加贈或折扣）」。只追蹤這些計畫：
{programs}

以下一律不算（回 is_promo=false）：獎勵票特價、信用卡開卡禮或審查文、轉點加贈、
一次列出多則優惠的彙整文、不在上列清單的計畫、已經結束的促銷。

今天是 {today}，文章發布於 {published}。
標題：{title}
摘要：{summary}

只輸出一個 JSON 物件，不要任何其他文字。
不是 → {{"is_promo": false}}
是 → {{"is_promo": true, "program": "<上列代號>", "kind": "bonus" 或 "discount",
"percent": <整數>, "stated_cpp": <數字或 null>, "end_date": "YYYY-MM-DD" 或 null, "up_to": true 或 false}}

欄位規則：
- kind：買點加贈（例 100% bonus）填 bonus；價格折扣（例 40% off）填 discount。
- percent：分級促銷取最高級距的數字。
- stated_cpp：文中寫明的每點／每哩成本，單位美分（"0.5 cents each" → 0.5）。沒寫就 null，不要自己算。
- end_date：促銷截止日。文中只寫月日時，以今天與發布日推斷年份。沒寫就 null。
- up_to：出現 "up to"、分級、targeted、「視帳號而定」任一情況填 true。"""


class ExtractError(RuntimeError):
    """模型回應無法解析，或抽出的數值不合理。"""


def build_prompt(article: Article, today: date) -> str:
    programs = "\n".join(f"- {code}＝{p['label']}" for code, p in PROGRAMS.items())
    return PROMPT_TEMPLATE.format(
        programs=programs,
        today=today.isoformat(),
        published=article.published.isoformat() if article.published else "不明",
        title=article.title,
        summary=article.summary,
    )


def _number(value, low: float, high: float, what: str) -> float:
    # bool 是 int 的子類別，要先排除，否則 true 會被當成 1
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExtractError(f"{what} 不是數字")
    if not low <= value <= high:
        raise ExtractError(f"{what} 超出合理範圍")
    return value


def parse_response(raw: str, article: Article, today: date) -> Promo | None:
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ExtractError("Haiku 回應不含 JSON")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ExtractError("Haiku 回應無法解析為 JSON") from e
    if not isinstance(data, dict) or not isinstance(data.get("is_promo"), bool):
        raise ExtractError("Haiku 回應缺少 is_promo")
    if not data["is_promo"]:
        return None

    if data.get("program") not in PROGRAMS:
        raise ExtractError("program 不在追蹤清單")
    if data.get("kind") not in ("bonus", "discount"):
        raise ExtractError("kind 不是 bonus 或 discount")
    percent = _number(data.get("percent"), 1, 300, "percent")
    if percent != int(percent):
        raise ExtractError("percent 不是整數")

    stated = data.get("stated_cpp")
    if stated is not None:
        stated = float(_number(stated, 0.1, 10, "stated_cpp"))

    end = data.get("end_date")
    if end is not None:
        try:
            end = date.fromisoformat(end)
        except (TypeError, ValueError) as e:
            raise ExtractError("end_date 格式錯誤") from e
        if end < today:
            raise ExtractError("end_date 早於今天")

    if not isinstance(data.get("up_to"), bool):
        raise ExtractError("up_to 不是布林值")

    return Promo(program=data["program"], kind=data["kind"], percent=int(percent),
                 stated_cpp=stated, end_date=end, up_to=data["up_to"], url=article.url)


def extract(article: Article, today: date) -> Promo | None:
    client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": build_prompt(article, today)}],
    )
    # 取第一個 text block，不假設 content[0] 就是文字
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
    return parse_response(text, article, today)
```

注意：`ExtractError` 的訊息是告警節流的鍵（`should_alert` 比對 reason），所以訊息裡不可放會變動的數字。

- [ ] **Step 4: 確認測試通過**

Run: `python3 -m pytest tests/test_points_extract.py -v`
Expected: 19 passed

- [ ] **Step 5: Commit**

```bash
git add points_watch/extract.py tests/test_points_extract.py
git commit -m "feat(points-watch): Haiku 促銷抽取與回應檢查"
```

---

### Task 8: 促銷狀態與截止提醒

**Files:**
- Create: `points_watch/store.py`
- Test: `tests/test_points_store.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/test_points_store.py`：

```python
"""promos.json 讀寫與截止提醒判定。"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import store  # noqa: E402
from points_watch.models import Promo, Rated  # noqa: E402

TODAY = date(2026, 10, 9)


def _rated(grade="green", end=date(2026, 10, 31), program="IHG"):
    promo = Promo(program=program, kind="bonus", percent=100, stated_cpp=0.5,
                  end_date=end, up_to=True, url="https://x.test/a")
    return Rated(promo=promo, cpp=0.5, best_cpp=0.5, grade=grade,
                 new_low=False, from_article=False)


def test_entry_roundtrip(tmp_path):
    path = tmp_path / "promos.json"
    r = _rated()
    store.save_promos(path, {r.promo.key: store.entry(r, TODAY)})
    assert store.load_promos(path) == {
        "IHG|bonus|100|2026-10-31": {
            "program": "IHG", "kind": "bonus", "percent": 100, "cpp": 0.5,
            "grade": "green", "end_date": "2026-10-31", "url": "https://x.test/a",
            "first_seen": "2026-10-09", "reminded": False,
        }
    }
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_load_missing_file(tmp_path):
    assert store.load_promos(tmp_path / "nope.json") == {}


def test_entry_without_end_date():
    assert store.entry(_rated(end=None), TODAY)["end_date"] is None


@pytest.mark.parametrize("end, due", [
    (date(2026, 10, 12), False),   # 剩 3 天
    (date(2026, 10, 11), True),    # 剩 2 天
    (date(2026, 10, 10), True),
    (date(2026, 10, 9), True),     # 今天截止
    (date(2026, 10, 8), False),    # 已過期
])
def test_due_by_days_left(end, due):
    r = _rated(end=end)
    promos = {r.promo.key: store.entry(r, date(2026, 10, 1))}
    assert bool(store.due_reminders(promos, TODAY)) is due


def test_only_green_gets_reminder():
    r = _rated(grade="yellow", end=date(2026, 10, 10))
    assert store.due_reminders({r.promo.key: store.entry(r, TODAY)}, TODAY) == []


def test_reminded_once_only():
    r = _rated(end=date(2026, 10, 10))
    e = store.entry(r, TODAY)
    e["reminded"] = True
    assert store.due_reminders({r.promo.key: e}, TODAY) == []


def test_no_end_date_no_reminder():
    r = _rated(end=None)
    assert store.due_reminders({r.promo.key: store.entry(r, TODAY)}, TODAY) == []


def test_corrupt_entry_is_skipped_not_fatal():
    # 這個檔 commit 進 public repo、可能被手改。壞一筆不該讓整個 run 死掉。
    promos = {"bad": {"grade": "green", "end_date": "not-a-date"}, "worse": "string"}
    assert store.due_reminders(promos, TODAY) == []
```

- [ ] **Step 2: 確認測試失敗**

Run: `python3 -m pytest tests/test_points_store.py -v`
Expected: FAIL，`ImportError: cannot import name 'store'`

- [ ] **Step 3: 實作**

`points_watch/store.py`：

```python
"""已處理過的促銷（promos.json）與截止提醒判定。

「看過的文章」（seen_articles.json）直接用 society_watch.state 的
load_seen／save_seen，這裡不重寫。
"""
import json
from datetime import date
from pathlib import Path

from society_watch.state import _atomic_write

from .models import Rated

REMIND_DAYS = 2   # 🟢 促銷剩幾天（含）以內提醒


def load_promos(path: Path) -> dict[str, dict]:
    if not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def save_promos(path: Path, promos: dict[str, dict]) -> None:
    _atomic_write(
        path, json.dumps(promos, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def entry(rated: Rated, today: date) -> dict:
    p = rated.promo
    return {
        "program": p.program, "kind": p.kind, "percent": p.percent,
        "cpp": rated.cpp, "grade": rated.grade,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "url": p.url, "first_seen": today.isoformat(), "reminded": False,
    }


def due_reminders(promos: dict[str, dict], today: date) -> list[str]:
    """回傳該送截止提醒的促銷鍵（已排序）。壞掉的紀錄跳過不拋例外。"""
    due = []
    for key, e in promos.items():
        if not isinstance(e, dict) or e.get("grade") != "green" or e.get("reminded"):
            continue
        try:
            end = date.fromisoformat(e.get("end_date") or "")
        except (TypeError, ValueError):
            continue
        if 0 <= (end - today).days <= REMIND_DAYS:
            due.append(key)
    return sorted(due)
```

- [ ] **Step 4: 確認測試通過**

Run: `python3 -m pytest tests/test_points_store.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add points_watch/store.py tests/test_points_store.py
git commit -m "feat(points-watch): 促銷狀態檔與截止提醒判定"
```

---

### Task 9: 訊息排版

**Files:**
- Create: `points_watch/notify.py`
- Test: `tests/test_points_notify.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/test_points_notify.py`：

```python
"""四種訊息的排版。"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import notify  # noqa: E402
from points_watch.models import Promo, Rated  # noqa: E402


def _rated(program="IHG", kind="bonus", percent=100, cpp=0.5, best=0.5, grade="green",
           new_low=False, from_article=False, up_to=False, end=date(2026, 10, 31)):
    promo = Promo(program=program, kind=kind, percent=percent, stated_cpp=None,
                  end_date=end, up_to=up_to, url="https://x.test/a")
    return Rated(promo=promo, cpp=cpp, best_cpp=best, grade=grade,
                 new_low=new_low, from_article=from_article)


def test_green_at_best_with_up_to():
    assert notify.format_promos([_rated(up_to=True)]) == "\n".join([
        "💰 點數促銷",
        "",
        "🟢 IHG 買點 100% 加贈",
        "每點 0.50¢（平歷史最佳）",
        "⚠️ 最高可達，需登入確認個人優惠",
        "截止 10/31",
        "https://x.test/a",
    ])


def test_yellow_miles_shows_gap():
    text = notify.format_promos([_rated(
        program="ALASKA", percent=70, cpp=2.21, best=1.88, grade="yellow",
        end=date(2026, 10, 20))])
    assert "🟡 Alaska 買哩程 70% 加贈" in text
    assert "每哩 2.21¢（歷史最佳 1.88¢，貴 18%）" in text
    assert "截止 10/20" in text
    assert "最高可達" not in text


def test_discount_wording():
    text = notify.format_promos([_rated(program="CHOICE", kind="discount", percent=45,
                                        cpp=0.57, best=0.57)])
    assert "🟢 Choice 買點 45% 折扣" in text


def test_new_low():
    text = notify.format_promos([_rated(cpp=0.48, best=0.50, new_low=True)])
    assert "每點 0.48¢（🏆 新低，原最佳 0.50¢）" in text


def test_from_article_note_and_missing_end_date():
    text = notify.format_promos([_rated(from_article=True, end=None)])
    assert "（依文章報價）" in text
    assert "截止日未註明" in text


def test_green_sorted_before_yellow_and_blank_line_between():
    text = notify.format_promos([
        _rated(program="ALASKA", cpp=2.0, best=1.88, grade="yellow"),
        _rated(program="IHG"),
    ])
    assert text.index("🟢 IHG") < text.index("🟡 Alaska")
    assert "https://x.test/a\n\n🟡 Alaska" in text


def test_reminder():
    entries = [{"program": "IHG", "kind": "bonus", "percent": 100, "cpp": 0.5,
                "end_date": "2026-10-11", "url": "https://x.test/a"}]
    assert notify.format_reminder(entries, date(2026, 10, 9)) == "\n".join([
        "⏰ 促銷即將截止",
        "",
        "🟢 IHG 買點 100% 加贈",
        "每點 0.50¢｜10/11 截止（剩 2 天）",
        "https://x.test/a",
    ])


def test_reminder_last_day():
    entries = [{"program": "ALASKA", "kind": "bonus", "percent": 100, "cpp": 1.88,
                "end_date": "2026-10-09", "url": "https://x.test/a"}]
    assert "每哩 1.88¢｜10/9 截止（今天截止）" in notify.format_reminder(entries, date(2026, 10, 9))


def test_alert():
    text = notify.format_alert([("omaat", "RSS 無法解析，可能被擋或改版")])
    assert text.startswith("⚠️ 點數促銷監測異常")
    assert "・omaat：RSS 無法解析，可能被擋或改版" in text


def test_heartbeat():
    text = notify.format_heartbeat(feed_count=3, article_count=42, promo_count=7)
    assert text.startswith("💓 點數促銷監測運作正常")
    assert "3" in text and "42" in text and "7" in text
```

- [ ] **Step 2: 確認測試失敗**

Run: `python3 -m pytest tests/test_points_notify.py -v`
Expected: FAIL，`ImportError: cannot import name 'notify'`

- [ ] **Step 3: 實作**

`points_watch/notify.py`：

```python
"""四種 LINE 訊息的排版。純函式；實際推送用 society_watch.notify.push_line。"""
from datetime import date

from .models import Rated
from .sources import PROGRAMS

_ICON = {"green": "🟢", "yellow": "🟡"}
_ORDER = {"green": 0, "yellow": 1}


def _headline(program: str, kind: str, percent: int) -> str:
    info = PROGRAMS[program]
    verb = "買點" if info["unit"] == "點" else "買哩程"
    return f"{info['label']} {verb} {percent}% {'加贈' if kind == 'bonus' else '折扣'}"


def _md(d: date) -> str:
    return f"{d.month}/{d.day}"


def _format_one(r: Rated) -> str:
    p = r.promo
    unit = PROGRAMS[p.program]["unit"]
    if r.new_low:
        compare = f"🏆 新低，原最佳 {r.best_cpp:.2f}¢"
    elif r.cpp <= r.best_cpp:
        compare = "平歷史最佳"
    else:
        gap = round((r.cpp / r.best_cpp - 1) * 100)
        compare = f"歷史最佳 {r.best_cpp:.2f}¢，貴 {gap}%"

    lines = [
        f"{_ICON[r.grade]} {_headline(p.program, p.kind, p.percent)}",
        f"每{unit} {r.cpp:.2f}¢（{compare}）",
    ]
    if r.from_article:
        lines.append("（依文章報價）")
    if p.up_to:
        lines.append("⚠️ 最高可達，需登入確認個人優惠")
    lines.append(f"截止 {_md(p.end_date)}" if p.end_date else "截止日未註明")
    lines.append(p.url)
    return "\n".join(lines)


def format_promos(rated: list[Rated]) -> str:
    """只接受 green／yellow；red 由呼叫端先濾掉。"""
    ordered = sorted(rated, key=lambda r: _ORDER[r.grade])   # sorted 是穩定排序
    return "💰 點數促銷\n\n" + "\n\n".join(_format_one(r) for r in ordered)


def format_reminder(entries: list[dict], today: date) -> str:
    blocks = []
    for e in entries:
        end = date.fromisoformat(e["end_date"])
        left = (end - today).days
        unit = PROGRAMS[e["program"]]["unit"]
        when = "今天截止" if left == 0 else f"剩 {left} 天"
        blocks.append("\n".join([
            f"🟢 {_headline(e['program'], e['kind'], e['percent'])}",
            f"每{unit} {e['cpp']:.2f}¢｜{_md(end)} 截止（{when}）",
            e["url"],
        ]))
    return "⏰ 促銷即將截止\n\n" + "\n\n".join(blocks)


def format_alert(failures: list[tuple[str, str]]) -> str:
    lines = ["⚠️ 點數促銷監測異常", ""]
    lines.extend(f"・{source}：{reason}" for source, reason in failures)
    return "\n".join(lines)


def format_heartbeat(feed_count: int, article_count: int, promo_count: int) -> str:
    return "\n".join([
        "💓 點數促銷監測運作正常",
        "",
        f"・監測來源：{feed_count} 個 RSS",
        f"・已判讀文章：{article_count} 篇",
        f"・已記錄促銷：{promo_count} 筆",
        "",
        "（每週一則。若某一週沒收到，表示監測可能已停擺，請查看 GitHub Actions。）",
    ])
```

- [ ] **Step 4: 確認測試通過**

Run: `python3 -m pytest tests/test_points_notify.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add points_watch/notify.py tests/test_points_notify.py
git commit -m "feat(points-watch): 促銷／提醒／告警／心跳訊息排版"
```

---

### Task 10: 主流程

**Files:**
- Create: `points_watch/main.py`
- Test: `tests/test_points_main.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/test_points_main.py`：

```python
"""主流程測試。網路、Haiku、LINE 全部以假函式取代，狀態檔寫到 tmp_path。"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import extract, main  # noqa: E402
from points_watch.models import Promo  # noqa: E402

TODAY = date(2026, 10, 9)
BASELINES = (
    '{\n'
    '  "IHG":        {"base_cpp": 1.00, "best_cpp": 0.50},\n'
    '  "ALASKA":     {"base_cpp": 3.76, "best_cpp": 1.88}\n'
    '}\n'
)


def _rss(*items: tuple[str, str]) -> str:
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link>"
        "<pubDate>Thu, 08 Oct 2026 06:00:00 +0000</pubDate>"
        "<description>d</description></item>"
        for t, u in items
    )
    return f"<rss><channel>{body}</channel></rss>"


IHG_ITEM = ("Buy IHG Points for as low as 0.5 cents each", "https://fm.test/ihg")
NOISE = ("Some airline news", "https://fm.test/news")


def _promo(program="IHG", percent=100, end=date(2026, 10, 31), url="https://fm.test/ihg"):
    return Promo(program=program, kind="bonus", percent=percent, stated_cpp=None,
                 end_date=end, up_to=False, url=url)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """預設：三個 feed 都回同一份含一篇 IHG 文章的 RSS，Haiku 回 IHG 100%。"""
    (tmp_path / "baselines.json").write_text(BASELINES, encoding="utf-8")
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)

    box = {"pushed": [], "feeds": {}, "extract": lambda a, t: _promo(), "calls": []}

    def fake_get(url, **kw):
        result = box["feeds"].get(url.split("?")[0], _rss(IHG_ITEM, NOISE))
        if isinstance(result, Exception):
            raise result
        return result

    def fake_extract(article, today):
        box["calls"].append(article.title)
        return box["extract"](article, today)

    monkeypatch.setattr(main.fetch, "get", fake_get)
    monkeypatch.setattr(main.extract, "extract", fake_extract)
    monkeypatch.setattr(main, "push_line", box["pushed"].append)
    box["dir"] = tmp_path
    return box


def _json(env, name):
    return json.loads((env["dir"] / name).read_text(encoding="utf-8"))


def test_pushes_green_once_and_records_state(env):
    failures = main.run(today=TODAY)
    assert failures == []
    promo_msgs = [m for m in env["pushed"] if m.startswith("💰")]
    assert len(promo_msgs) == 1 and "🟢 IHG 買點 100% 加贈" in promo_msgs[0]
    assert env["calls"] == [IHG_ITEM[0]]            # 同文出現在三個 feed 只判讀一次；雜訊不送
    assert "IHG|bonus|100|2026-10-31" in _json(env, "promos.json")
    assert _json(env, "seen_articles.json")["seen"] == ["https://fm.test/ihg|2026-10-08"]


def test_second_run_is_silent(env):
    main.run(today=TODAY)
    env["pushed"].clear(), env["calls"].clear()
    main.run(today=TODAY)
    assert env["pushed"] == [] and env["calls"] == []


def test_same_promo_from_another_article_not_pushed_twice(env):
    main.run(today=TODAY)
    env["pushed"].clear()
    env["feeds"]["https://loyaltylobby.com/feed/"] = _rss(
        ("IHG Buy Points 100% Bonus Sale Through October 31", "https://ll.test/ihg"))
    main.run(today=TODAY)
    assert not [m for m in env["pushed"] if m.startswith("💰")]


def test_red_is_recorded_but_not_pushed(env):
    env["extract"] = lambda a, t: _promo(percent=50)      # 0.67，red
    main.run(today=TODAY)
    assert not [m for m in env["pushed"] if m.startswith("💰")]
    assert _json(env, "promos.json")["IHG|bonus|50|2026-10-31"]["grade"] == "red"


def test_not_a_promo_is_marked_seen(env):
    env["extract"] = lambda a, t: None
    main.run(today=TODAY)
    assert _json(env, "seen_articles.json")["seen"]
    assert not (env["dir"] / "promos.json").exists() or _json(env, "promos.json") == {}


def test_extract_failure_alerts_and_retries_next_day(env):
    def boom(a, t):
        raise extract.ExtractError("Haiku 回應不含 JSON")
    env["extract"] = boom
    failures = main.run(today=TODAY)
    # 三個 feed 回同一篇，collect 保留最先出現的那份，所以來源是 loyaltylobby
    assert failures == [("loyaltylobby／抽取", "Haiku 回應不含 JSON")]
    assert any(m.startswith("⚠️ 點數促銷監測異常") for m in env["pushed"])
    seen = (env["dir"] / "seen_articles.json")
    assert not seen.exists() or _json(env, "seen_articles.json")["seen"] == []


def test_suspicious_price_alerts_and_leaves_baseline_alone(env):
    env["extract"] = lambda a, t: _promo(percent=250)
    failures = main.run(today=TODAY)
    assert failures and "疑似抽取錯誤" in failures[0][1]
    assert (env["dir"] / "baselines.json").read_text(encoding="utf-8") == BASELINES
    assert not [m for m in env["pushed"] if m.startswith("💰")]


def test_new_low_updates_baseline_minimally(env):
    env["extract"] = lambda a, t: _promo(percent=110)     # 0.48
    main.run(today=TODAY)
    assert any("🏆 新低" in m for m in env["pushed"])
    assert (env["dir"] / "baselines.json").read_text(encoding="utf-8") == \
        BASELINES.replace('"best_cpp": 0.50', '"best_cpp": 0.48')


def test_one_feed_down_others_continue(env):
    env["feeds"]["https://onemileatatime.com/feed/"] = requests.ConnectionError("x")
    failures = main.run(today=TODAY)
    assert [s for s, _ in failures] == ["omaat"]
    assert any(m.startswith("💰") for m in env["pushed"])
    assert any(m.startswith("⚠️") for m in env["pushed"])


def test_empty_feed_is_a_failure(env):
    env["feeds"]["https://frequentmiler.com/feed/"] = _rss()
    failures = main.run(today=TODAY)
    assert ("frequentmiler", "RSS 回傳 0 篇，疑似改版") in failures


def test_alert_throttled_within_seven_days(env):
    env["feeds"]["https://onemileatatime.com/feed/"] = requests.ConnectionError("x")
    main.run(today=TODAY)
    env["pushed"].clear()
    main.run(today=date(2026, 10, 10))
    assert not [m for m in env["pushed"] if m.startswith("⚠️")]


def test_push_failure_leaves_state_untouched(env, monkeypatch):
    def fail(text):
        raise requests.HTTPError("500")
    monkeypatch.setattr(main, "push_line", fail)
    with pytest.raises(requests.HTTPError):
        main.run(today=TODAY)
    assert not (env["dir"] / "seen_articles.json").exists()
    assert not (env["dir"] / "promos.json").exists()


def test_bootstrap_marks_seen_without_extract_or_push(env):
    main.run(bootstrap=True, today=TODAY)
    assert env["pushed"] == [] and env["calls"] == []
    assert _json(env, "seen_articles.json")["seen"] == ["https://fm.test/ihg|2026-10-08"]
    main.run(today=TODAY)
    assert not [m for m in env["pushed"] if m.startswith("💰")]


def test_dry_run_prints_but_writes_nothing(env, capsys):
    main.run(dry_run=True, today=TODAY)
    assert env["pushed"] == []
    assert "🟢 IHG 買點 100% 加贈" in capsys.readouterr().out
    assert sorted(p.name for p in env["dir"].iterdir()) == ["baselines.json"]


def test_reminder_sent_once_when_two_days_left(env):
    env["extract"] = lambda a, t: _promo(end=date(2026, 10, 20))
    main.run(today=TODAY)
    env["pushed"].clear()
    main.run(today=date(2026, 10, 17))
    assert not [m for m in env["pushed"] if m.startswith("⏰")]
    main.run(today=date(2026, 10, 18))
    assert len([m for m in env["pushed"] if m.startswith("⏰")]) == 1
    env["pushed"].clear()
    main.run(today=date(2026, 10, 19))
    assert not [m for m in env["pushed"] if m.startswith("⏰")]


def test_heartbeat_once_per_week(env):
    main.run(today=TODAY)
    assert len([m for m in env["pushed"] if m.startswith("💓")]) == 1
    env["pushed"].clear()
    main.run(today=date(2026, 10, 10))
    assert not [m for m in env["pushed"] if m.startswith("💓")]


def test_pages_argument_fetches_more_urls(env, monkeypatch):
    urls = []
    monkeypatch.setattr(main.fetch, "get", lambda u, **kw: urls.append(u) or _rss(NOISE))
    main.run(pages=3, today=TODAY)
    assert len(urls) == 9 and "https://frequentmiler.com/feed/?paged=3" in urls
```

- [ ] **Step 2: 確認測試失敗**

Run: `python3 -m pytest tests/test_points_main.py -v`
Expected: FAIL，`ImportError: cannot import name 'main'`

- [ ] **Step 3: 實作**

`points_watch/main.py`：

```python
"""點數促銷監測主流程。

用法：
    python3 -m points_watch.main --bootstrap   # 首次：只把現有文章記為已看過，不判讀不推播
    python3 -m points_watch.main --dry-run     # 驗收：照常判讀，訊息印到 stdout，不推播不寫檔
    python3 -m points_watch.main               # 日常執行
"""
import argparse
import traceback
from datetime import date
from pathlib import Path

import requests

from society_watch import fetch
from society_watch import state as sw_state
from society_watch.notify import push_line, split_message

from . import extract, feeds, notify, rating, store
from .models import Article, Rated
from .sources import DEFAULT_PAGES, FEEDS, feed_urls, is_candidate

DATA_DIR = Path(__file__).resolve().parent


def _reason(error: Exception) -> str:
    """把例外轉成告警文字。這串同時是 should_alert 的節流鍵，必須短而穩定。"""
    if isinstance(error, (feeds.FeedError, extract.ExtractError, rating.SuspiciousPrice)):
        return str(error)
    if isinstance(error, requests.RequestException):
        return f"連線失敗 {type(error).__name__}"
    if (type(error).__module__ or "").startswith("anthropic"):
        return f"Anthropic API 問題（先查餘額與月上限）{type(error).__name__}"
    return f"程式錯誤（需改 code）{type(error).__name__}"


def collect(pages: int) -> tuple[list[Article], list[tuple[str, str]]]:
    """逐 feed 抓取解析。單一 feed 失敗不影響其他 feed。同一篇文章只留一份。"""
    articles: dict[str, Article] = {}
    failures: list[tuple[str, str]] = []
    for feed in FEEDS:
        name = feed["name"]
        try:
            found: list[Article] = []
            for url in feed_urls(feed, pages):
                found.extend(feeds.parse_feed(fetch.get(url), name))
        except Exception as e:
            print(f"  ❌ {name} 抓取失敗：{type(e).__name__}: {e}")
            traceback.print_exc()
            failures.append((name, _reason(e)))
            continue
        if not found:
            print(f"  ⚠️ {name} RSS 回傳 0 篇")
            failures.append((name, "RSS 回傳 0 篇，疑似改版"))
            continue
        print(f"  ✅ {name} {len(found)} 篇")
        for a in found:
            articles.setdefault(a.key, a)
    return list(articles.values()), failures


def run(bootstrap: bool = False, dry_run: bool = False,
        pages: int = DEFAULT_PAGES, today: date | None = None) -> list[tuple[str, str]]:
    today = today or date.today()
    seen_path = DATA_DIR / "seen_articles.json"
    promos_path = DATA_DIR / "promos.json"
    baselines_path = DATA_DIR / "baselines.json"
    alerts_path = DATA_DIR / "alert_state.json"
    heartbeat_path = DATA_DIR / "heartbeat.json"

    mode = "bootstrap" if bootstrap else "dry-run" if dry_run else "日常"
    print(f"執行日期：{today}｜模式：{mode}｜每 feed {pages} 頁")

    articles, failures = collect(pages)
    candidates = [a for a in articles if is_candidate(a.title)]
    seen = sw_state.load_seen(seen_path)
    print(f"抓到 {len(articles)} 篇，通過關鍵字 {len(candidates)} 篇")

    if bootstrap:
        sw_state.save_seen(seen_path, seen | {a.key for a in candidates})
        print("bootstrap 模式：只記錄已看過的文章，不判讀不推播。")
        return failures

    # dry-run 無視 seen，才看得到現有文章會產生什麼訊息
    fresh = candidates if dry_run else [a for a in candidates if a.key not in seen]

    baselines = rating.load_baselines(baselines_path)
    promos = store.load_promos(promos_path)
    judged: set[str] = set()       # 判讀完成（含判否）的文章鍵
    rated: dict[str, Rated] = {}   # 本輪新出現的促銷

    for article in fresh:
        print(f"  判讀：[{article.feed}] {article.title}")
        try:
            promo = extract.extract(article, today)
            if promo is None:
                print("    → 不是買點促銷")
            elif promo.key in promos or promo.key in rated:
                print(f"    → 已知促銷 {promo.key}")
            else:
                r = rating.rate(promo, baselines[promo.program])
                rated[promo.key] = r
                print(f"    → {promo.key} {r.cpp:.2f}¢ {r.grade}")
        except Exception as e:
            # 這篇不進 judged → 不記為已看過 → 明天重試
            print(f"    ❌ {type(e).__name__}: {e}")
            traceback.print_exc()
            failures.append((f"{article.feed}／抽取", _reason(e)))
            continue
        judged.add(article.key)

    to_push = [r for r in rated.values() if r.grade in ("green", "yellow")]

    if dry_run:
        print("\n===== dry-run：以下是會推播的內容 =====")
        print(notify.format_promos(to_push) if to_push else "（沒有 🟢／🟡 促銷）")
        if failures:
            print("\n" + notify.format_alert(failures))
        return failures

    # 告警先送：之後的推播若拋例外，當天的異常才不會跟著消失
    if failures:
        alerts = sw_state.load_alerts(alerts_path)
        due = [f for f in failures if sw_state.should_alert(alerts, f[0], today, f[1])]
        if due:
            push_line(notify.format_alert(due))
            for source, reason in due:
                sw_state.record_alert(alerts, source, today, reason)
            sw_state.save_alerts(alerts_path, alerts)
            print(f"已送出 {len(due)} 則告警。")

    if to_push:
        for part in split_message(notify.format_promos(to_push)):
            push_line(part)
        print(f"已推播 {len(to_push)} 筆促銷。")
    else:
        print("沒有新的 🟢／🟡 促銷，不推播。")

    # 推播成功才推進狀態。push_line 失敗會拋例外穿出去，這段到不了，
    # 下一輪整批重來——重複優於漏報。
    for key, r in rated.items():
        promos[key] = store.entry(r, today)
    if rated:
        store.save_promos(promos_path, promos)
    lows = {r.promo.program: r.cpp for r in rated.values() if r.new_low}
    if lows:
        text = baselines_path.read_text(encoding="utf-8")
        for program, cpp in lows.items():
            text = rating.update_best(text, program, cpp)
        baselines_path.write_text(text, encoding="utf-8")
    sw_state.save_seen(seen_path, seen | judged)

    due_keys = store.due_reminders(promos, today)
    if due_keys:
        push_line(notify.format_reminder([promos[k] for k in due_keys], today))
        for k in due_keys:
            promos[k]["reminded"] = True
        store.save_promos(promos_path, promos)
        print(f"已送出 {len(due_keys)} 筆截止提醒。")

    if sw_state.should_heartbeat(sw_state.load_heartbeat(heartbeat_path), today):
        push_line(notify.format_heartbeat(
            feed_count=len(FEEDS),
            article_count=len(seen | judged),
            promo_count=len(promos),
        ))
        sw_state.save_heartbeat(heartbeat_path, sw_state.heartbeat_period(today))
        print("已送出每週心跳。")

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="點數促銷監測與推播")
    parser.add_argument("--bootstrap", action="store_true",
                        help="首次執行：只把現有文章記為已看過，不判讀不推播")
    parser.add_argument("--dry-run", action="store_true",
                        help="照常判讀，訊息印到 stdout；不推播、不寫任何狀態檔")
    parser.add_argument("--pages", type=int, default=DEFAULT_PAGES,
                        help="每個 feed 抓幾頁（dry-run 想回溯多一點時調大）")
    args = parser.parse_args()
    failures = run(bootstrap=args.bootstrap, dry_run=args.dry_run, pages=args.pages)

    # 所有 feed 都掛掉時亮紅燈。告警有 7 天節流，否則第 2～7 天會是
    # 「綠燈、零訊息」，跟「今天沒有促銷」長得一模一樣。
    down = {source for source, _ in failures} & {f["name"] for f in FEEDS}
    if len(down) == len(FEEDS):
        print("❌ 所有 feed 都失敗，以非零狀態結束。")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 確認測試通過**

Run: `python3 -m pytest tests/test_points_main.py -v`
Expected: 17 passed

- [ ] **Step 5: 跑整個 points_watch 測試與既有 society_watch 測試**

Run: `python3 -m pytest tests/test_points_*.py tests/test_society_*.py -q`
Expected: 全部通過，0 failed。（確認 import `society_watch` 的函式沒有造成副作用。）

- [ ] **Step 6: Commit**

```bash
git add points_watch/main.py tests/test_points_main.py
git commit -m "feat(points-watch): 主流程（bootstrap／dry-run／日常）"
```

---

### Task 11: GitHub Actions workflow（先不開排程）

**Files:**
- Create: `.github/workflows/points-watch.yml`

排程在 Task 13 驗收後才加。這一步只開手動觸發。

- [ ] **Step 1: 建立 workflow**

`.github/workflows/points-watch.yml`：

```yaml
name: 點數促銷監測

on:
  workflow_dispatch:
    inputs:
      mode:
        description: '執行模式'
        type: choice
        default: 'normal'
        options:
          - normal
          - bootstrap
          - dry-run
      pages:
        description: '每個 feed 抓幾頁（dry-run 想回溯時調大）'
        required: false
        default: '2'

permissions:
  contents: write

jobs:
  watch:
    runs-on: ubuntu-latest
    timeout-minutes: 15

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

      - name: Run points watch
        env:
          PYTHONUNBUFFERED: "1"
          CLAUDE_API_KEY: ${{ secrets.CLAUDE_API_KEY }}
          LINE_CHANNEL_ACCESS_TOKEN: ${{ secrets.LINE_CHANNEL_ACCESS_TOKEN }}
          LINE_USER_ID: ${{ secrets.LINE_USER_ID }}
          MODE: ${{ github.event.inputs.mode }}
          PAGES: ${{ github.event.inputs.pages }}
        run: |
          case "$MODE" in
            bootstrap) python3 -m points_watch.main --bootstrap --pages "${PAGES:-2}" ;;
            dry-run)   python3 -m points_watch.main --dry-run --pages "${PAGES:-2}" ;;
            *)         python3 -m points_watch.main --pages "${PAGES:-2}" ;;
          esac

      - name: Commit state
        # always()：告警送出後 alert_state.json 已寫檔，若接著推播失敗就跳過
        # commit，7 天冷卻紀錄會遺失而隔天重複告警。
        if: always()
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          # 用 -A 而非逐檔列舉：狀態檔有些只在特定情況才產生，
          # git add 遇到不存在的 pathspec 會整條失敗且什麼都不 stage。
          git add -A points_watch/
          if git diff --cached --quiet; then
            echo "狀態無變化，不 commit。"
          else
            git commit -m "chore: update points watch state [skip ci]"
            git push || (git pull --rebase origin main && git push)
          fi
```

`beautifulsoup4` 是 `society_watch.fetch`／`extract` 被 import 時的相依，本套件自己不用。輸入值經由 `env` 傳入而非直接插進 shell 字串，避免注入。

- [ ] **Step 2: 檢查 YAML 語法**

```bash
python3 -c "import yaml, sys; yaml.safe_load(open('.github/workflows/points-watch.yml')); print('OK')"
```

Expected: `OK`（若沒有 `yaml` 模組，改用 `ruby -ryaml -e "YAML.load_file('.github/workflows/points-watch.yml'); puts 'OK'"`）

- [ ] **Step 3: Commit 並 push**

```bash
git add .github/workflows/points-watch.yml
git commit -m "ci(points-watch): 手動觸發的 workflow（排程待驗收後開啟）"
git push || (git pull --no-rebase --no-edit origin main && git push)
```

工作區有使用者未提交的檔案，撞到遠端的狀態 commit 時用 merge，不要 rebase 或 stash。

---

### Task 12: dry-run 驗收（使用者檢查點）

**Files:** 無

**這是 CLAUDE.md「先做一個單位停下來驗收」的檢查點。使用者確認訊息內容正確之前，不做 Task 13。**

- [ ] **Step 1: 在 Actions 跑 dry-run，回溯四頁**

```bash
gh workflow run points-watch.yml -f mode=dry-run -f pages=4
sleep 15
gh run watch "$(gh run list --workflow=points-watch.yml --limit 1 --json databaseId -q '.[0].databaseId')"
```

- [ ] **Step 2: 取出 log 中的判讀結果與訊息**

```bash
gh run view "$(gh run list --workflow=points-watch.yml --limit 1 --json databaseId -q '.[0].databaseId')" --log \
  | grep -E "✅|❌|⚠️|判讀：|→|=====|💰|🟢|🟡|每點|每哩|截止|https://" 
```

Expected：三個 feed 都 ✅；`判讀：` 之後的每一篇都有 `→` 結果；`===== dry-run` 區塊之後是完整的 💰 訊息或「（沒有 🟢／🟡 促銷）」。四頁回溯（OMAAT 約到 9 月底）預期至少包含 2026-10-02 的 Alaska 買哩程文章。

- [ ] **Step 3: 逐篇對照原文**

對 log 中每一篇被判為促銷的文章，開啟原文網址，核對四個值：計畫、加贈／折扣百分比、每點成本、截止日。對每一篇被判為「不是買點促銷」的文章，確認判斷正確。把對照結果整理成表格。

- [ ] **Step 4: 回報使用者並等待確認**

貼出 dry-run 產生的完整訊息文字與對照表。若有抽取錯誤，修正 `extract.PROMPT_TEMPLATE` 並重跑本任務；若關鍵字漏掉或誤放文章，修正 `sources.py` 並補測試。**使用者確認訊息格式與數字都正確後才繼續。**

---

### Task 13: 上線

**Files:**
- Modify: `.github/workflows/points-watch.yml`（`on:` 區塊）

- [ ] **Step 1: bootstrap**

```bash
gh workflow run points-watch.yml -f mode=bootstrap -f pages=2
sleep 15
gh run watch "$(gh run list --workflow=points-watch.yml --limit 1 --json databaseId -q '.[0].databaseId')"
git pull --no-rebase --no-edit origin main
cat points_watch/seen_articles.json
```

Expected：run 成功；`seen_articles.json` 存在且格式為 `{"seen": [...]}`（可能是空陣列——當下 feed 沒有候選文章時屬正常）。

- [ ] **Step 2: 手動跑一次日常模式**

```bash
gh workflow run points-watch.yml -f mode=normal
sleep 15
gh run watch "$(gh run list --workflow=points-watch.yml --limit 1 --json databaseId -q '.[0].databaseId')"
```

Expected：log 顯示「沒有新的 🟢／🟡 促銷，不推播。」與「已送出每週心跳。」

- [ ] **Step 3: 請使用者確認 LINE 收到 💓**

LINE push 回 200 不代表送達。請使用者確認手機上收到「💓 點數促銷監測運作正常」。沒收到就停下來查 `LINE_USER_ID`，不要開排程。

- [ ] **Step 4: 開啟排程**

把 `.github/workflows/points-watch.yml` 的

```yaml
on:
  workflow_dispatch:
```

改成

```yaml
on:
  schedule:
    # 每日 02:30 UTC = 10:30 台灣時間，與學會監測的 10:00 錯開
    - cron: '30 2 * * *'
  workflow_dispatch:
```

- [ ] **Step 5: Commit 並 push**

```bash
git add .github/workflows/points-watch.yml
git commit -m "ci(points-watch): 開啟每日 10:30 排程"
git push || (git pull --no-rebase --no-edit origin main && git push)
```

- [ ] **Step 6: 更新記憶與規格狀態**

在 `docs/superpowers/specs/2026-10-09-points-promo-watch-design.md` 第 4 行把狀態改為「已上線（RSS 九計畫）；CUB 待另案」。在記憶目錄新增 `project_points_watch.md` 並在 `MEMORY.md` 加一行索引，內容包含：上線日期、三個 feed、四種訊息、基準檔位置與「一計畫一行」的版面限制、OMAAT 固定網址所以 seen 鍵含發布日、CUB 尚未實作。

---

## Self-Review 紀錄

**Spec 覆蓋：** §2.1 九計畫→Task 4；§2.2 來源→Task 4、5；§3 架構與重用→Task 7、8、10 的 import；§3.1 資料結構→Task 3；§4 流程 1–9→Task 10（bootstrap 含）；§6.1 公式與門檻→Task 6；§6.2 基準→Task 1；§7 四種訊息→Task 9、10；§8 錯誤處理→Task 5（FeedError）、7（數值檢查）、10（告警、不記 seen）；§9 費用→無需實作；§10 測試→各任務；§11 上線→Task 12、13。§5 CUB 明確排除於本計畫。

**與 spec 的差異（已同步修改 spec）：** seen 鍵改為 `URL|發布日`；每 feed 抓兩頁；Frequent Miler 納入；心跳內容改為累計數；新增「低於歷史最佳七成視為抽取錯誤」防護；狀態模組命名為 `store.py`（避免與 `society_watch.state` 混淆）。
