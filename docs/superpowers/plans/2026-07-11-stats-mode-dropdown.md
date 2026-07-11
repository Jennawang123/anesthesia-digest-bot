# 統計分頁模式下拉選單 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在「統計」分頁的「歷年儲蓄率」卡片加一個下拉選單，切換「儲蓄率／收入／支出」三種歷年比較內容。

**Architecture:** 純前端渲染邏輯調整，`finance-app/index.html` 單檔。既有 `/finance/summary/years` API 回傳的資料（`total_income`/`total_expense`/`balance`/`by_category`）已足夠支撐三種模式，不新增後端 API、不重複 fetch。把現有 `loadStats()` 拆成「fetch 一次存起來」＋「依下拉選單值渲染」兩層，支出模式重用既有 `renderCategoryChart()` 畫每年類別圓餅圖。

**Tech Stack:** 原生 JS（無框架）、Chart.js（既有 `renderCategoryChart()`）。

**Spec:** `docs/superpowers/specs/2026-07-11-stats-mode-dropdown-design.md`

---

### Task 1: 下拉選單 UI 骨架 + 模組狀態變數

**Files:**
- Modify: `finance-app/index.html:435-441`（統計分頁卡片 HTML）
- Modify: `finance-app/index.html:988`（`loadStats()` 之前，新增模組層級變數）

- [ ] **Step 1: 在統計分頁卡片加入下拉選單，label 改成有 id 可動態更新**

當前 `finance-app/index.html:435-441` 是：

```html
<!-- ══════════════ TAB 5: 統計 ══════════════ -->
<div id="page-stats" class="page">
  <div class="card">
    <div class="label">歷年儲蓄率</div>
    <div id="stats-years-list"><div class="empty">尚無資料</div></div>
  </div>
</div>
```

改成：

```html
<!-- ══════════════ TAB 5: 統計 ══════════════ -->
<div id="page-stats" class="page">
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
      <div class="label" id="stats-label" style="margin-bottom:0">歷年儲蓄率</div>
      <select id="stats-mode" onchange="renderStatsMode()" style="width:auto;margin-bottom:0;padding:5px 10px;font-size:12px;border-radius:20px;background:#0f172a;color:#38bdf8;border:1px solid #1e3a5f">
        <option value="rate">儲蓄率</option>
        <option value="income">收入</option>
        <option value="expense">支出</option>
      </select>
    </div>
    <div id="stats-years-list"><div class="empty">尚無資料</div></div>
  </div>
</div>
```

下拉選單樣式沿用既有 `.badge`／`.nw-toggle` 的深色圓角 pill 語言（`#0f172a` 底、`#38bdf8` 字、`#1e3a5f` 邊框、`border-radius:20px`），`width:auto;margin-bottom:0` 是為了蓋掉全域 `input,select{width:100%;margin-bottom:10px}` 規則，讓選單維持行內小尺寸。

- [ ] **Step 2: 新增模組層級狀態變數，管理已 fetch 的資料與每年圓餅圖的 Chart.js 實例**

在 `finance-app/index.html` 的 `async function loadStats()`（目前第 989 行）正上方插入：

```javascript
let statsYearsData = [];
let statsCatCharts = {};

function statsCatChartRef(year) {
  return {
    get chart(){ return statsCatCharts[year]; },
    set chart(v){ statsCatCharts[year] = v; }
  };
}
```

`statsCatChartRef(year)` 回傳的物件符合既有 `renderCategoryChart(canvasId, legendId, chartVar, catMap)` 對 `chartVar` 參數的介面要求（需要 `.chart` 的 getter/setter），讓每個年份的圓餅圖各自用 `statsCatCharts[year]` 存自己的 Chart.js 實例，重畫時才能正確 destroy 舊圖。

- [ ] **Step 3: 用 Playwright 確認下拉選單骨架正確顯示（此時選單還不會真的切換內容，因為 `renderStatsMode()` 尚未實作）**

用 Playwright 開啟本地起的 `finance-app/index.html`（例如 `python3 -m http.server` 在 `finance-app/` 目錄下），切到「📊 統計」分頁，截圖確認：
- 「歷年儲蓄率」標籤右側出現「儲蓄率／收入／支出」下拉選單，樣式是深色圓角小 pill
- 選單目前預設選到「儲蓄率」
- 頁面其餘內容（若已設定 API 且有資料）維持跟切換前一致（因為 `renderStatsMode()` 還沒實作，`onchange` 呼叫會拋 `renderStatsMode is not defined` 但不影響既有畫面，只是 console 會有錯誤，這是預期中的暫時狀態，Task 2 會修掉）

- [ ] **Step 4: Commit**

```bash
git add finance-app/index.html
git commit -m "feat: add stats mode dropdown UI shell and chart-instance state"
```

---

### Task 2: 重構 `loadStats()`，實作 `renderStatsMode()` 與儲蓄率模式

**Files:**
- Modify: `finance-app/index.html:989-1026`（現有 `loadStats()`，改成 fetch-and-store + 分派渲染）

- [ ] **Step 1: 把現有 `loadStats()` 拆成「fetch 存資料」與「渲染儲蓄率模式」兩個函式**

當前 `finance-app/index.html:989-1026` 是：

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

整段換成：

```javascript
async function loadStats() {
  if(!API) return;
  try {
    statsYearsData = await api('/finance/summary/years');
    document.getElementById('stats-mode').value = 'rate';
    renderStatsMode();
  } catch(e){ console.error(e); }
}

function renderStatsMode() {
  const mode = document.getElementById('stats-mode').value;
  const labelEl = document.getElementById('stats-label');
  const listEl = document.getElementById('stats-years-list');
  const years = statsYearsData;
  if(!years.length){
    labelEl.textContent = mode==='rate'?'歷年儲蓄率':mode==='income'?'歷年收入':'歷年支出';
    listEl.innerHTML = '<div class="empty">尚無資料</div>';
    return;
  }
  if(mode==='rate') renderStatsRate(years, labelEl, listEl);
  else if(mode==='income') renderStatsIncome(years, labelEl, listEl);
  else renderStatsExpense(years, labelEl, listEl);
}

function renderStatsRate(years, labelEl, listEl) {
  labelEl.textContent = '歷年儲蓄率';
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
}
```

`renderStatsRate()` 的內容跟原本 `loadStats()` 裡的渲染邏輯逐字相同，只是換了資料來源（參數傳入而非重新 fetch）跟多加了 `labelEl.textContent` 設定。`renderStatsIncome()`／`renderStatsExpense()` 會在 Task 3、Task 4 實作，這一步先不呼叫它們也不用定義空函式——`renderStatsMode()` 裡引用到它們是正常的 forward reference（JS function 宣告會 hoist，但下拉選單預設值是 `rate`，使用者要手動切到 income/expense 才會呼叫到，Task 2 結束時先確保不切換的情況下功能正常）。

- [ ] **Step 2: 用 Playwright 確認儲蓄率模式維持原本行為**

用 Playwright 開啟本地 `finance-app/index.html`，設定好 API URL，切到「📊 統計」分頁，確認畫面內容（年份、儲蓄率、進度條、收入/支出金額、歷年平均）跟改動前完全一致（可以用先前 Task 4 of yearly-savings-rate-tab plan 建立的測試資料）。

- [ ] **Step 3: Commit**

```bash
git add finance-app/index.html
git commit -m "refactor: split loadStats into fetch-once + renderStatsMode dispatch"
```

---

### Task 3: 實作「收入」模式

**Files:**
- Modify: `finance-app/index.html`（`renderStatsRate()` 函式之後，新增 `renderStatsIncome()`）

- [ ] **Step 1: 在 `renderStatsRate()` 之後加入 `renderStatsIncome()`**

```javascript
function renderStatsIncome(years, labelEl, listEl) {
  labelEl.textContent = '歷年收入';
  const nowYear = String(new Date().getFullYear());
  let rows='', sum=0;
  years.forEach(y=>{
    sum += y.total_income;
    const tag = y.year===nowYear ? ' <span class="badge" style="margin-left:6px;cursor:default">本年</span>' : '';
    rows += `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <span style="font-size:15px;font-weight:700">${y.year}年${tag}</span>
        <span style="font-size:16px;font-weight:800;color:#4ade80">NT$${y.total_income.toLocaleString()}</span>
      </div>`;
  });
  const avg = sum/years.length;
  rows += `
    <div style="border-top:1px solid #334155;padding-top:10px;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:14px;font-weight:600">歷年平均</span>
      <span style="font-size:16px;font-weight:800;color:#4ade80">NT$${Math.round(avg).toLocaleString()}</span>
    </div>`;
  listEl.innerHTML = rows;
}
```

- [ ] **Step 2: 用 Playwright 驗證收入模式**

切到「📊 統計」分頁，把下拉選單切成「收入」，用既有 3 年測試資料（2024/2025/2026，收入分別 NT$1,000,000／NT$1,200,000／NT$800,000）截圖確認：
- 標籤變成「歷年收入」
- 三個年度由舊到新列出，2026 有「本年」標籤，金額正確、無進度條
- 底部「歷年平均」= NT$1,000,000（三年平均剛好整數，方便肉眼核對）

- [ ] **Step 3: Commit**

```bash
git add finance-app/index.html
git commit -m "feat: add income mode to stats tab dropdown"
```

---

### Task 4: 實作「支出」模式（含每年類別圓餅圖）

**Files:**
- Modify: `finance-app/index.html`（`renderStatsIncome()` 函式之後，新增 `renderStatsExpense()`）

- [ ] **Step 1: 在 `renderStatsIncome()` 之後加入 `renderStatsExpense()`**

```javascript
function renderStatsExpense(years, labelEl, listEl) {
  labelEl.textContent = '歷年支出';
  const nowYear = String(new Date().getFullYear());
  let rows='', sum=0;
  years.forEach(y=>{
    sum += y.total_expense;
    const tag = y.year===nowYear ? ' <span class="badge" style="margin-left:6px;cursor:default">本年</span>' : '';
    rows += `
      <div style="margin-bottom:20px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <span style="font-size:15px;font-weight:700">${y.year}年${tag}</span>
          <span style="font-size:16px;font-weight:800;color:#f87171">NT$${y.total_expense.toLocaleString()}</span>
        </div>
        <div class="chart-wrap"><canvas id="stats-cat-chart-${y.year}"></canvas></div>
        <div id="stats-cat-legend-${y.year}"></div>
      </div>`;
  });
  const avg = sum/years.length;
  rows += `
    <div style="border-top:1px solid #334155;padding-top:10px;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:14px;font-weight:600">歷年平均</span>
      <span style="font-size:16px;font-weight:800;color:#f87171">NT$${Math.round(avg).toLocaleString()}</span>
    </div>`;
  listEl.innerHTML = rows;
  years.forEach(y=>{
    renderCategoryChart(`stats-cat-chart-${y.year}`, `stats-cat-legend-${y.year}`, statsCatChartRef(y.year), y.by_category);
  });
}
```

`listEl.innerHTML = rows` 要先執行完，`canvas` 元素才會真的存在於 DOM 裡，之後才能逐年呼叫 `renderCategoryChart()`——這就是為什麼圓餅圖的渲染迴圈要放在 `innerHTML` 賦值之後，而不是跟組 HTML 字串的迴圈合併在一起。`renderCategoryChart()` 內建的 `if(chartVar.chart) chartVar.chart.destroy()` 會處理重畫時的清理，這裡不用額外處理。

- [ ] **Step 2: 用 Playwright 驗證支出模式，含類別圓餅圖跟切換不疊圖**

切到「📊 統計」分頁，把下拉選單切成「支出」，用既有 3 年測試資料（2024/2025/2026 支出分別 NT$300,000／NT$400,000／NT$500,000，皆為單一「日常」類別的測試交易）截圖確認：
- 標籤變成「歷年支出」
- 三個年度由舊到新列出，各自下方有一個圓餅圖跟 legend，2026 有「本年」標籤
- 圓餅圖類別比例正確（測試資料只有「日常」一個類別，圓餅圖應該是純色圓形，legend 顯示「日常 NT$xxx (100.0%)」）
- 底部「歷年平均」= NT$400,000

再把下拉選單切回「儲蓄率」、切回「支出」兩次，截圖確認圓餅圖沒有疊圖、殘影或報錯（打開瀏覽器 console 確認沒有新的 error log）。

- [ ] **Step 3: Commit**

```bash
git add finance-app/index.html
git commit -m "feat: add expense mode with per-year category pie charts to stats tab"
```

---

### Task 5: 部署確認

**Files:** 無程式變更

- [ ] **Step 1: 確認 monorepo commit 都已 push**

Run: `git log origin/main..HEAD --oneline`（在 monorepo 根目錄）
Expected: 空輸出

- [ ] **Step 2: 提醒使用者這是前端限定變更，push 後 Netlify 會自動部署，等 1-2 分鐘後開正式網址確認**

用 Playwright 開啟 `https://incandescent-mooncake-3de7e3.netlify.app`，切到「📊 統計」分頁，依序切三種下拉選單模式，截圖確認正式環境資料（2022~2026 真實歷史資料）在三種模式下都正確顯示，尤其確認支出模式的圓餅圖类別跟既有「支出」分頁的年度圓餅圖數字一致。
