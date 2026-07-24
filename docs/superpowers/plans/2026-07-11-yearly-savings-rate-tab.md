# 歷年儲蓄率比較分頁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一個「統計」分頁，顯示歷年儲蓄率比較卡片（年份、儲蓄率、進度條、收支金額、歷年平均）。

**Architecture:** 後端在 `finance-server/finance_db.py` 新增 `years_with_data()` / `yearly_summaries()`，`finance_api.py` 新增 `GET /finance/summary/years` route（必須註冊在既有 `/summary/{year_month}` 之前，否則會被該動態路由攔截）。前端在 `finance-app/index.html` 單檔內新增第 5 個分頁（tab button + page + JS render function），沿用既有卡片樣式與 `go()` tab 切換 pattern。

**Tech Stack:** FastAPI + SQLAlchemy + SQLite/Postgres（後端）、原生 JS + Chart.js（前端，本次功能不需要圖表）、pytest + httpx（後端測試）。

**Spec:** `docs/superpowers/specs/2026-07-11-yearly-savings-rate-tab-design.md`

---

### Task 1: 後端 — `finance_db.py` 新增年度彙總函式

**Files:**
- Modify: `finance-server/finance_db.py:247`（`yearly_summary()` 函式結束後插入新函式）
- Test: `finance-server/tests/conftest.py`（新建）
- Test: `finance-server/tests/test_summary_years.py`（新建）

- [ ] **Step 1: 建立 pytest 可以找到 `finance_db` 模組的 conftest，並提供獨立資料庫的 fixture**

建立 `finance-server/tests/conftest.py`：

```python
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def finance_db(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sys.modules.pop("finance_db", None)
    import finance_db as db
    db.init_db()
    return db
```

這個 fixture 讓每個測試都拿到一個指向全新暫存 SQLite 檔案的 `finance_db` 模組（透過 `DATA_DIR` 環境變數 + 清掉 `sys.modules` 快取強制重新 import，因為 `finance_db.py` 在 import 當下就用環境變數建立 `engine`）。

- [ ] **Step 2: 寫會失敗的測試——驗證零收入年份被排除、年份由舊到新排序**

建立 `finance-server/tests/test_summary_years.py`：

```python
def test_years_with_data_excludes_zero_income_years(finance_db):
    db = finance_db
    db.insert_transaction({
        "date": "2023-05-10", "merchant": "test", "amount": 1000,
        "currency": "TWD", "category": "日常", "bank": "test",
        "card_last4": "", "note": "", "is_travel": 0,
    })
    db.upsert_income("2024-01", "薪資", 50000, "")
    db.insert_transaction({
        "date": "2024-01-10", "merchant": "test", "amount": 2000,
        "currency": "TWD", "category": "日常", "bank": "test",
        "card_last4": "", "note": "", "is_travel": 0,
    })

    summaries = db.yearly_summaries()

    years = [s["year"] for s in summaries]
    assert years == ["2024"]


def test_yearly_summaries_sorted_ascending(finance_db):
    db = finance_db
    for ym, amt in [("2022-06", 100000), ("2024-06", 200000), ("2023-06", 150000)]:
        db.upsert_income(ym, "薪資", amt, "")

    summaries = db.yearly_summaries()

    assert [s["year"] for s in summaries] == ["2022", "2023", "2024"]
    assert summaries[0]["total_income"] == 100000
    assert summaries[1]["total_income"] == 150000
    assert summaries[2]["total_income"] == 200000
```

- [ ] **Step 3: 執行測試，確認因為函式不存在而失敗**

Run: `cd finance-server && python3 -m pytest tests/test_summary_years.py -v`
Expected: FAIL，錯誤訊息包含 `AttributeError: module 'finance_db' has no attribute 'yearly_summaries'`

- [ ] **Step 4: 實作 `years_with_data()` 與 `yearly_summaries()`**

在 `finance-server/finance_db.py` 第 247 行（`yearly_summary()` 函式結尾、`# ── Income ──` 註解之前）插入：

```python
def years_with_data() -> list:
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT DISTINCT substr(date,1,4) AS y FROM transactions "
            "UNION "
            "SELECT DISTINCT substr(year_month,1,4) AS y FROM income "
            "ORDER BY y"
        ))
        return [r[0] for r in result]


def yearly_summaries() -> list:
    summaries = []
    for year in years_with_data():
        s = yearly_summary(year)
        if s["total_income"] > 0:
            summaries.append(s)
    return summaries
```

`years_with_data()` 用 `UNION` 取 `transactions.date` 與 `income.year_month` 兩邊出現過的年份聯集，`substr` 在 SQLite 跟 Postgres 都通用，不用像其他函式一樣分 `IS_PG` 兩套 SQL。`yearly_summaries()` 沿用既有 `yearly_summary(year)` 邏輯逐年計算，並過濾掉 `total_income == 0` 的年份。

- [ ] **Step 5: 執行測試，確認通過**

Run: `cd finance-server && python3 -m pytest tests/test_summary_years.py -v`
Expected: PASS（2 passed）

- [ ] **Step 6: Commit**

```bash
cd finance-server
git add finance_db.py tests/conftest.py tests/test_summary_years.py
git commit -m "feat: add yearly_summaries() for cross-year savings rate comparison"
```

**注意：`finance-server/` 是獨立 git repo（origin 指向 `jenna-finance`），這個 commit 要在 `finance-server/` 目錄內執行，push 到它自己的 repo 才會觸發 Render 部署，push monorepo 不會生效。**

---

### Task 2: 後端 — 新增 `GET /finance/summary/years` route

**Files:**
- Modify: `finance-server/finance_api.py:103`（在既有 `/summary/{year_month}` route 之前插入新 route）
- Modify: `finance-server/requirements.txt`（新增 `pytest`、`httpx` 供測試使用）
- Test: `finance-server/tests/test_summary_years_api.py`（新建）

- [ ] **Step 1: 在 requirements.txt 加入測試依賴**

修改 `finance-server/requirements.txt`，在檔案末尾加入：

```
pytest
httpx
```

- [ ] **Step 2: 寫會失敗的測試——驗證新 route 沒有被既有的 `/summary/{year_month}` 動態路由攔截**

建立 `finance-server/tests/test_summary_years_api.py`：

```python
import sys


def _fresh_app(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for mod in ("main", "finance_api", "finance_db"):
        sys.modules.pop(mod, None)
    import main
    return main.app


def test_summary_years_route_not_shadowed(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    app = _fresh_app(tmp_path, monkeypatch)
    client = TestClient(app)

    import finance_db as db
    db.upsert_income("2024-01", "薪資", 50000, "")

    resp = client.get("/finance/summary/years")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["year"] == "2024"
    assert body[0]["total_income"] == 50000
```

這個測試特別針對「路由順序」這個坑：`/finance/summary/years` 跟既有的 `/finance/summary/{year_month}` 都是兩段路徑，如果新 route 註冊在舊 route 之後，FastAPI 會先用 `year_month="years"` 去匹配舊的 `get_summary`，回傳的會是月度摘要格式（沒有 `total_income` 意義正確的清單），這個測試會因為 `body` 不是 list 而失敗，藉此守住正確的註冊順序。

- [ ] **Step 3: 執行測試，確認因為 404 或格式不符而失敗**

Run: `cd finance-server && python3 -m pytest tests/test_summary_years_api.py -v`
Expected: FAIL（`assert isinstance(body, list)` 失敗，因為 route 還不存在，會被 `/summary/{year_month}` 攔截並回傳月度摘要 dict，或是 404）

- [ ] **Step 4: 實作 route，並確保註冊順序在 `/summary/{year_month}` 之前**

在 `finance-server/finance_api.py` 第 103 行（`@router.get("/summary/{year_month}")` 之前）插入：

```python
@router.get("/summary/years")
def get_yearly_summaries(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return db.yearly_summaries()


```

插入後確認原本的 `/summary/{year_month}` 與 `/summary/year/{year}` 兩個 route 維持在它後面，不要刪除或調換。

- [ ] **Step 5: 執行測試，確認通過**

Run: `cd finance-server && python3 -m pytest tests/ -v`
Expected: PASS（3 passed，含 Task 1 的兩個測試）

- [ ] **Step 6: 用 curl 手動確認本地啟動的 server 也正常回應**

Run:
```bash
cd finance-server
DATA_DIR=/tmp/finance-manual-check uvicorn main:app --port 8010 &
sleep 2
curl -s http://localhost:8010/finance/summary/years
kill %1
```
Expected: 回傳 `[]`（乾淨的暫存資料庫沒有資料，回傳空陣列，不會是 404 或錯誤格式）

- [ ] **Step 7: Commit**

```bash
cd finance-server
git add finance_api.py requirements.txt tests/test_summary_years_api.py
git commit -m "feat: expose GET /finance/summary/years endpoint"
git push origin main
```

**同 Task 1 的提醒：這個 commit 要 push 到 `finance-server/` 自己的 repo（`jenna-finance`），Render 才會抓到新版本部署。push 前跟用戶確認一次。**

---

### Task 3: 前端 — 新增「統計」分頁骨架

**Files:**
- Modify: `finance-app/index.html:179`（tab bar 加第 5 個按鈕）
- Modify: `finance-app/index.html:431`（TAB 4 資產 `</div>` 後、MODALS 註解前插入新分頁 `<div>`）
- Modify: `finance-app/index.html:654`（`TABS` 陣列加入 `'stats'`）

- [ ] **Step 1: 在 tab bar 加入第 5 個分頁按鈕**

在 `finance-app/index.html` 第 179 行（`<button class="tab" onclick="go('assets')">🏦 資產</button>` 之後）插入：

```html
  <button class="tab" onclick="go('stats')">📊 統計</button>
```

- [ ] **Step 2: 在 TAB 4 資產區塊結束後插入新的統計分頁容器**

在 `finance-app/index.html` 第 431 行（資產分頁的 `</div>`，緊接在 `⚙️ API 設定` 按鈕的 `</div>` 之後，`<!-- ══════════════ MODALS ══════════════ -->` 之前）插入：

```html
<!-- ══════════════ TAB 5: 統計 ══════════════ -->
<div id="page-stats" class="page">
  <div class="card">
    <div class="label">歷年儲蓄率</div>
    <div id="stats-years-list"><div class="empty">尚無資料</div></div>
  </div>
</div>
```

- [ ] **Step 3: 把 `stats` 加進 `TABS` 陣列**

修改 `finance-app/index.html:654`：

```javascript
const TABS=['expenses','income','investment','assets','stats'];
```

- [ ] **Step 4: 用瀏覽器確認分頁能切換（尚未接資料，先確認骨架正確）**

用 Playwright 開啟本地檔案（或本地靜態伺服器）下的 `finance-app/index.html`，點擊新的「📊 統計」分頁按鈕，確認：
- 按鈕會被標記為 `on`（跟其他分頁切換時的高亮效果一致）
- 頁面切到顯示「歷年儲蓄率」卡片、內容是「尚無資料」

- [ ] **Step 5: Commit**

```bash
git add finance-app/index.html
git commit -m "feat: add empty 統計 tab shell with 歷年儲蓄率 card"
```

---

### Task 4: 前端 — 串接 API、渲染歷年儲蓄率列表

**Files:**
- Modify: `finance-app/index.html:656-666`（`go()` 函式，新增 `stats` 分支）
- Modify: `finance-app/index.html`（在既有 `loadYearlyBalance()` 附近新增 `loadStats()` 函式）

- [ ] **Step 1: 在 `go()` 裡把最後的 `else loadAssets();` 拆成明確的 `assets`／`stats` 兩支**

`finance-app/index.html:662-665` 目前是：

```javascript
  if(tab==='expenses'){ loadExpenses(); loadYearlyExpense(); }
  else if(tab==='income'){ loadIncome(); loadYearlyBalance(); }
  else if(tab==='investment') loadInvestment();
  else loadAssets();
```

改成：

```javascript
  if(tab==='expenses'){ loadExpenses(); loadYearlyExpense(); }
  else if(tab==='income'){ loadIncome(); loadYearlyBalance(); }
  else if(tab==='investment') loadInvestment();
  else if(tab==='assets') loadAssets();
  else loadStats();
```

- [ ] **Step 2: 新增 `loadStats()` 函式**

在 `finance-app/index.html` 裡 `loadYearlyBalance()` 函式（目前在 `finance-server` 對應行是第 958-978 行附近）後面加入：

```javascript
async function loadStats() {
  if(!API) return;
  try {
    const years = await api('/finance/summary/years');
    const listEl = document.getElementById('stats-years-list');
    if(!years.length){ listEl.innerHTML='<div class="empty">尚無資料</div>'; return; }
    const nowYear = String(new Date().getFullYear());
    let rows='', rateSum=0;
    years.forEach(y=>{
      const rate = y.total_income>0 ? (y.balance/y.total_income*100) : 0;
      rateSum += rate;
      const color = rate>=0?'#4ade80':'#f87171';
      const barWidth = Math.max(0, Math.min(rate, 100));
      const tag = y.year===nowYear ? ' <span class="badge" style="margin-left:6px;cursor:default">本年</span>' : '';
      rows += `
        <div style="margin-bottom:18px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <span style="font-size:15px;font-weight:700">${y.year}年${tag}</span>
            <span style="font-size:16px;font-weight:800;color:${color}">${rate>=0?'+':''}${rate.toFixed(1)}%</span>
          </div>
          <div style="background:#0f172a;border-radius:6px;height:8px;overflow:hidden;margin-bottom:6px">
            <div style="height:100%;background:#4ade80;width:${barWidth}%;border-radius:6px"></div>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:12px;color:#64748b">
            <span>收入 NT$${y.total_income.toLocaleString()}</span>
            <span>支出 NT$${y.total_expense.toLocaleString()}</span>
          </div>
        </div>`;
    });
    const avg = rateSum/years.length;
    rows += `
      <div style="border-top:1px solid #334155;padding-top:10px;display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:14px;font-weight:600">歷年平均</span>
        <span style="font-size:16px;font-weight:800;color:${avg>=0?'#4ade80':'#f87171'}">${avg>=0?'+':''}${avg.toFixed(1)}%</span>
      </div>`;
    listEl.innerHTML = rows;
  } catch(e){ console.error(e); }
}
```

年份資料由後端保證舊到新排序，前端不用再排序。`barWidth` 用 `Math.max(0, Math.min(rate,100))` 實現「0%~100% 固定滿版基準，超過截斷、負值不畫條」的規則；`歷年平均` 用 `rateSum/years.length` 做算術平均，含本年一起算。

- [ ] **Step 3: 起本地後端，寫入至少 3 年測試資料，手動驗證畫面**

Run:
```bash
cd finance-server
DATA_DIR=/tmp/finance-manual-check2 uvicorn main:app --port 8010 &
sleep 2
curl -s -X POST http://localhost:8010/finance/income -H "Content-Type: application/json" -d '{"year_month":"2024-06","source":"薪資","amount":1000000,"note":""}'
curl -s -X POST http://localhost:8010/finance/income -H "Content-Type: application/json" -d '{"year_month":"2025-06","source":"薪資","amount":1200000,"note":""}'
curl -s -X POST http://localhost:8010/finance/income -H "Content-Type: application/json" -d '{"year_month":"2026-06","source":"薪資","amount":800000,"note":""}'
curl -s -X POST http://localhost:8010/finance/transactions -H "Content-Type: application/json" -d '{"date":"2024-06-01","merchant":"test","amount":300000,"currency":"TWD","category":"日常","bank":"test","card_last4":"","note":"","is_travel":0}'
curl -s -X POST http://localhost:8010/finance/transactions -H "Content-Type: application/json" -d '{"date":"2025-06-01","merchant":"test","amount":400000,"currency":"TWD","category":"日常","bank":"test","card_last4":"","note":"","is_travel":0}'
curl -s -X POST http://localhost:8010/finance/transactions -H "Content-Type: application/json" -d '{"date":"2026-06-01","merchant":"test","amount":500000,"currency":"TWD","category":"日常","bank":"test","card_last4":"","note":"","is_travel":0}'
curl -s http://localhost:8010/finance/summary/years
```

用 Playwright：
1. 開啟 `finance-app/index.html`（本地靜態伺服器，例如 `python3 -m http.server` 在 `finance-app/` 目錄下）
2. 在「⚙️ API 設定」把 API URL 設成 `http://localhost:8010`
3. 點「📊 統計」分頁
4. 截圖確認：三個年度（2024/2025/2026）由舊到新排列、2026 有「本年」標籤、綠色進度條長度反映各年儲蓄率（2024: 70%、2025: 約66.7%、2026: 37.5%）、收入/支出金額正確、底部「歷年平均」約 58%

執行完後：

```bash
kill %1
```

- [ ] **Step 4: Commit**

```bash
git add finance-app/index.html
git commit -m "feat: render yearly savings rate comparison in 統計 tab"
```

---

### Task 5: 部署確認

**Files:** 無程式變更，純部署與跨 repo 確認

- [ ] **Step 1: 確認 Task 1、2 的 commit 已經 push 到 `finance-server/` 自己的 repo（`jenna-finance`），而不是只 push 到 monorepo**

Run: `cd finance-server && git log origin/main..HEAD --oneline`
Expected: 空輸出（代表本地 commit 都已經 push，Render 會抓到新版本）

- [ ] **Step 2: 確認 Task 3、4 的 monorepo commit 已經 push，讓 Netlify CD 觸發前端部署**

Run: `git log origin/main..HEAD --oneline`（在 monorepo 根目錄）
Expected: 空輸出

- [ ] **Step 3: 等 Render 重新部署完成後，用 curl 打正式環境驗證新 endpoint**

Run: `curl -s -H "x-api-key: <使用者的 API key>" https://jenna-finance.onrender.com/finance/summary/years`
Expected: 回傳實際歷史資料的年度陣列（非空、格式跟本地測試一致）

- [ ] **Step 4: 打開正式 Netlify 網址，切到「統計」分頁，確認正式資料正確顯示**

用 Playwright 開啟 `https://incandescent-mooncake-3de7e3.netlify.app`，切到「📊 統計」分頁，截圖確認實際歷史資料（2022~2026）都正確列出、本年標籤在 2026、數字跟後端 `/finance/summary/years` 回傳一致。
