# 年度統計 — 支出頁類別分佈圓環 + 收入頁年度結餘

## 背景

`finance-app/index.html` 目前支出頁、收入頁都只提供「當月」視角：
- 支出頁有「本月支出＋類別分佈圓環圖」（`cat-chart`）
- 收入頁有「本月結餘」卡片（收入／支出／結餘三行）

使用者想在兩個頁面各加一個「年度」視角的統計，看整年花在各類別多少錢、整年收支結餘多少。

## 後端變更

新增一支 API：

```
GET /finance/summary/year/{year}
```

`year` 格式 `YYYY`（如 `2026`）。回傳格式與現有 `GET /finance/summary/{year_month}` 一致：

```json
{
  "year": "2026",
  "total_expense": 123456,
  "total_income": 234567,
  "balance": 111111,
  "by_category": {"日常": 12345, "房租": 60000, ...},
  "transaction_count": 42
}
```

實作（`finance_db.py`）：新增 `yearly_summary(year: str)`，比照 `monthly_summary()`，差異在於：

- `list_transactions` 的 `date LIKE :ym` 本來就用前綴比對，`year_month` 傳 `"2026"` 即可直接沿用（`LIKE '2026%'`），**不需修改**。
- `list_income` 目前是 `WHERE year_month = :ym` 精確比對，需新增一個前綴比對的查詢路徑（例如新增參數 `prefix: bool = False`，或另開一個 `list_income_by_year(year)` 函式，內部用 `WHERE year_month LIKE :y`）。選擇新增獨立函式 `list_income_by_year`，不動原本 `list_income` 的行為，避免影響既有呼叫方。

`finance_api.py` 新增路由：

```python
@router.get("/summary/year/{year}")
def get_yearly_summary(year: str, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return db.yearly_summary(year)
```

## 前端變更

### 共用：年份下拉選單

新增 `buildYears(id)` 函式，仿照現有 `buildMonths(id)`：產生近 5 年（今年含以前 4 年）的選項，`value` 為 `YYYY`。支出頁、收入頁的年度卡片**各自**用獨立的 `<select>`（`sel-exp-year`、`sel-inc-year`），選中狀態互不影響。

### 支出頁（`page-expenses`）

在既有「類別分佈」卡片（月度 `cat-chart`）下方、`tx-list` 交易清單上方，新增一張卡片：

```html
<div class="card">
  <div class="month-row" style="margin-bottom:8px">
    <select id="sel-exp-year" onchange="loadYearlyExpense()"></select>
  </div>
  <div class="label">年度支出</div>
  <div class="big red" id="exp-year-total">--</div>
  <div class="chart-wrap" style="height:200px;margin-top:8px"><canvas id="cat-chart-year"></canvas></div>
  <div id="cat-legend-year" style="margin-top:12px"></div>
</div>
```

新增 `loadYearlyExpense()`：呼叫 `/finance/summary/year/{year}`，用回傳的 `total_expense`、`by_category` 渲染。圓環圖與 legend 的渲染邏輯直接複用 `renderExpenses()` 裡已有的 `CAT_COLORS` 對照表與 HTML legend 樣式（抽成共用函式 `renderCategoryChart(canvasId, legendId, chartVarRef, catMap)`，讓月度 `cat-chart` 與年度 `cat-chart-year` 共用同一份渲染邏輯，避免複製貼上兩份幾乎一樣的程式碼）。

`go('expenses')` 切換到支出頁時，若年度下拉選單尚未初始化則呼叫 `buildYears('sel-exp-year')` 並觸發一次 `loadYearlyExpense()`。

### 收入頁（`page-income`）

在既有「本月結餘」卡片（`balance-card`）下方，新增一張「年度結餘」卡片，結構比照月度版本：

```html
<div class="card" id="balance-card-year">
  <div class="month-row" style="margin-bottom:8px">
    <select id="sel-inc-year" onchange="loadYearlyBalance()"></select>
  </div>
  <div class="label">年度結餘</div>
  <div style="display:flex;justify-content:space-between;align-items:center;margin:10px 0 6px">
    <span style="font-size:13px;color:#64748b">年度收入</span>
    <span style="font-size:15px;font-weight:700;color:#4ade80" id="bal-year-income">--</span>
  </div>
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <span style="font-size:13px;color:#64748b">年度支出</span>
    <span style="font-size:15px;font-weight:700;color:#f87171" id="bal-year-expense">--</span>
  </div>
  <div style="border-top:1px solid #334155;margin:8px 0"></div>
  <div style="display:flex;justify-content:space-between;align-items:center">
    <span style="font-size:14px;font-weight:600">年度結餘</span>
    <span style="font-size:22px;font-weight:800" id="bal-year-net">--</span>
  </div>
</div>
```

新增 `loadYearlyBalance()`：呼叫 `/finance/summary/year/{year}`，用 `total_income`、`total_expense`、`balance` 填入對應欄位（`bal-year-net` 依正負套用綠/紅色，比照月度版本邏輯）。

`go('income')` 切換到收入頁時，若年度下拉選單尚未初始化則呼叫 `buildYears('sel-inc-year')` 並觸發一次 `loadYearlyBalance()`。

## 資料流程

1. 使用者切到支出／收入頁 → 若年度選單未初始化，建立選單（預設選今年）並打年度 API
2. 使用者切換年度下拉選單 → 重新打 `/finance/summary/year/{year}` → 重繪對應卡片
3. 月度視角（既有邏輯）完全不受影響，兩者互相獨立

## 錯誤處理

`loadYearlyExpense()` / `loadYearlyBalance()` 各自包在自己的 `try/catch`，失敗時 `console.error` 並讓對應卡片維持 `--`，不影響頁面其他既有區塊（吸取先前資產頁「一個 API 失敗導致整頁空白」的教訓，年度卡片與既有月度卡片渲染邏輯互不阻斷）。

## 部署

- 後端改動需 push 到 `Jennawang123/jenna-finance` repo（Render 實際部署來源，非本 monorepo 的 `finance-server/`，需比照先前流程手動同步）
- 前端改動 push 到本 monorepo `main` 分支即可，Netlify 已設定自動部署
