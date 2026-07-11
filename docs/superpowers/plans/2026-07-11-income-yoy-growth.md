# 統計頁「收入」模式年增長率 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 「統計」分頁「收入」模式的每一列收入金額下方，加一行顯示跟列表上一筆比較的年增長率。

**Architecture:** 純前端小改動，只動 `finance-app/index.html` 裡的 `renderStatsIncome()` 函式，改用帶 index 的迴圈計算 `(當年-上一筆)/上一筆*100`，陣列第一筆不顯示。不新增後端 API、不動其他模式。

**Tech Stack:** 原生 JS，無框架。

**Spec:** `docs/superpowers/specs/2026-07-11-income-yoy-growth-design.md`

---

### Task 1: `renderStatsIncome()` 加年增長率

**Files:**
- Modify: `finance-app/index.html:1065-1085`（`renderStatsIncome()` 函式）

- [ ] **Step 1: 把 `renderStatsIncome()` 換成帶年增長率計算的版本**

當前 `finance-app/index.html:1065-1085` 是：

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

改成：

```javascript
function renderStatsIncome(years, labelEl, listEl) {
  labelEl.textContent = '歷年收入';
  const nowYear = String(new Date().getFullYear());
  let rows='', sum=0;
  years.forEach((y,i)=>{
    sum += y.total_income;
    const tag = y.year===nowYear ? ' <span class="badge" style="margin-left:6px;cursor:default">本年</span>' : '';
    let yoyRow = '';
    if(i>0){
      const prev = years[i-1].total_income;
      const growth = (y.total_income - prev) / prev * 100;
      const color = growth>=0?'#4ade80':'#f87171';
      yoyRow = `
        <div style="text-align:right;font-size:12px;color:${color};margin-top:2px">vs 去年 ${growth>=0?'+':''}${growth.toFixed(1)}%</div>`;
    }
    rows += `
      <div style="margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:15px;font-weight:700">${y.year}年${tag}</span>
          <span style="font-size:16px;font-weight:800;color:#4ade80">NT$${y.total_income.toLocaleString()}</span>
        </div>${yoyRow}
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

差異：`years.forEach(y=>{...})` 改成 `years.forEach((y,i)=>{...})` 拿到 index；`i>0` 時才計算 `growth`（陣列第一筆 `i===0` 沒有上一筆可比，`yoyRow` 維持空字串）；比較對象固定是 `years[i-1]`（陣列裡的前一筆），不管年份數字是否連續；原本單行的 flex row 包進一個外層 `<div style="margin-bottom:14px">`，`margin-bottom` 從內層 flex row 移到外層，讓年增長率那行可以接在下面且維持列與列之間的間距。

不需要處理 `prev===0` 的除以零情況——`years` 資料來自 `/finance/summary/years`，該 API 已經排除 `total_income===0` 的年份（見 `docs/superpowers/specs/2026-07-11-yearly-savings-rate-tab-design.md`），`prev` 一定大於 0。

- [ ] **Step 2: 用 Playwright 驗證年增長率計算與顯示**

啟動本地 `finance-server`（沿用先前 Task 用過的做法：`DATA_DIR` 指向暫存目錄的 `uvicorn`），寫入 3 年收入測試資料：2024 NT$1,000,000、2025 NT$1,200,000、2026 NT$800,000（沿用先前 stats-mode-dropdown 計畫用過的種子資料）。用本地靜態伺服器開啟 `finance-app/index.html`，在「⚙️ API 設定」指到本地後端，切到「📊 統計」分頁、下拉選單選「收入」，截圖確認：

- 2024（陣列第一筆）金額下方**沒有**「vs 去年」那行
- 2025 顯示「vs 去年 +20.0%」，綠色（`(1200000-1000000)/1000000*100=20.0`）
- 2026 顯示「vs 去年 -33.3%」，紅色（`(800000-1200000)/1200000*100=-33.33...`，四捨五入到一位小數是 -33.3）
- 底部「歷年平均」金額不受影響，維持 NT$1,000,000

再切到「儲蓄率」跟「支出」模式，確認畫面沒有受影響（regression check），瀏覽器 console 沒有新增錯誤。驗證完後 kill 掉本地啟動的 `uvicorn` 與靜態伺服器背景行程。

- [ ] **Step 3: Commit**

```bash
git add finance-app/index.html
git commit -m "feat: add YoY growth rate to stats income mode"
```

---

### Task 2: 部署確認

**Files:** 無程式變更

- [ ] **Step 1: 確認 monorepo commit 已 push**

Run: `git log origin/main..HEAD --oneline`（在 monorepo 根目錄）
Expected: 空輸出（若非空，需先跟使用者確認才能 push，因為會觸發 Netlify 正式環境部署）

- [ ] **Step 2: Push 後打開正式 Netlify 網址驗證**

用 Playwright 開啟 `https://incandescent-mooncake-3de7e3.netlify.app`，切到「📊 統計」分頁、下拉選單選「收入」，用真實歷史資料截圖確認年增長率數字合理（跟正式環境的實際年度收入金額手動核對至少一年）。
