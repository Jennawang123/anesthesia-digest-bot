# 四腿票搜尋器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 自動掃描長榮境外票（四段同 PNR）在不同城市與日期組合下的價格，記錄成可排序、可追蹤漲跌的比價表。

**Architecture:** 三層。純函式層（URL 構造、文字解析、匯率換算）完全可單元測試；掃描層用 Playwright headless 驅動 Google Flights 取價，具節流與斷點續跑；前端單檔 HTML 讀 Firebase 呈現比價表。掃描分快掃（6 秒／組，取總價）與詳掃（48 秒／組，補四段時刻），只對最便宜的前 N 組詳掃。

**Tech Stack:** Python 3（playwright、urllib）、Firebase Realtime Database REST API、單檔 HTML/JS、pytest

**Spec:** `docs/superpowers/specs/2026-08-18-four-leg-fare-scanner-design.md`

---

## File Structure

| 檔案 | 職責 |
|---|---|
| `scripts/gf_url.py` | 把四段行程編碼成 Google Flights 的 `tfs` protobuf URL。純函式，無 I/O |
| `scripts/gf_parse.py` | 把航班列表文字解析成結構化資料（時刻、直飛、轉機點、價格）。純函式，無 I/O |
| `scripts/fx_rate.py` | 取 KRW→TWD 匯率並換算。唯一的外部 HTTP 相依 |
| `scripts/fare_combos.py` | 依城市清單與日期窗產生待掃組合。純函式 |
| `scripts/fare_store.py` | 掃描結果的讀寫（本機 JSON + Firebase REST） |
| `scripts/fare_scan.py` | 掃描主程式：Playwright 取價、節流、斷點續跑、CLI |
| `four-leg-fare.html` | 前端比價表 |
| `tests/test_gf_url.py` | URL 構造測試，基準為使用者提供的真實網址 |
| `tests/test_gf_parse.py` | 解析測試，fixture 為實測抓到的真實列表文字 |
| `tests/test_fare_combos.py` | 組合產生測試 |

拆分理由：前四個是純函式，可完整單元測試且執行極快；Playwright 與網路 I/O 集中在 `fare_scan.py` 與 `fx_rate.py`，隔離不穩定的部分。

---

## Task 1: Google Flights URL 構造器

**Files:**
- Create: `scripts/gf_url.py`
- Test: `tests/test_gf_url.py`

- [ ] **Step 1: 寫失敗測試**

真實基準：使用者在瀏覽器實際操作產生的網址，四段為 `PUS→TPE 2026-12-23`、`TPE→SEA 2027-02-26`、`SEA→TPE 2027-03-07`、`TPE→ICN 2027-04-20`。

建立 `tests/test_gf_url.py`：

```python
"""Google Flights tfs URL 構造測試。

基準值 REAL_TFS 取自使用者 2026-08-18 在瀏覽器實際操作產生的網址，
不是推測值。任何改動都必須讓 build_tfs 逐字元重現它。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from gf_url import build_tfs, build_url  # noqa: E402

REAL_TFS = (
    "CBwQAhoeEgoyMDI2LTEyLTIzagcIARIDUFVTcgcIARIDVFBFGh4SCjIwMjctMDItMjZqBwgB"
    "EgNUUEVyBwgBEgNTRUEaHhIKMjAyNy0wMy0wN2oHCAESA1NFQXIHCAESA1RQRRoeEgoyMDI3"
    "LTA0LTIwagcIARIDVFBFcgcIARIDSUNOQAFIAXABggELCP___________wGYAQM"
)

GROUND_TRUTH_LEGS = [
    ("2026-12-23", "PUS", "TPE"),
    ("2027-02-26", "TPE", "SEA"),
    ("2027-03-07", "SEA", "TPE"),
    ("2027-04-20", "TPE", "ICN"),
]


def test_四段行程可逐字元重現真實tfs():
    assert build_tfs(GROUND_TRUTH_LEGS) == REAL_TFS


def test_url含正確路徑與固定參數():
    url = build_url(GROUND_TRUTH_LEGS, currency="KRW")
    assert url.startswith("https://www.google.com/travel/flights/search?tfs=")
    assert "tfu=EgIIACIA" in url
    assert "curr=KRW" in url


def test_改日期會產生不同tfs():
    other = [("2026-12-21", "PUS", "TPE")] + GROUND_TRUTH_LEGS[1:]
    assert build_tfs(other) != REAL_TFS


def test_兩段行程也能編碼():
    two = GROUND_TRUTH_LEGS[:2]
    assert isinstance(build_tfs(two), str)
    assert len(build_tfs(two)) < len(REAL_TFS)
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd "$(git rev-parse --show-toplevel)" && python3 -m pytest tests/test_gf_url.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gf_url'`

- [ ] **Step 3: 實作 URL 構造器**

建立 `scripts/gf_url.py`：

```python
#!/usr/bin/env python3
"""把四段行程編碼成 Google Flights 的 tfs 查詢網址。

tfs 是 base64url 編碼的 protobuf。結構為 2026-08-18 以使用者實際操作
產生的網址反解得出，並經逐字元比對驗證：

    [1]  varint = 28              固定值
    [2]  varint = 2               固定值（填 1 會被 Google 拒絕並退回首頁）
    [3]  message  ← repeated，一段航程一筆
         [2]  str     出發日期 "2026-12-23"
         [13] message 出發地 { [1]=1 (機場), [2]="PUS" }
         [14] message 目的地 { [1]=1, [2]="TPE" }
    [8]  varint      成人數
    [9]  varint = 1  艙等：1 = 經濟艙
    [14] varint = 1
    [16] message { [1] = 2^64-1 }
    [19] varint = 3  行程類型：3 = multi-city

注意路徑是 /travel/flights/search（不是 /travel/flights），且必須帶
tfu=EgIIACIA，否則不會進入搜尋結果頁。

Google 未公開此格式，日後改版可能失效。fare_scan.py 會在連續多次
查無結果時警告，避免格式失效被誤判成「所有組合都沒票」。
"""

import base64

TFU = "EgIIACIA"
BASE = "https://www.google.com/travel/flights/search"

LOC_AIRPORT = 1  # location type：1 = 機場（IATA code）
CABIN_ECONOMY = 1
TRIP_MULTI_CITY = 3


def _varint(n):
    out = b""
    while True:
        x = n & 0x7F
        n >>= 7
        out += bytes([x | 0x80]) if n else bytes([x])
        if not n:
            return out


def _tag(field, wire_type):
    return _varint((field << 3) | wire_type)


def _str_field(field, value):
    raw = value.encode()
    return _tag(field, 2) + _varint(len(raw)) + raw


def _msg_field(field, payload):
    return _tag(field, 2) + _varint(len(payload)) + payload


def _varint_field(field, value):
    return _tag(field, 0) + _varint(value)


def _location(iata):
    return _varint_field(1, LOC_AIRPORT) + _str_field(2, iata)


def _leg(date, origin, dest):
    return (_str_field(2, date)
            + _msg_field(13, _location(origin))
            + _msg_field(14, _location(dest)))


def build_tfs(legs, adults=1, cabin=CABIN_ECONOMY):
    """legs: [(date, origin_iata, dest_iata), ...]，回傳 base64url 字串。"""
    body = _varint_field(1, 28) + _varint_field(2, 2)
    for date, origin, dest in legs:
        body += _msg_field(3, _leg(date, origin, dest))
    body += (_varint_field(8, adults)
             + _varint_field(9, cabin)
             + _varint_field(14, 1)
             + _msg_field(16, _varint_field(1, (1 << 64) - 1))
             + _varint_field(19, TRIP_MULTI_CITY))
    return base64.urlsafe_b64encode(body).decode().rstrip("=")


def build_url(legs, currency="KRW", lang="zh-TW", adults=1):
    """產生可直接開啟的 Google Flights 查詢網址。"""
    tfs = build_tfs(legs, adults=adults)
    return f"{BASE}?tfs={tfs}&tfu={TFU}&hl={lang}&curr={currency}"
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_gf_url.py -v`
Expected: PASS，4 passed

若 live 測試出現 `SSL: CERTIFICATE_VERIFY_FAILED`，那不是 API 或網路問題，
而是 python.org 版 Python 未安裝 CA bundle。見 Task 5 附註。

- [ ] **Step 5: Commit**

```bash
git add scripts/gf_url.py tests/test_gf_url.py
git commit -m "feat(fare): Google Flights tfs URL 構造器

以使用者實際操作產生的網址為基準，逐字元驗證編碼正確。"
```

---

## Task 2: 中文時刻轉 24 小時制

**Files:**
- Create: `scripts/gf_parse.py`
- Test: `tests/test_gf_parse.py`

Google Flights 中文介面用「凌晨／清晨／上午／中午／下午／晚上」前綴，必須轉成 24 小時制才能排序與比較。對照基準為使用者截圖中長榮官網的實際時刻。

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_gf_parse.py`：

```python
"""Google Flights 航班列表解析測試。

所有 fixture 均為 2026-08-18 實測抓取的真實文字，非捏造。
時刻對照基準為使用者提供的長榮官網截圖（BR163 18:55–20:25 等）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from gf_parse import parse_clock  # noqa: E402


def test_下午轉24小時制():
    # 長榮官網截圖 BR163 為 18:55 起飛
    assert parse_clock("下午6:55") == ("18:55", 0)


def test_晚上轉24小時制():
    # 同班機抵達 20:25
    assert parse_clock("晚上8:25") == ("20:25", 0)


def test_晚上11點半夜航班():
    # TPE-SEA 截圖為 23:40
    assert parse_clock("晚上11:40") == ("23:40", 0)


def test_凌晨12點應為00點():
    # SEA-TPE 截圖為 00:10
    assert parse_clock("凌晨12:10") == ("00:10", 0)


def test_清晨不加12():
    assert parse_clock("清晨7:30") == ("07:30", 0)
    assert parse_clock("清晨5:20") == ("05:20", 0)


def test_上午不加12():
    assert parse_clock("上午11:00") == ("11:00", 0)


def test_中午12點不變():
    assert parse_clock("中午12:30") == ("12:30", 0)


def test_跨日標記回傳日數差():
    # 截圖 SEA-TPE 抵達為 05:20+1
    assert parse_clock("清晨5:20+1") == ("05:20", 1)


def test_無法解析回傳None():
    assert parse_clock("整趟行程") is None
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_gf_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gf_parse'`

- [ ] **Step 3: 實作時刻解析**

建立 `scripts/gf_parse.py`：

```python
#!/usr/bin/env python3
"""解析 Google Flights 中文介面的航班列表文字。

所有格式均以 2026-08-18 實測抓取的真實文字為準。列表項文字範例：

    下午6:55 |  –  | 晚上8:25 | 長榮航空 | 2 小時 30 分鐘 | PUS–TPE | 直達 |
    154 公斤 CO2e | 比一般排放量高出 22% | ￦1,774,600 | 整趟行程

轉機版本：

    下午2:55 |  –  | 下午1:05+1 | 長榮航空 | 15 小時 10 分鐘 | VIE–TPE |
    轉機 1 次 | 1 小時 20 分鐘 BKK | ... | ￦2,401,200 | 整趟行程

注意：幣別符號是全形 ￦（U+FFE6），不是半形 ₩（U+20A9）。
用半形寫 regex 會完全抓不到價格。
"""

import re

# 中文時段前綴 → 是否需要加 12 小時
_PERIOD_ADD_12 = {
    "凌晨": False,   # 凌晨12:10 = 00:10（特例見下方）
    "清晨": False,
    "上午": False,
    "中午": False,
    "下午": True,
    "晚上": True,
}

_CLOCK_RE = re.compile(
    r"(凌晨|清晨|上午|中午|下午|晚上)\s*(\d{1,2}):(\d{2})\s*(?:\+(\d))?"
)


def parse_clock(text):
    """把「下午6:55」轉成 ("18:55", 0)，回傳 (HH:MM, 跨日天數)。

    無法解析時回傳 None。
    """
    m = _CLOCK_RE.search(text)
    if not m:
        return None
    period, hour, minute, plus_days = m.groups()
    hour = int(hour)

    if _PERIOD_ADD_12[period]:
        if hour < 12:
            hour += 12
    elif period == "凌晨" and hour == 12:
        # 「凌晨12:10」代表 00:10
        hour = 0

    return f"{hour:02d}:{minute}", int(plus_days or 0)
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_gf_parse.py -v`
Expected: PASS，9 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/gf_parse.py tests/test_gf_parse.py
git commit -m "feat(fare): 中文時段時刻轉 24 小時制

對照長榮官網截圖實際時刻驗證，含凌晨12點=00點與跨日標記。"
```

---

## Task 3: 航班列表項解析

**Files:**
- Modify: `scripts/gf_parse.py`
- Modify: `tests/test_gf_parse.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_gf_parse.py` 檔尾追加（同時更新最上方的 import 行為 `from gf_parse import parse_clock, parse_row`）：

```python
# 以下 fixture 為 2026-08-18 實測抓取的真實列表文字
ROW_NONSTOP = ("下午6:55 |  –  | 晚上8:25 | 長榮航空 | 2 小時 30 分鐘 | "
               "PUS–TPE | 直達 | 154 公斤 CO2e | 比一般排放量高出 22% | "
               "￦1,774,600 | 整趟行程")

ROW_CONNECTING = ("下午2:55 |  –  | 下午1:05+1 | 長榮航空 | 15 小時 10 分鐘 | "
                  "VIE–TPE | 轉機 1 次 | 1 小時 20 分鐘 BKK | 591 公斤 CO2e | "
                  "比一般排放量低 10% | ￦2,401,200 | 整趟行程")


def test_解析直飛航班():
    r = parse_row(ROW_NONSTOP)
    assert r["depart"] == "18:55"
    assert r["arrive"] == "20:25"
    assert r["arrive_plus_days"] == 0
    assert r["carrier"] == "長榮航空"
    assert r["duration"] == "2 小時 30 分鐘"
    assert r["from"] == "PUS"
    assert r["to"] == "TPE"
    assert r["nonstop"] is True
    assert r["via"] is None
    assert r["price"] == 1774600


def test_解析轉機航班():
    r = parse_row(ROW_CONNECTING)
    assert r["from"] == "VIE"
    assert r["to"] == "TPE"
    assert r["nonstop"] is False
    assert r["via"] == "BKK"
    assert r["price"] == 2401200
    assert r["arrive_plus_days"] == 1


def test_價格用全形韓元符號():
    # 用半形 ₩ 寫 regex 會抓不到，這是實作時踩過的坑
    assert parse_row(ROW_NONSTOP)["price"] == 1774600


def test_非航班列無法解析回傳None():
    assert parse_row("價格為包含所有稅額及手續費的最終價格") is None
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_gf_parse.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_row'`

- [ ] **Step 3: 實作列表項解析**

在 `scripts/gf_parse.py` 檔尾追加：

```python
# 全形 ￦ (U+FFE6)。半形 ₩ (U+20A9) 抓不到 Google Flights 的價格。
_PRICE_RE = re.compile(r"[￦₩]\s?([\d,]{4,})")
_ROUTE_RE = re.compile(r"([A-Z]{3})[–\-—]([A-Z]{3})")
_DURATION_RE = re.compile(r"(\d+\s*小時(?:\s*\d+\s*分鐘)?|\d+\s*分鐘)")
# 轉機點：「1 小時 20 分鐘 BKK」的結尾機場代碼
_VIA_RE = re.compile(r"分鐘\s+([A-Z]{3})")
_CARRIER_RE = re.compile(r"(長榮航空|中華航空|大韓航空|[一-鿿]{2,6}航空)")


def parse_row(text):
    """解析一列航班文字，回傳 dict；非航班列回傳 None。

    回傳欄位：depart, arrive, arrive_plus_days, carrier, duration,
    from, to, nonstop, via, price
    """
    route = _ROUTE_RE.search(text)
    price = _PRICE_RE.search(text)
    if not route or not price:
        return None

    clocks = _CLOCK_RE.findall(text)
    if len(clocks) < 2:
        return None
    depart = parse_clock(_rebuild_clock(clocks[0]))
    arrive = parse_clock(_rebuild_clock(clocks[1]))
    if not depart or not arrive:
        return None

    nonstop = "直達" in text
    via = None
    if not nonstop:
        m = _VIA_RE.search(text)
        via = m.group(1) if m else None

    carrier = _CARRIER_RE.search(text)
    duration = _DURATION_RE.search(text)

    return {
        "depart": depart[0],
        "arrive": arrive[0],
        "arrive_plus_days": arrive[1],
        "carrier": carrier.group(1) if carrier else None,
        "duration": duration.group(1).strip() if duration else None,
        "from": route.group(1),
        "to": route.group(2),
        "nonstop": nonstop,
        "via": via,
        "price": int(price.group(1).replace(",", "")),
    }


def _rebuild_clock(groups):
    """把 _CLOCK_RE.findall 的 tuple 還原成可再解析的字串。"""
    period, hour, minute, plus_days = groups
    s = f"{period}{hour}:{minute}"
    return s + f"+{plus_days}" if plus_days else s
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_gf_parse.py -v`
Expected: PASS，13 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/gf_parse.py tests/test_gf_parse.py
git commit -m "feat(fare): 解析航班列表項

fixture 為實測真實文字，含直飛與經 BKK 轉機兩種格式。
價格 regex 使用全形 ￦，半形 ₩ 抓不到。"
```

---

## Task 4: 掃描組合產生器

**Files:**
- Create: `scripts/fare_combos.py`
- Test: `tests/test_fare_combos.py`

Phase 1 範圍：韓國進出（ICN／PUS 各進出＝4 組城市對）× VIE／MXP × 108 組日期 = 864 組。

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_fare_combos.py`：

```python
"""掃描組合產生測試。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fare_combos import combo_id, date_windows, generate  # noqa: E402

PHASE1 = {
    "asia_in": ["ICN", "PUS"],
    "asia_out": ["ICN", "PUS"],
    "long_haul": ["VIE", "MXP"],
    "windows": {
        "leg1": ("2026-12-21", "2026-12-23"),
        "leg2": ("2027-02-25", "2027-02-27"),
        "leg3": ("2027-03-05", "2027-03-08"),
        "leg4": ("2027-04-14", "2027-04-16"),
    },
}


def test_日期窗展開為每日清單():
    assert date_windows("2026-12-21", "2026-12-23") == [
        "2026-12-21", "2026-12-22", "2026-12-23"]


def test_四天窗展開四天():
    assert len(date_windows("2027-03-05", "2027-03-08")) == 4


def test_phase1總組合數為864():
    # 城市對 2×2=4，目的地 2，日期 3×3×4×3=108 → 4×2×108 = 864
    assert len(generate(PHASE1)) == 864


def test_每組合為四段且首段飛台北():
    combos = generate(PHASE1)
    for c in combos[:20]:
        assert len(c["legs"]) == 4
        assert c["legs"][0][2] == "TPE"
        assert c["legs"][1][1] == "TPE"
        assert c["legs"][3][1] == "TPE"


def test_長程段來回為同一目的地():
    for c in generate(PHASE1)[:20]:
        assert c["legs"][1][2] == c["legs"][2][1]


def test_combo_id穩定且唯一():
    combos = generate(PHASE1)
    ids = [c["id"] for c in combos]
    assert len(set(ids)) == len(ids)
    # 同樣輸入必須得到同樣 id，否則重複掃描會產生重複記錄
    assert combo_id(combos[0]["legs"]) == combos[0]["id"]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_fare_combos.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fare_combos'`

- [ ] **Step 3: 實作組合產生器**

建立 `scripts/fare_combos.py`：

```python
#!/usr/bin/env python3
"""產生待掃描的四段行程組合。

四段結構固定為境外票模式：
    腿1  <亞洲進> → TPE      讓票價以該國為 fare origin
    腿2  TPE → <長程目的地>
    腿3  <長程目的地> → TPE
    腿4  TPE → <亞洲出>      回到出發區域，形成 open-jaw

Phase 1（韓國進出 × 歐洲兩點）為 4 × 2 × 108 = 864 組。
"""

import hashlib
from datetime import date, timedelta

PHASE1 = {
    "asia_in": ["ICN", "PUS"],
    "asia_out": ["ICN", "PUS"],
    "long_haul": ["VIE", "MXP"],
    "windows": {
        "leg1": ("2026-12-21", "2026-12-23"),
        "leg2": ("2027-02-25", "2027-02-27"),
        "leg3": ("2027-03-05", "2027-03-08"),
        "leg4": ("2027-04-14", "2027-04-16"),
    },
}


def date_windows(start, end):
    """把起訖日展開成每日字串清單（含頭含尾）。"""
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    out = []
    while d0 <= d1:
        out.append(d0.isoformat())
        d0 += timedelta(days=1)
    return out


def combo_id(legs):
    """由四段內容產生穩定 id，確保同組合重複掃描落在同一筆。"""
    key = "|".join(f"{d}:{o}-{t}" for d, o, t in legs)
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def generate(config):
    """依設定產生所有組合，回傳 [{"id":..., "legs":[(date,from,to)x4]}]。"""
    w = config["windows"]
    d1 = date_windows(*w["leg1"])
    d2 = date_windows(*w["leg2"])
    d3 = date_windows(*w["leg3"])
    d4 = date_windows(*w["leg4"])

    combos = []
    for a_in in config["asia_in"]:
        for a_out in config["asia_out"]:
            for dest in config["long_haul"]:
                for x1 in d1:
                    for x2 in d2:
                        for x3 in d3:
                            for x4 in d4:
                                legs = [
                                    (x1, a_in, "TPE"),
                                    (x2, "TPE", dest),
                                    (x3, dest, "TPE"),
                                    (x4, "TPE", a_out),
                                ]
                                combos.append({"id": combo_id(legs), "legs": legs})
    return combos
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_fare_combos.py -v`
Expected: PASS，6 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/fare_combos.py tests/test_fare_combos.py
git commit -m "feat(fare): 掃描組合產生器

Phase 1 韓國進出 × VIE/MXP × 108 日期組合 = 864 組。"
```

---

## Task 5: 匯率換算

**Files:**
- Create: `scripts/fx_rate.py`
- Test: `tests/test_fx_rate.py`

實測 `open.er-api.com` 可用且免 key（`frankfurter` 301、`exchangerate.host` 已需付費 key）。

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_fx_rate.py`：

```python
"""匯率換算測試。換算邏輯離線測，取匯率另有 --live 測試。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fx_rate import fetch_krw_twd, to_twd  # noqa: E402


def test_換算取整數():
    # 1,774,600 KRW × 0.022492 = 39,914.3032
    assert to_twd(1774600, 0.022492) == 39914


def test_換算四捨五入():
    assert to_twd(100, 0.5) == 50
    assert to_twd(101, 0.5) == 51


def test_匯率為None時回傳None():
    assert to_twd(1774600, None) is None


@pytest.mark.live
def test_實際取得匯率():
    rate, fetched_at = fetch_krw_twd()
    # KRW→TWD 合理範圍，2026-08 實測為 0.0225
    assert 0.015 < rate < 0.035
    assert fetched_at
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_fx_rate.py -v -m "not live"`
Expected: FAIL — `ModuleNotFoundError: No module named 'fx_rate'`

- [ ] **Step 3: 實作匯率模組**

建立 `scripts/fx_rate.py`：

```python
#!/usr/bin/env python3
"""取得 KRW→TWD 匯率並換算。

2026-08-18 實測三家免費服務：
    open.er-api.com        可用，免 key，每日更新    ← 採用
    api.frankfurter.app    301 重導
    api.exchangerate.host  已改為需要 access key

匯率每日更新一次即可，不需每次查詢都取。
"""

import json
import math
import urllib.request

API = "https://open.er-api.com/v6/latest/KRW"


def fetch_krw_twd(timeout=15):
    """回傳 (匯率, 更新時間字串)。失敗時拋出例外，由呼叫端決定如何處理。"""
    with urllib.request.urlopen(API, timeout=timeout) as r:
        data = json.loads(r.read())
    if data.get("result") != "success":
        raise RuntimeError(f"匯率 API 回傳非 success：{data.get('result')}")
    rate = data["rates"]["TWD"]
    return rate, data.get("time_last_update_utc", "")


def to_twd(krw, rate):
    """把韓元換算成台幣整數。rate 為 None 時回傳 None。

    用 math.floor(x + 0.5) 而非 round()：Python 的 round() 是銀行家捨入，
    round(50.5) == 50、round(101 * 0.5) == 50，與「四捨五入」的預期不符。
    """
    if rate is None:
        return None
    return math.floor(krw * rate + 0.5)
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_fx_rate.py -v -m "not live"`
Expected: PASS，3 passed（`test_實際取得匯率` 被 deselect）

再跑一次含連網測試確認 API 真的可用：

Run: `python3 -m pytest tests/test_fx_rate.py -v`
Expected: PASS，4 passed

若 live 測試出現 `SSL: CERTIFICATE_VERIFY_FAILED`，那不是 API 或網路問題，
而是 python.org 版 Python 未安裝 CA bundle。見 Task 5 附註。

- [ ] **Step 5: 註冊 live marker 避免警告**

建立 `pytest.ini`：

```ini
[pytest]
markers =
    live: 需要連外網路的測試
```

- [ ] **Step 6: Commit**

```bash
git add scripts/fx_rate.py tests/test_fx_rate.py pytest.ini
git commit -m "feat(fare): KRW→TWD 匯率換算

採 open.er-api.com（實測免 key 可用）。"
```

---

## Task 6: 掃描結果儲存

**Files:**
- Create: `scripts/fare_store.py`
- Test: `tests/test_fare_store.py`

本機 JSON 為主要真實來源（支援斷點續跑），Firebase 為前端讀取用的同步目標。

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_fare_store.py`：

```python
"""掃描結果儲存測試。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fare_store import LocalStore  # noqa: E402


def test_寫入後可讀回(tmp_path):
    s = LocalStore(tmp_path / "f.json")
    s.put("abc", {"priceKRW": 1774600, "status": "ok"})
    assert s.get("abc")["priceKRW"] == 1774600


def test_已掃描過的id可判定(tmp_path):
    s = LocalStore(tmp_path / "f.json")
    s.put("abc", {"status": "ok"})
    assert s.has("abc") is True
    assert s.has("zzz") is False


def test_error狀態不算已掃描才能重試(tmp_path):
    # 斷點續跑時，錯誤的組合必須重跑，查無票的不必
    s = LocalStore(tmp_path / "f.json")
    s.put("e1", {"status": "error"})
    s.put("n1", {"status": "no_result"})
    assert s.has("e1") is False
    assert s.has("n1") is True


def test_落地為檔案且可重新載入(tmp_path):
    p = tmp_path / "f.json"
    LocalStore(p).put("abc", {"status": "ok", "priceKRW": 1})
    assert json.loads(p.read_text())["abc"]["priceKRW"] == 1
    assert LocalStore(p).has("abc") is True


def test_每次put都即時落地(tmp_path):
    # 掃描中途被中斷也不能掉資料
    p = tmp_path / "f.json"
    s = LocalStore(p)
    s.put("a", {"status": "ok"})
    assert "a" in json.loads(p.read_text())
    s.put("b", {"status": "ok"})
    assert "b" in json.loads(p.read_text())
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_fare_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fare_store'`

- [ ] **Step 3: 實作儲存層**

建立 `scripts/fare_store.py`：

```python
#!/usr/bin/env python3
"""掃描結果的儲存。

本機 JSON 是唯一真實來源，支援斷點續跑；Firebase 只是給前端讀的同步副本。
掃描 864 組要跑近兩小時，中途中斷必須能接續，因此每筆 put 都立即落地。

Firebase Database URL 從環境變數 FOUR_LEG_FARE_DB 或
~/four_leg_fare.conf 讀取。本 repo 為 public，URL 絕不進版控。
"""

import json
import os
import urllib.request
from pathlib import Path

CONF = Path.home() / "four_leg_fare.conf"

# 這些狀態代表「已經有答案了」，續跑時可跳過。
# error 不在其中：那是查詢失敗，必須重試。
DONE_STATUSES = {"ok", "no_result"}


class LocalStore:
    """本機 JSON 儲存，每次寫入立即落地。"""

    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
        else:
            self.data = {}
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def has(self, combo_id):
        """是否已有可用結果（error 不算，需重試）。"""
        rec = self.data.get(combo_id)
        return bool(rec) and rec.get("status") in DONE_STATUSES

    def get(self, combo_id):
        return self.data.get(combo_id)

    def put(self, combo_id, record):
        self.data[combo_id] = record
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=1))

    def all_ok(self):
        """回傳所有成功且有價格的記錄。"""
        return {k: v for k, v in self.data.items()
                if v.get("status") == "ok" and v.get("priceKRW")}


def read_db_url():
    """讀 Firebase Database URL。找不到時回傳 None（僅本機儲存）。"""
    url = os.environ.get("FOUR_LEG_FARE_DB", "").strip()
    if url:
        return url.rstrip("/")
    if CONF.exists():
        for line in CONF.read_text().splitlines():
            line = line.strip()
            if line.startswith("FOUR_LEG_FARE_DB="):
                return line.split("=", 1)[1].strip().rstrip("/")
    return None


def push_firebase(db_url, combo_id, record, timeout=20):
    """PATCH 單筆記錄到 Firebase。

    只 PATCH 最深的子節點，不整包 PUT——整包 PUT 會洗掉其他欄位
    （專案先前踩過此坑）。
    """
    url = f"{db_url}/fares/{combo_id}.json"
    body = json.dumps(record, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url, data=body, method="PATCH",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status == 200
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_fare_store.py -v`
Expected: PASS，5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/fare_store.py tests/test_fare_store.py
git commit -m "feat(fare): 掃描結果儲存層

本機 JSON 即時落地支援斷點續跑；error 狀態不視為完成以便重試。
Firebase 只 PATCH 子節點避免洗掉其他欄位。"
```

---

## Task 7: 快掃單一組合

**Files:**
- Create: `scripts/fare_scan.py`

這是第一個碰真實網路的任務，用 Task 1–3 的純函式組裝。

- [ ] **Step 1: 建立掃描器與單組查詢**

建立 `scripts/fare_scan.py`：

```python
#!/usr/bin/env python3
"""四腿票掃描器：用 Google Flights 查四段行程總價。

用法：
    python3 scripts/fare_scan.py --once          # 只掃一組，驗證環境
    python3 scripts/fare_scan.py --phase1        # 掃 Phase 1 全部 864 組
    python3 scripts/fare_scan.py --detail 20     # 對最便宜前 20 組補時刻

兩段式掃描（依據見 spec 的「完整四段資訊的取得成本」）：
    快掃 約 6 秒／組，只讀第一段列表，取整趟總價
    詳掃 約 48 秒／組，逐段點選補四段時刻與直飛狀態

各段選項的總價相同（同一 fare bucket），所以總價快掃就準確，
詳掃純粹是補時刻欄位。

結果存 ~/four-leg-fares.json，中斷可直接重跑接續。
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fare_combos import PHASE1, generate
from fare_store import LocalStore, push_firebase, read_db_url
from fx_rate import fetch_krw_twd, to_twd
from gf_parse import parse_row
from gf_url import build_url

STORE_PATH = Path.home() / "four-leg-fares.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

# 列表載入的輪詢設定：每 2.5 秒檢查一次，最多等 60 秒
POLL_INTERVAL_MS = 2500
POLL_MAX_TRIES = 24

ROWS_JS = """() => [...document.querySelectorAll('li')]
    .map(e => (e.innerText || '').replace(/\\n+/g, ' | '))
    .filter(t => t.includes('整趟行程'))"""


async def read_rows(page):
    """等待並讀取含「整趟行程」的航班列。逾時回傳空清單。"""
    for _ in range(POLL_MAX_TRIES):
        await page.wait_for_timeout(POLL_INTERVAL_MS)
        rows = await page.evaluate(ROWS_JS)
        if rows:
            return rows
    return []


async def quick_scan(context, legs):
    """快掃一組行程，回傳結果 dict。"""
    page = await context.new_page()
    try:
        await page.goto(build_url(legs, currency="KRW"),
                        wait_until="domcontentloaded", timeout=60000)
        rows = await read_rows(page)
        if not rows:
            return {"status": "no_result"}

        parsed = [p for p in (parse_row(r) for r in rows) if p]
        if not parsed:
            return {"status": "no_result"}

        best = min(parsed, key=lambda p: p["price"])
        return {
            "status": "ok",
            "priceKRW": best["price"],
            "carrier": best["carrier"],
            "legs": [
                {"date": d, "from": o, "to": t,
                 **({"depart": best["depart"], "arrive": best["arrive"],
                     "arrivePlusDays": best["arrive_plus_days"],
                     "duration": best["duration"],
                     "nonstop": best["nonstop"], "via": best["via"]}
                    if i == 0 else {})}
                for i, (d, o, t) in enumerate(legs)
            ],
            "detail": "quick",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}
    finally:
        await page.close()
```

- [ ] **Step 2: 加入 `--once` 入口**

在 `scripts/fare_scan.py` 檔尾追加：

```python
async def run_once():
    """掃一組已知有票的行程，驗證整條鏈路可用。

    這組是使用者 2026-08-18 實際查到的行程，長榮官網報價
    KRW 1,736,600，Google Flights 應報約 1,774,600（差約 2.2%）。
    """
    from playwright.async_api import async_playwright

    legs = [("2026-12-23", "PUS", "TPE"), ("2027-02-26", "TPE", "SEA"),
            ("2027-03-07", "SEA", "TPE"), ("2027-04-20", "TPE", "ICN")]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="zh-TW", user_agent=UA,
            viewport={"width": 1600, "height": 1400})
        result = await quick_scan(ctx, legs)
        await browser.close()

    print(f"status   : {result['status']}")
    if result["status"] == "ok":
        rate, at = fetch_krw_twd()
        twd = to_twd(result["priceKRW"], rate)
        print(f"價格     : ￦{result['priceKRW']:,}  ≈ NT${twd:,}")
        print(f"航空公司 : {result['carrier']}")
        leg1 = result["legs"][0]
        print(f"第一段   : {leg1['depart']}–{leg1['arrive']} "
              f"{'直達' if leg1['nonstop'] else '轉機 ' + str(leg1['via'])}")
        print(f"匯率     : {rate} ({at})")


def main():
    ap = argparse.ArgumentParser(description="四腿票掃描器")
    ap.add_argument("--once", action="store_true", help="只掃一組驗證環境")
    args = ap.parse_args()

    if args.once:
        asyncio.run(run_once())
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 執行驗證整條鏈路**

Run: `python3 scripts/fare_scan.py --once`

Expected: 輸出類似（價格會隨時間變動，重點是 status 為 ok 且價格落在合理範圍）

```
status   : ok
價格     : ￦1,774,600  ≈ NT$39,914
航空公司 : 長榮航空
第一段   : 18:55–20:25 直達
匯率     : 0.022492 (Tue, 18 Aug 2026 00:02:31 +0000)
```

若 status 為 `no_result`，先確認 `python3 -m playwright install chromium` 已執行。

- [ ] **Step 4: Commit**

```bash
git add scripts/fare_scan.py
git commit -m "feat(fare): 快掃單組行程

以使用者已知行程驗證整條鏈路，對照長榮官網報價。"
```

---

## Task 8: 批次掃描與斷點續跑

**Files:**
- Modify: `scripts/fare_scan.py`

- [ ] **Step 1: 加入批次掃描函式**

在 `scripts/fare_scan.py` 的 `def main():` 之前插入：

```python
# 連續這麼多組查無結果就中止：正常情況不可能整片沒票，
# 較可能是 tfs 格式失效或被速率限制。靜默記成「沒票」會讓
# 整批資料變成無聲的錯誤。
CONSECUTIVE_EMPTY_ABORT = 15


async def scan_batch(combos, store, db_url, rate, fx_at,
                     delay=3.0, concurrency=2):
    """批次快掃。已有結果的跳過，每筆立即落地。"""
    from playwright.async_api import async_playwright

    todo = [c for c in combos if not store.has(c["id"])]
    print(f"待掃 {len(todo)} / 共 {len(combos)} 組"
          f"（已完成 {len(combos) - len(todo)}）")
    if not todo:
        return

    sem = asyncio.Semaphore(concurrency)
    counters = {"done": 0, "ok": 0, "empty_streak": 0, "aborted": False}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="zh-TW", user_agent=UA,
            viewport={"width": 1600, "height": 1400})

        async def worker(combo):
            if counters["aborted"]:
                return
            async with sem:
                result = await quick_scan(ctx, combo["legs"])
                await asyncio.sleep(delay)

            if result["status"] == "ok":
                result["priceTWD"] = to_twd(result["priceKRW"], rate)
                result["fxRate"] = rate
                result["fxAt"] = fx_at
                counters["ok"] += 1
                counters["empty_streak"] = 0
            elif result["status"] == "no_result":
                counters["empty_streak"] += 1

            result["scannedAt"] = datetime.now(timezone.utc).isoformat()
            store.put(combo["id"], result)
            if db_url and result["status"] == "ok":
                try:
                    push_firebase(db_url, combo["id"], result)
                except Exception as e:
                    print(f"  Firebase 寫入失敗：{str(e)[:80]}")

            counters["done"] += 1
            if counters["done"] % 10 == 0:
                print(f"  {counters['done']}/{len(todo)} 完成，"
                      f"{counters['ok']} 組有票")

            if counters["empty_streak"] >= CONSECUTIVE_EMPTY_ABORT:
                counters["aborted"] = True
                print(f"\n!! 連續 {CONSECUTIVE_EMPTY_ABORT} 組查無結果，中止。\n"
                      f"   可能是 tfs 格式失效或被速率限制，"
                      f"請先用 --once 確認鏈路是否還通。")

        await asyncio.gather(*(worker(c) for c in todo))
        await browser.close()

    print(f"\n完成 {counters['done']} 組，{counters['ok']} 組有票")
```

- [ ] **Step 2: 加入 `--phase1` 入口**

把 `main()` 整個替換為：

```python
def main():
    ap = argparse.ArgumentParser(description="四腿票掃描器")
    ap.add_argument("--once", action="store_true", help="只掃一組驗證環境")
    ap.add_argument("--phase1", action="store_true",
                    help="掃 Phase 1：韓國進出 × VIE/MXP，864 組")
    ap.add_argument("--delay", type=float, default=3.0, help="每組間隔秒數")
    ap.add_argument("--concurrency", type=int, default=2, help="並行數")
    args = ap.parse_args()

    if args.once:
        asyncio.run(run_once())
        return

    if args.phase1:
        combos = generate(PHASE1)
        store = LocalStore(STORE_PATH)
        db_url = read_db_url()
        print(f"結果檔：{STORE_PATH}")
        print(f"Firebase：{'已設定' if db_url else '未設定（僅本機儲存）'}")
        try:
            rate, fx_at = fetch_krw_twd()
            print(f"匯率：KRW→TWD {rate}（{fx_at}）")
        except Exception as e:
            rate, fx_at = None, ""
            print(f"匯率取得失敗，台幣欄位留空：{str(e)[:80]}")
        asyncio.run(scan_batch(combos, store, db_url, rate, fx_at,
                               delay=args.delay, concurrency=args.concurrency))
        return

    ap.print_help()
```

- [ ] **Step 3: 用小樣本驗證續跑機制**

先跑 30 秒後按 Ctrl-C 中斷：

Run: `timeout 30 python3 scripts/fare_scan.py --phase1 --concurrency 1`
Expected: 印出「待掃 864 / 共 864 組」並開始掃描，中斷後有部分結果落地

再跑一次確認會跳過已完成的：

Run: `timeout 20 python3 scripts/fare_scan.py --phase1 --concurrency 1`
Expected: 「待掃 N / 共 864 組（已完成 M）」，M 大於 0

- [ ] **Step 4: Commit**

```bash
git add scripts/fare_scan.py
git commit -m "feat(fare): 批次掃描與斷點續跑

含節流、並行控制，以及連續查無結果自動中止的保護——
避免 tfs 格式失效被靜默記成「所有組合都沒票」。"
```

---

## Task 9: 詳掃補四段時刻

**Files:**
- Modify: `scripts/fare_scan.py`

- [ ] **Step 1: 加入詳掃函式**

在 `scripts/fare_scan.py` 的 `def main():` 之前插入：

```python
async def detail_scan(context, legs):
    """逐段點選，補齊四段時刻與直飛狀態。約 48 秒／組。

    每段都選總價最低者。實測各選項總價相同，所以此處選擇不影響
    總價，只影響取得的時刻。
    """
    page = await context.new_page()
    try:
        await page.goto(build_url(legs, currency="KRW"),
                        wait_until="domcontentloaded", timeout=60000)
        collected = []
        for seg in range(len(legs)):
            rows = await read_rows(page)
            if not rows:
                return {"status": "no_result"}
            parsed = [(p, i) for i, p in
                      ((i, parse_row(r)) for i, r in enumerate(rows)) if p]
            if not parsed:
                return {"status": "no_result"}
            best, idx = min(parsed, key=lambda x: x[0]["price"])
            collected.append(best)
            if seg == len(legs) - 1:
                break
            items = page.locator("li").filter(has_text="整趟行程")
            await items.nth(idx).click()
            await page.wait_for_timeout(3000)

        return {
            "status": "ok",
            "priceKRW": collected[0]["price"],
            "carrier": collected[0]["carrier"],
            "legs": [
                {"date": d, "from": o, "to": t,
                 "depart": c["depart"], "arrive": c["arrive"],
                 "arrivePlusDays": c["arrive_plus_days"],
                 "duration": c["duration"],
                 "nonstop": c["nonstop"], "via": c["via"]}
                for (d, o, t), c in zip(legs, collected)
            ],
            "allNonstop": all(c["nonstop"] for c in collected),
            "detail": "full",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}
    finally:
        await page.close()


async def run_detail(top_n, store, db_url, rate, fx_at, delay=3.0):
    """對最便宜的前 N 組執行詳掃。"""
    from playwright.async_api import async_playwright

    ok = store.all_ok()
    ranked = sorted(ok.items(), key=lambda kv: kv[1]["priceKRW"])
    targets = [(cid, rec) for cid, rec in ranked
               if rec.get("detail") != "full"][:top_n]
    print(f"最便宜前 {top_n} 組中，{len(targets)} 組尚未詳掃")
    if not targets:
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="zh-TW", user_agent=UA,
            viewport={"width": 1600, "height": 1400})
        for n, (cid, rec) in enumerate(targets, 1):
            legs = [(l["date"], l["from"], l["to"]) for l in rec["legs"]]
            result = await detail_scan(ctx, legs)
            if result["status"] == "ok":
                result["priceTWD"] = to_twd(result["priceKRW"], rate)
                result["fxRate"] = rate
                result["fxAt"] = fx_at
                result["scannedAt"] = datetime.now(timezone.utc).isoformat()
                store.put(cid, result)
                if db_url:
                    try:
                        push_firebase(db_url, cid, result)
                    except Exception as e:
                        print(f"  Firebase 寫入失敗：{str(e)[:80]}")
                mark = "全直飛" if result["allNonstop"] else "含轉機"
                print(f"  [{n}/{len(targets)}] ￦{result['priceKRW']:,} {mark}")
            else:
                print(f"  [{n}/{len(targets)}] {result['status']}")
            await asyncio.sleep(delay)
        await browser.close()
```

- [ ] **Step 2: 加入 `--detail` 入口**

在 `main()` 中，`if args.phase1:` 區塊之前插入參數定義與處理。先在 `ap.add_argument("--concurrency", ...)` 之後加：

```python
    ap.add_argument("--detail", type=int, metavar="N",
                    help="對最便宜的前 N 組補四段時刻")
```

再在 `if args.phase1:` 區塊之前插入：

```python
    if args.detail:
        store = LocalStore(STORE_PATH)
        db_url = read_db_url()
        try:
            rate, fx_at = fetch_krw_twd()
        except Exception:
            rate, fx_at = None, ""
        asyncio.run(run_detail(args.detail, store, db_url, rate, fx_at,
                               delay=args.delay))
        return
```

- [ ] **Step 3: 驗證詳掃**

Run: `python3 scripts/fare_scan.py --detail 2`

Expected: 對已掃結果中最便宜的 2 組執行詳掃，輸出類似

```
最便宜前 2 組中，2 組尚未詳掃
  [1/2] ￦2,401,200 含轉機
  [2/2] ￦2,401,200 含轉機
```

- [ ] **Step 4: 確認四段時刻已寫入**

Run: `python3 -c "
import json,pathlib
d=json.loads((pathlib.Path.home()/'four-leg-fares.json').read_text())
full=[v for v in d.values() if v.get('detail')=='full']
print('詳掃筆數:',len(full))
if full:
    for l in full[0]['legs']:
        print(f\"  {l['date']} {l['from']}→{l['to']} {l.get('depart')}–{l.get('arrive')} {'直達' if l.get('nonstop') else '轉機 '+str(l.get('via'))}\")
"`

Expected: 四段都有 depart／arrive／nonstop 欄位

- [ ] **Step 5: Commit**

```bash
git add scripts/fare_scan.py
git commit -m "feat(fare): 詳掃補四段時刻與直飛狀態

只對最便宜前 N 組執行，避免全量詳掃的 8 倍成本。"
```

---

## Task 10: 前端比價表

**Files:**
- Create: `four-leg-fare.html`

沿用專案既有單檔 HTML + Firebase 模式。DB URL 存 localStorage，首次開啟時填入。

- [ ] **Step 1: 建立前端骨架與資料載入**

建立 `four-leg-fare.html`：

```html
<!doctype html>
<html lang="zh-TW">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>四腿票比價</title>
<style>
  :root{--bg:#faf9f7;--card:#fff;--line:#e5e2dc;--ink:#2b2b2b;
        --muted:#7a756c;--accent:#1a73e8;--best:#0b8043}
  *{box-sizing:border-box}
  body{margin:0;padding:16px;font-family:-apple-system,"PingFang TC",sans-serif;
       background:var(--bg);color:var(--ink);font-size:16px;line-height:1.6}
  h1{font-size:20px;margin:0 0 4px}
  .sub{color:var(--muted);font-size:14px;margin-bottom:16px}
  .bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
  select,button,input{font-size:15px;padding:8px 12px;border:1px solid var(--line);
         border-radius:8px;background:var(--card);color:var(--ink)}
  button{cursor:pointer}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;
        padding:14px 16px;margin-bottom:10px}
  .card.best{border-color:var(--best);border-width:2px}
  .price{font-size:22px;font-weight:700}
  .price small{font-size:13px;color:var(--muted);font-weight:400;margin-left:8px}
  .legs{margin-top:10px;display:grid;gap:6px}
  .leg{display:grid;grid-template-columns:96px 1fr auto;gap:10px;
       font-size:14px;align-items:center}
  .leg .route{font-weight:600}
  .leg .time{color:var(--muted)}
  .leg .time.pending{opacity:.4;font-style:italic}
  .tag{font-size:12px;padding:2px 8px;border-radius:12px;white-space:nowrap}
  .tag.nonstop{background:#e6f4ea;color:var(--best)}
  .tag.via{background:#fef7e0;color:#b06000}
  .tag.unknown{background:#f1f3f4;color:var(--muted)}
  .links{margin-top:10px;display:flex;gap:10px}
  .links a{font-size:14px;color:var(--accent);text-decoration:none}
  .empty{text-align:center;color:var(--muted);padding:40px 0}
  .filebtn{font-size:15px;padding:8px 12px;border:1px solid var(--line);
        border-radius:8px;background:var(--card);cursor:pointer}
</style>

<h1>四腿票比價</h1>
<div class="sub" id="meta">載入中…</div>

<div class="bar">
  <select id="sort">
    <option value="price">依價格（低→高）</option>
    <option value="date">依出發日</option>
  </select>
  <select id="filterDest"><option value="">全部目的地</option></select>
  <select id="filterStop">
    <option value="">直飛不限</option>
    <option value="nonstop">只看四段全直飛</option>
  </select>
  <label class="filebtn">載入本機檔案
    <input type="file" id="loadFile" accept=".json" hidden>
  </label>
  <button id="setup">設定資料庫</button>
</div>

<div id="list"></div>

<script>
const LS_KEY = "fourLegFareDB";
let RECORDS = [];

function dbUrl(){ return localStorage.getItem(LS_KEY) || ""; }

function askDb(){
  const cur = dbUrl();
  const v = prompt("Firebase Realtime Database 網址\n" +
                   "例：https://xxx-default-rtdb.firebaseio.com", cur);
  if (v !== null){ localStorage.setItem(LS_KEY, v.trim().replace(/\/$/,"")); load(); }
}
document.getElementById("setup").onclick = askDb;

// 掃描器把結果寫在 ~/four-leg-fares.json。用 file:// 開啟時瀏覽器
// 不允許 fetch 本機檔案，所以改由使用者手動選檔載入。
document.getElementById("loadFile").onchange = async (ev) => {
  const f = ev.target.files[0];
  if (!f) return;
  try{
    const data = JSON.parse(await f.text());
    RECORDS = Object.entries(data)
      .map(([id, v]) => ({id, ...v}))
      .filter(v => v.status === "ok" && v.priceKRW);
    buildDestFilter();
    render();
  }catch(e){
    document.getElementById("meta").textContent = "檔案讀取失敗：" + e.message;
  }
};

function buildDestFilter(){
  const sel = document.getElementById("filterDest");
  const dests = [...new Set(RECORDS.map(r => r.legs[1].to))].sort();
  sel.innerHTML = '<option value="">全部目的地</option>' +
    dests.map(d => `<option value="${d}">${d}</option>`).join("");
}

async function load(){
  const base = dbUrl();
  if (!base){
    document.getElementById("meta").textContent = "尚未設定資料庫";
    document.getElementById("list").innerHTML =
      '<div class="empty">點「載入本機檔案」選擇 ~/four-leg-fares.json<br>' +
      '或點「設定資料庫」填入 Firebase 網址</div>';
    return;
  }
  try{
    const r = await fetch(base + "/fares.json");
    const data = await r.json() || {};
    RECORDS = Object.entries(data)
      .map(([id, v]) => ({id, ...v}))
      .filter(v => v.status === "ok" && v.priceKRW);
    buildDestFilter();
    render();
  }catch(e){
    document.getElementById("meta").textContent = "讀取失敗：" + e.message;
  }
}

function fmtTWD(n){ return n ? "NT$" + n.toLocaleString() : "—"; }
function fmtKRW(n){ return "￦" + n.toLocaleString(); }

function render(){
  const sortBy = document.getElementById("sort").value;
  const fDest = document.getElementById("filterDest").value;
  const fStop = document.getElementById("filterStop").value;

  let rows = RECORDS.slice();
  if (fDest) rows = rows.filter(r => r.legs[1].to === fDest);
  if (fStop === "nonstop") rows = rows.filter(r => r.allNonstop === true);

  rows.sort((a,b) => sortBy === "price"
    ? a.priceKRW - b.priceKRW
    : a.legs[0].date.localeCompare(b.legs[0].date));

  const cheapest = rows.length ? rows[0].priceKRW : null;
  const fx = RECORDS.find(r => r.fxRate);
  document.getElementById("meta").textContent =
    `${rows.length} 組${fx ? `　匯率 ${fx.fxRate}（${fx.fxAt}）` : ""}`;

  document.getElementById("list").innerHTML = rows.length
    ? rows.map(r => card(r, r.priceKRW === cheapest)).join("")
    : '<div class="empty">沒有符合條件的組合</div>';
}

function card(r, isBest){
  const legs = r.legs.map(l => {
    const known = l.depart && l.arrive;
    const time = known
      ? `${l.depart} – ${l.arrive}${l.arrivePlusDays ? "<sup>+" + l.arrivePlusDays + "</sup>" : ""}`
      : "時刻待補";
    let tag;
    if (l.nonstop === true) tag = '<span class="tag nonstop">直飛</span>';
    else if (l.nonstop === false) tag = `<span class="tag via">經 ${l.via || "轉機"}</span>`;
    else tag = '<span class="tag unknown">未知</span>';
    return `<div class="leg">
      <span class="route">${l.from}→${l.to}</span>
      <span class="time${known ? "" : " pending"}">${l.date}　${time}</span>
      ${tag}</div>`;
  }).join("");

  return `<div class="card${isBest ? " best" : ""}">
    <div class="price">${fmtTWD(r.priceTWD)}<small>${fmtKRW(r.priceKRW)}</small></div>
    <div class="legs">${legs}</div>
    <div class="links">
      <a href="${gfLink(r)}" target="_blank" rel="noopener">Google Flights 複查</a>
      <a href="https://www.evaair.com/zh-tw/index.html" target="_blank" rel="noopener">長榮訂票</a>
    </div>
  </div>`;
}

function gfLink(r){
  // 掃描器已存過 tfs 時直接用；否則退回搜尋首頁
  return r.url || "https://www.google.com/travel/flights";
}

document.getElementById("sort").onchange = render;
document.getElementById("filterDest").onchange = render;
document.getElementById("filterStop").onchange = render;
load();
</script>
</html>
```

- [ ] **Step 2: 在瀏覽器開啟確認畫面**

Run: `open four-leg-fare.html`
Expected: 顯示「尚未設定資料庫」，畫面提示可點「載入本機檔案」或「設定資料庫」

- [ ] **Step 2b: 載入真實資料確認畫面**

點「載入本機檔案」，選擇 `~/four-leg-fares.json`（掃描器已產生的真實結果）。
Expected: 出現比價卡片，台幣為主、韓元小字並列，四段航線與直飛狀態正確顯示，
最便宜的一組有綠色外框。快掃資料的第 2–4 段時刻顯示為淡灰的「時刻待補」。

- [ ] **Step 3: Commit**

```bash
git add four-leg-fare.html
git commit -m "feat(fare): 前端比價表

台幣為主韓元為輔，逐段直飛狀態標示，快掃未補的時刻以淡灰標示。"
```

---

## Task 11: 掃描器存入 Google Flights 連結

**Files:**
- Modify: `scripts/fare_scan.py`

前端的「Google Flights 複查」需要每組的查詢網址。

- [ ] **Step 1: 在快掃結果加入 url 欄位**

在 `scripts/fare_scan.py` 的 `quick_scan` 中，把回傳 dict 的 `"detail": "quick",` 那行改為：

```python
            "detail": "quick",
            "url": build_url(legs, currency="KRW"),
```

同樣在 `detail_scan` 的回傳 dict 中，把 `"detail": "full",` 改為：

```python
            "detail": "full",
            "url": build_url(legs, currency="KRW"),
```

- [ ] **Step 2: 驗證欄位寫入**

Run: `python3 scripts/fare_scan.py --once`
Expected: 仍正常輸出 status ok

Run: `python3 -c "
import sys,pathlib; sys.path.insert(0,'scripts')
from gf_url import build_url
print(build_url([('2026-12-23','PUS','TPE'),('2027-02-26','TPE','SEA'),('2027-03-07','SEA','TPE'),('2027-04-20','TPE','ICN')])[:90])
"`
Expected: 印出以 `https://www.google.com/travel/flights/search?tfs=` 開頭的網址

- [ ] **Step 3: Commit**

```bash
git add scripts/fare_scan.py
git commit -m "feat(fare): 掃描結果存入 GF 查詢網址供前端複查"
```

---

## Task 12: 執行 Phase 1

**Files:** 無程式碼變更，這是實際跑資料的任務。

- [ ] **Step 1: 確認鏈路可用**

Run: `python3 scripts/fare_scan.py --once`
Expected: status ok，價格落在 ￦1,700,000–2,000,000 之間

- [ ] **Step 2: 小樣本試跑，觀察是否被速率限制**

Run: `timeout 300 python3 scripts/fare_scan.py --phase1 --concurrency 2 --delay 3`
Expected: 5 分鐘內完成約 40–80 組，`ok` 數量持續增加。若出現「連續 15 組查無結果」中止訊息，代表被限制，改用 `--concurrency 1 --delay 8` 重跑。

- [ ] **Step 3: 完整跑 Phase 1**

Run: `python3 scripts/fare_scan.py --phase1 --concurrency 2 --delay 3`
Expected: 約 1.5–2 小時完成 864 組。中途可 Ctrl-C，重跑會自動接續。

- [ ] **Step 4: 詳掃最便宜的 20 組**

Run: `python3 scripts/fare_scan.py --detail 20`
Expected: 約 16 分鐘，每組印出價格與「全直飛／含轉機」

- [ ] **Step 5: 檢視結果摘要**

Run: `python3 -c "
import json,pathlib
d=json.loads((pathlib.Path.home()/'four-leg-fares.json').read_text())
ok=[v for v in d.values() if v.get('status')=='ok']
print(f'總計 {len(d)} 組，有票 {len(ok)} 組')
for v in sorted(ok,key=lambda x:x['priceKRW'])[:10]:
    l=v['legs']; ns='全直飛' if v.get('allNonstop') else ''
    print(f\"  NT\${v.get('priceTWD',0):>7,}  {l[0]['date']} {l[0]['from']}→TPE  \"
          f\"{l[1]['date']} TPE→{l[1]['to']}  {l[3]['date']} TPE→{l[3]['to']} {ns}\")
"`
Expected: 列出最便宜的 10 組，含台幣價格與四段日期

- [ ] **Step 6: 記錄實測結果到 spec**

把 Phase 1 的實際耗時、是否遭遇速率限制、最便宜組合的價格寫回
`docs/superpowers/specs/2026-08-18-four-leg-fare-scanner-design.md` 的
「未解問題」段落——速率限制原本就列為未知，跑完應該有答案。

```bash
git add docs/superpowers/specs/2026-08-18-four-leg-fare-scanner-design.md
git commit -m "docs(spec): 補上 Phase 1 實測結果與速率限制觀察"
```

---

## Task 13: 掃描限定直飛航班

**Files:**
- Modify: `scripts/gf_url.py`
- Modify: `scripts/fare_scan.py`
- Modify: `tests/test_gf_url.py`

使用者要求只看直飛。實測已確認 `tfs` 的每個 `[3]` 段內加 `[5]=0` 即為「僅顯示直達航班」，
且限定直飛**不會變貴也不會沒票**（SEA 線同價；VIE 線同價、選項由 4 個減為 2 個）。

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_gf_url.py` 檔尾追加（並把最上方 import 改為 `from gf_url import build_tfs, build_url`，若已是則不動）：

```python
# 使用者在 Google Flights 點「僅顯示直達航班」後產生的真實網址。
# 注意 Google 只把旗標加在第一段（UI 的篩選只套用當前段）。
GOOGLE_NONSTOP_FIRST_LEG = (
    "CBwQAhogEgoyMDI2LTEyLTIzKABqBwgBEgNQVVNyBwgBEgNUUEUaHhIKMjAyNy0wMi0yNmoH"
    "CAESA1RQRXIHCAESA1NFQRoeEgoyMDI3LTAzLTA3agcIARIDU0VBcgcIARIDVFBFGh4SCjIw"
    "MjctMDQtMjBqBwgBEgNUUEVyBwgBEgNJQ05AAUgBcAGCAQsI____________AZgBAw"
)

# 四段全部限定直飛（本專案實際要用的形式）
ALL_NONSTOP = (
    "CBwQAhogEgoyMDI2LTEyLTIzKABqBwgBEgNQVVNyBwgBEgNUUEUaIBIKMjAyNy0wMi0yNigA"
    "agcIARIDVFBFcgcIARIDU0VBGiASCjIwMjctMDMtMDcoAGoHCAESA1NFQXIHCAESA1RQRRog"
    "EgoyMDI3LTA0LTIwKABqBwgBEgNUUEVyBwgBEgNJQ05AAUgBcAGCAQsI____________AZgBAw"
)


def test_僅第一段限直飛可重現Google產生的網址():
    assert build_tfs(GROUND_TRUTH_LEGS, nonstop=[0]) == GOOGLE_NONSTOP_FIRST_LEG


def test_四段全限直飛():
    assert build_tfs(GROUND_TRUTH_LEGS, nonstop=True) == ALL_NONSTOP


def test_預設不限直飛時與原本相同():
    # 既有行為不可被破壞
    assert build_tfs(GROUND_TRUTH_LEGS) == REAL_TFS
    assert build_tfs(GROUND_TRUTH_LEGS, nonstop=False) == REAL_TFS


def test_build_url可帶直飛參數():
    u = build_url(GROUND_TRUTH_LEGS, nonstop=True)
    assert ALL_NONSTOP in u
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python3 -m pytest tests/test_gf_url.py -v`
Expected: FAIL — `TypeError: build_tfs() got an unexpected keyword argument 'nonstop'`

- [ ] **Step 3: 實作**

在 `scripts/gf_url.py` 中，把 `_leg` 與 `build_tfs`、`build_url` 三個函式改為：

```python
def _leg(date, origin, dest, nonstop=False):
    body = _str_field(2, date)
    if nonstop:
        # [5]=0 等同 UI 的「僅顯示直達航班」（0 次轉機）。
        # 實測位置在日期之後、出發地之前，順序不可調換。
        body += _varint_field(5, 0)
    return body + _msg_field(13, _location(origin)) + _msg_field(14, _location(dest))


def build_tfs(legs, adults=1, cabin=CABIN_ECONOMY, nonstop=False):
    """legs: [(date, origin_iata, dest_iata), ...]，回傳 base64url 字串。

    nonstop: True 代表每段都限定直達；也可傳段索引的可迭代物件
    （如 [0]）只限定特定段。
    """
    if nonstop is True:
        ns = set(range(len(legs)))
    elif nonstop is False or nonstop is None:
        ns = set()
    else:
        ns = set(nonstop)

    body = _varint_field(1, 28) + _varint_field(2, 2)
    for i, (date, origin, dest) in enumerate(legs):
        body += _msg_field(3, _leg(date, origin, dest, i in ns))
    body += (_varint_field(8, adults)
             + _varint_field(9, cabin)
             + _varint_field(14, 1)
             + _msg_field(16, _varint_field(1, (1 << 64) - 1))
             + _varint_field(19, TRIP_MULTI_CITY))
    return base64.urlsafe_b64encode(body).decode().rstrip("=")


def build_url(legs, currency="KRW", lang="zh-TW", adults=1, nonstop=False):
    """產生可直接開啟的 Google Flights 查詢網址。"""
    tfs = build_tfs(legs, adults=adults, nonstop=nonstop)
    return f"{BASE}?tfs={tfs}&tfu={TFU}&hl={lang}&curr={currency}"
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 -m pytest tests/test_gf_url.py -v`
Expected: PASS，8 passed（原 4 個 + 新增 4 個）

- [ ] **Step 5: 掃描器改為只查直飛**

在 `scripts/fare_scan.py` 中，把 `quick_scan` 與 `detail_scan` 內所有
`build_url(legs, currency="KRW")` 改為 `build_url(legs, currency="KRW", nonstop=True)`。
兩個函式各有兩處（`page.goto` 一處、回傳 dict 的 `url` 欄位一處），共四處。

改完確認：

Run: `grep -c 'nonstop=True' scripts/fare_scan.py`
Expected: `4`

- [ ] **Step 6: 實跑驗證**

Run: `python3 -u scripts/fare_scan.py --once`
Expected: `status : ok`，價格約 ￦1,770,000 上下，第一段 18:55–20:25 直達

- [ ] **Step 7: 舊資料改名保留，重新掃描**

既有 `~/four-leg-fares.json` 是不限轉機時掃的，語意已不同，必須重掃。
先改名保留（不要刪除，日後可比對限直飛前後的差異）：

```bash
mv ~/four-leg-fares.json ~/four-leg-fares-anystop-backup.json
```

- [ ] **Step 8: Commit**

```bash
git add scripts/gf_url.py scripts/fare_scan.py tests/test_gf_url.py
git commit -m "feat(fare): 掃描限定直飛航班

tfs 每段加 [5]=0 即 UI 的「僅顯示直達航班」，以真實網址逐字元驗證。
實測限直飛不會變貴也不會沒票（SEA 同價；VIE 同價、選項 4→2）。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 14: 前端改為四段日期條與聯動篩選

**Files:**
- Modify: `four-leg-fare.html`

使用者回饋：兩兩矩陣不直覺。改為一段一列、每天一格標「選這天的最低總價」，
點選後其他三列即時重算為「已選條件下的最低價」，對應實際的決策流程。
同時補上資料掃描時間（使用者問過「這是即時價格嗎」，畫面必須答得出來）。

- [ ] **Step 1: 改寫 four-leg-fare.html**

保留既有的檔案載入、Firebase 載入、卡片列表，新增日期條與篩選器。
把 `<body>` 內容整個替換為：

```html
<h1>四腿票比價</h1>
<div class="sub" id="meta">載入中…</div>

<div class="bar">
  <label>亞洲進 <select id="fIn"><option value="">全部</option></select></label>
  <label>亞洲出 <select id="fOut"><option value="">全部</option></select></label>
  <label>目的地 <select id="fDest"><option value="">全部</option></select></label>
  <label><input type="checkbox" id="fNonstop"> 只看四段全直飛</label>
  <button id="clear">清除選取</button>
  <label class="filebtn">載入本機檔案
    <input type="file" id="loadFile" accept=".json" hidden>
  </label>
  <button id="setup">設定資料庫</button>
</div>

<div id="grid"></div>
<div class="sub" id="picked"></div>
<div id="list"></div>

<script>
const LS_KEY = "fourLegFareDB";
const LEG_NAMES = ["腿1 亞洲→TPE", "腿2 TPE→長程", "腿3 長程→TPE", "腿4 TPE→亞洲"];
let RECORDS = [];
let sel = [null, null, null, null];   // 各段已選日期

function dbUrl(){ return localStorage.getItem(LS_KEY) || ""; }
function fmtTWD(n){ return n ? "NT$" + n.toLocaleString() : "—"; }
function fmtKRW(n){ return "￦" + n.toLocaleString(); }

// ---- 篩選（下拉與直飛勾選，與日期選取無關）----
function passFilters(r){
  const fi = fIn.value, fo = fOut.value, fd = fDest.value;
  if (fi && r.legs[0].from !== fi) return false;
  if (fo && r.legs[3].to !== fo) return false;
  if (fd && r.legs[1].to !== fd) return false;
  if (fNonstop.checked && r.allNonstop !== true) return false;
  return true;
}

// ---- 某段某日期，在「其他段已選條件」下的最低價 ----
function lowestFor(legIdx, date){
  let best = null;
  for (const r of RECORDS){
    if (!passFilters(r)) continue;
    if (r.legs[legIdx].date !== date) continue;
    let ok = true;
    for (let i = 0; i < 4; i++){
      if (i !== legIdx && sel[i] && r.legs[i].date !== sel[i]){ ok = false; break; }
    }
    if (!ok) continue;
    if (best === null || r.priceTWD < best) best = r.priceTWD;
  }
  return best;
}

function datesOf(legIdx){
  return [...new Set(RECORDS.filter(passFilters).map(r => r.legs[legIdx].date))].sort();
}

function renderGrid(){
  const rows = [];
  for (let i = 0; i < 4; i++){
    const dates = datesOf(i);
    if (!dates.length) continue;
    const prices = dates.map(d => lowestFor(i, d));
    const valid = prices.filter(p => p !== null);
    const lo = Math.min(...valid), hi = Math.max(...valid);
    const cells = dates.map((d, k) => {
      const p = prices[k];
      const isSel = sel[i] === d;
      const isBest = p !== null && p === lo;
      // 色階：最便宜偏綠、最貴偏紅
      let bg = "transparent";
      if (p !== null && hi > lo){
        const t = (p - lo) / (hi - lo);
        bg = `hsl(${Math.round(130 - 130 * t)}, 62%, ${92 - 6 * t}%)`;
      } else if (p !== null){ bg = "hsl(130,62%,92%)"; }
      return `<button class="cell${isSel ? " sel" : ""}${p === null ? " dead" : ""}"
        style="background:${bg}" data-leg="${i}" data-date="${d}">
        <span class="d">${d.slice(5)}</span>
        <span class="p">${p === null ? "—" : p.toLocaleString()}</span>
        ${isBest ? '<span class="star">★</span>' : ""}
      </button>`;
    }).join("");
    rows.push(`<div class="legrow"><div class="legname">${LEG_NAMES[i]}</div>
      <div class="cells">${cells}</div></div>`);
  }
  grid.innerHTML = rows.join("") || '<div class="empty">沒有資料</div>';
  grid.querySelectorAll(".cell").forEach(b => {
    b.onclick = () => {
      const i = +b.dataset.leg;
      sel[i] = (sel[i] === b.dataset.date) ? null : b.dataset.date;
      renderAll();
    };
  });
}

function matched(){
  return RECORDS.filter(r => passFilters(r) &&
    [0,1,2,3].every(i => !sel[i] || r.legs[i].date === sel[i]));
}

function renderPicked(){
  const rows = matched();
  if (!rows.length){ picked.textContent = "目前條件下沒有符合的組合"; return; }
  const lo = Math.min(...rows.map(r => r.priceTWD));
  const chosen = sel.map((d, i) => d ? d.slice(5) : "任選").join(" / ");
  picked.innerHTML = `目前選取：<b>${fmtTWD(lo)}</b>　${chosen}　（${rows.length} 組符合）`;
}

function renderList(){
  const rows = matched().sort((a,b) => a.priceTWD - b.priceTWD).slice(0, 40);
  const lo = rows.length ? rows[0].priceTWD : null;
  list.innerHTML = rows.map(r => card(r, r.priceTWD === lo)).join("")
    || '<div class="empty">沒有符合條件的組合</div>';
}

function card(r, isBest){
  const legs = r.legs.map(l => {
    const known = l.depart && l.arrive;
    const time = known
      ? `${l.depart} – ${l.arrive}${l.arrivePlusDays ? "<sup>+" + l.arrivePlusDays + "</sup>" : ""}`
      : "時刻待補";
    let tag;
    if (l.nonstop === true) tag = '<span class="tag nonstop">直飛</span>';
    else if (l.nonstop === false) tag = `<span class="tag via">經 ${l.via || "轉機"}</span>`;
    else tag = '<span class="tag unknown">未知</span>';
    return `<div class="leg"><span class="route">${l.from}→${l.to}</span>
      <span class="time${known ? "" : " pending"}">${l.date}　${time}</span>${tag}</div>`;
  }).join("");
  return `<div class="card${isBest ? " best" : ""}">
    <div class="price">${fmtTWD(r.priceTWD)}<small>${fmtKRW(r.priceKRW)}</small></div>
    <div class="legs">${legs}</div>
    <div class="links">
      <a href="${r.url || "https://www.google.com/travel/flights"}" target="_blank" rel="noopener">Google Flights 複查（即時價）</a>
      <a href="https://www.evaair.com/zh-tw/index.html" target="_blank" rel="noopener">長榮訂票</a>
    </div></div>`;
}

function buildFilters(){
  const fill = (el, vals) => {
    const cur = el.value;
    el.innerHTML = '<option value="">全部</option>' +
      vals.map(v => `<option value="${v}">${v}</option>`).join("");
    if (vals.includes(cur)) el.value = cur;
  };
  fill(fIn,   [...new Set(RECORDS.map(r => r.legs[0].from))].sort());
  fill(fOut,  [...new Set(RECORDS.map(r => r.legs[3].to))].sort());
  fill(fDest, [...new Set(RECORDS.map(r => r.legs[1].to))].sort());
}

function renderMeta(){
  if (!RECORDS.length){ meta.textContent = "沒有資料"; return; }
  const times = RECORDS.map(r => r.scannedAt).filter(Boolean).sort();
  const fx = RECORDS.find(r => r.fxRate);
  const when = times.length
    ? new Date(times[times.length - 1]).toLocaleString("zh-TW",
        {month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit"})
    : "未知";
  const nsCount = RECORDS.filter(r => r.allNonstop === true).length;
  meta.innerHTML = `${RECORDS.length} 組　最後掃描 ${when}` +
    `${fx ? `　匯率 ${fx.fxRate}` : ""}　` +
    `<span class="warn">價格為掃描當下的快照，非即時；要看即時價請點卡片的「Google Flights 複查」</span>` +
    `${nsCount < RECORDS.length ? `<br><span class="warn">僅 ${nsCount} 組已確認四段全直飛（其餘尚未詳掃）</span>` : ""}`;
}

function renderAll(){ buildFilters(); renderGrid(); renderPicked(); renderList(); renderMeta(); }

function ingest(data){
  RECORDS = Object.entries(data).map(([id, v]) => ({id, ...v}))
    .filter(v => v.status === "ok" && v.priceKRW);
  sel = [null, null, null, null];
  renderAll();
}

loadFile.onchange = async (ev) => {
  const f = ev.target.files[0];
  if (!f) return;
  try { ingest(JSON.parse(await f.text())); }
  catch (e){ meta.textContent = "檔案讀取失敗：" + e.message; }
};

[fIn, fOut, fDest, fNonstop].forEach(el => el.onchange = renderAll);
clear.onclick = () => { sel = [null,null,null,null]; renderAll(); };
setup.onclick = () => {
  const v = prompt("Firebase Realtime Database 網址", dbUrl());
  if (v !== null){ localStorage.setItem(LS_KEY, v.trim().replace(/\/$/,"")); load(); }
};

async function load(){
  const base = dbUrl();
  if (!base){
    meta.textContent = "尚未載入資料";
    list.innerHTML = '<div class="empty">點「載入本機檔案」選擇 ~/four-leg-fares.json<br>' +
      '或點「設定資料庫」填入 Firebase 網址</div>';
    return;
  }
  try {
    const r = await fetch(base + "/fares.json");
    ingest(await r.json() || {});
  } catch (e){ meta.textContent = "讀取失敗：" + e.message; }
}
load();
</script>
```

- [ ] **Step 2: 補上日期條所需樣式**

在 `<style>` 內追加：

```css
  .bar label{font-size:14px;color:var(--muted);display:flex;align-items:center;gap:6px}
  .warn{color:#b06000;font-size:13px}
  .legrow{background:var(--card);border:1px solid var(--line);border-radius:10px;
    padding:10px 12px;margin-bottom:8px}
  .legname{font-size:13px;color:var(--muted);margin-bottom:6px}
  .cells{display:flex;gap:6px;flex-wrap:wrap}
  .cell{display:flex;flex-direction:column;align-items:center;gap:2px;
    border:1px solid var(--line);border-radius:8px;padding:8px 12px;cursor:pointer;
    font-family:inherit;position:relative;min-width:78px}
  .cell .d{font-size:13px;color:var(--muted)}
  .cell .p{font-size:15px;font-weight:600;color:var(--ink)}
  .cell.sel{border-color:var(--accent);border-width:2px;box-shadow:0 0 0 2px #1a73e822}
  .cell.dead{opacity:.35;cursor:default}
  .cell .star{position:absolute;top:2px;right:4px;font-size:10px;color:var(--best)}
  #picked{margin:10px 0 16px;font-size:15px}
```

- [ ] **Step 3: 用 Playwright 驗證**

寫一段暫存的 Playwright 腳本（放系統暫存目錄，不要留在 repo），開啟頁面、
用 `set_input_files` 載入 `~/four-leg-fares.json`，然後驗證：

1. 四列日期條都出現，格子數與各段日期數相符
2. 點擊腿3 的某一天後，腿2 的價格數字**有變化**（證明聯動生效）
3. 再點同一格會取消選取
4. `#meta` 含「最後掃描」與「非即時」字樣
5. 主控台無 JS 錯誤

- [ ] **Step 4: Commit**

```bash
git add four-leg-fare.html
git commit -m "feat(fare): 前端改為四段日期條與聯動篩選

一段一列、每天標最低總價，點選後其他段即時重算，取代兩兩矩陣。
補上掃描時間與「非即時」提示，並加入亞洲進出、目的地、全直飛篩選。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-Review 檢查結果

**Spec 覆蓋**：

| Spec 要求 | 對應任務 |
|---|---|
| tfs URL 構造 | Task 1 |
| 全形 ￦ 價格解析 | Task 3 |
| 起降時刻、直飛狀態、轉機點 | Task 2、3、9 |
| 台幣自動換算 | Task 5、8 |
| Phase 1 韓國進出 × VIE/MXP 864 組 | Task 4、12 |
| 兩段式掃描（快掃／詳掃） | Task 7、9 |
| 節流與並行控制 | Task 8 |
| 斷點續跑 | Task 6、8 |
| 格式失效偵測 | Task 8（連續 15 組空白即中止）|
| Firebase 只 PATCH 子節點 | Task 6 |
| 憑證不進版控 | Task 6（環境變數／家目錄設定檔）|
| 前端比價表、排序、篩選 | Task 10 |
| 台幣為主韓元為輔顯示 | Task 10 |
| 快掃未補時刻需視覺區分 | Task 10（`.time.pending` 淡灰）|
| 外連 GF 複查／長榮訂票 | Task 10、11 |

**未納入本計畫的 spec 項目**（刻意延後，非遺漏）：

- **價格歷史折線**：spec 的 `/fares/<id>/history/<ts>` 與前端趨勢圖。Phase 1 是首次掃描，尚無歷史資料可畫。待有第二次掃描後再實作，屆時另開計畫。
- **V 艙手動標記**：spec 的 `/vclass` 節點與前端打勾。需先有 Phase 1 結果才知道要標哪幾組，且此功能不影響掃描正確性。
- **Phase 2／Phase 3**：擴大範圍只需改 `fare_combos.py` 的設定字典，無新程式碼，待 Phase 1 驗證速率限制後再執行。

**型別一致性**：`combo_id` 在 Task 4 定義、Task 6／8 使用；`parse_row` 回傳欄位（snake_case）在 Task 3 定義，Task 7／9 轉成 Firebase 的 camelCase 欄位，兩者命名邊界在 `quick_scan`／`detail_scan` 內完成轉換，前端只接觸 camelCase。`read_rows` 在 Task 7 定義、Task 9 重用。
