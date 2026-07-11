# 統計分頁模式下拉選單 — 設計文件

日期：2026-07-11
狀態：待實作

## 背景

「統計」分頁目前只有「歷年儲蓄率」一張卡片（見 `docs/superpowers/specs/2026-07-11-yearly-savings-rate-tab-design.md`）。這次要在卡片上加一個下拉選單，讓用戶切換顯示「儲蓄率／收入／支出」三種歷年比較內容。

## 範圍

**這次要做的**：在既有「統計」分頁的卡片加下拉選單，切換三種歷年比較內容（前端渲染邏輯，不新增後端 API）。

**不做的**：月度細節、跨年趨勢折線圖、收入來源分類（`income.source` 目前是自由文字，沒有固定分類，不在此次範圍內新增）。

## 1. 資料串接

`/finance/summary/years`（既有 endpoint，見 yearly-savings-rate-tab 那份 spec）回傳的每筆資料已經包含 `year`、`total_income`、`total_expense`、`balance`、`by_category`，三種模式共用同一份資料，不需要新增或修改後端 API。

**前端資料流程調整**：
- `loadStats()` 只在切進「統計」分頁時 fetch 一次，結果存進模組層級變數 `statsYearsData`
- 新增 `renderStatsMode()`，讀取 `#stats-mode` 下拉選單目前的值，用 `statsYearsData` 渲染對應內容到 `#stats-years-list`
- 下拉選單 `onchange` 只呼叫 `renderStatsMode()`，不重新呼叫 API
- 每次重新進入「統計」分頁（`go('stats')`）都重新 `loadStats()`，下拉選單狀態不記憶，預設回「儲蓄率」

## 2. UI

**下拉選單**：在既有卡片內、標籤旁加一個原生 `<select id="stats-mode">`：

```html
<select id="stats-mode" onchange="renderStatsMode()">
  <option value="rate">儲蓄率</option>
  <option value="income">收入</option>
  <option value="expense">支出</option>
</select>
```

卡片的 `.label` 文字依模式動態切換（「歷年儲蓄率」／「歷年收入」／「歷年支出」）。

**三種模式內容**（`#stats-years-list` 依模式渲染不同 HTML，年份仍由舊到新排列，含「本年」標籤）：

| 模式 | 每年顯示 | 歷年平均 |
|---|---|---|
| 儲蓄率 | 儲蓄率百分比＋0~100%固定比例尺綠色進度條＋收入/支出金額（維持現有實作不變） | 各年儲蓄率算術平均 |
| 收入 | 當年總收入金額（純文字，不畫進度條） | 各年收入算術平均 |
| 支出 | 當年總支出金額（純文字，不畫進度條）＋該年類別分解圓餅圖 | 各年支出算術平均 |

金額模式（收入／支出）不畫進度條，因為金額沒有像儲蓄率那樣自然的 0~100% 上限，avoid 誤導性的相對比例尺。

**支出模式圓餅圖**：重用既有 `renderCategoryChart(canvasId, legendId, chartVar, catMap)` 函式（`finance-app/index.html` 既有邏輯，`支出`分頁年度圓餅圖用的同一套）。每個年份要有獨立的 canvas/legend DOM id（例如 `stats-cat-chart-${year}` / `stats-cat-legend-${year}`）與獨立的 Chart.js 實例，用一個以年份為 key 的物件 `statsCatCharts = {}` 管理：

```javascript
function statsCatChartRef(year) {
  return {
    get chart(){ return statsCatCharts[year]; },
    set chart(v){ statsCatCharts[year] = v; }
  };
}
```

`renderStatsMode()` 切到支出模式時，要先把 HTML（含所有年份的 canvas/legend 容器）插入 DOM，再逐年呼叫 `renderCategoryChart(...)`（Chart.js 需要 canvas 已存在於 DOM 才能繪製）。若同一年份的 chart 實例已存在（例如使用者切走又切回支出模式），`renderCategoryChart` 內建的 `if(chartVar.chart) chartVar.chart.destroy()` 會先銷毀舊實例再重畫，避免疊圖或記憶體洩漏。

## 3. 邊界情況

| 情況 | 處理方式 |
|---|---|
| `statsYearsData` 為空陣列 | 三種模式都顯示「尚無資料」，不顯示下拉選單以外的內容（沿用現有空狀態文字） |
| 使用者切換模式又切回 | 不重新 fetch，直接用已存的 `statsYearsData` 重新渲染；支出模式的圓餅圖走 destroy-before-redraw |
| 離開「統計」分頁再進來 | `go('stats')` 重新呼叫 `loadStats()`，重新 fetch 一次，下拉選單重置回「儲蓄率」 |

## 4. 測試計畫

無後端變更，純前端。用 Playwright：
1. 用既有測試資料（3 個年度，沿用歷年儲蓄率驗證時建立的資料）打開「統計」分頁
2. 確認預設顯示「儲蓄率」模式，內容跟現況一致
3. 切到「收入」，確認每年顯示正確總收入金額、無進度條、歷年平均收入正確
4. 切到「支出」，確認每年顯示正確總支出金額、下方有該年類別圓餅圖，圖表類別比例跟 App 既有「支出」分頁的年度圓餅圖一致
5. 來回切換三種模式兩次，確認圓餅圖沒有疊圖或殘留（destroy-before-redraw 生效）
