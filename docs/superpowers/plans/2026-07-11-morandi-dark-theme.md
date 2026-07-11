# 深色莫蘭迪色系改版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把個人財務 App 的核心色（背景/卡片/文字/語意色/邊框，218 處寫死 hex）跟支出類別十色，換成莫蘭迪深色系配色，改用 CSS 變數統一管理。

**Architecture:** 純前端換色，只動 `finance-app/index.html` 單檔。先在 `<style>` 最上面宣告 `:root` CSS 變數，再用全域字串取代把舊 hex 換成 `var(--xxx)`（CSS 規則跟 JS 樣板字串裡的 inline style 都是同一份文字檔，取代方式一致）。`CAT_COLORS` 物件的十個類別色直接改成新 hex 值。不新增後端 API、不改版面配置。

**Tech Stack:** 原生 CSS 自訂屬性（CSS Custom Properties）、原生 JS，無框架。

**Spec:** `docs/superpowers/specs/2026-07-11-morandi-dark-theme-design.md`

---

### Task 1: 宣告 CSS 變數

**Files:**
- Modify: `finance-app/index.html:14`（`<style>` 標籤正下方）

- [ ] **Step 1: 在 `<style>` 開頭插入 `:root` 變數區塊**

`finance-app/index.html` 第 14 行是 `<style>`，第 19 行開始是第一條 CSS 規則（`.tab{...}`）。在第 14 行 `<style>` 之後、第一條規則之前插入：

```css
:root {
  --bg-base: #1C1815;
  --bg-card: #2A2622;
  --text-primary: #E5DFD6;
  --text-secondary: #A89C8E;
  --text-muted: #948977;
  --green: #8FB088;
  --red: #D97D6C;
  --blue: #7CAFCE;
  --border: #443E37;
  --badge-border: #3E4A47;
}
```

- [ ] **Step 2: 確認變數區塊語法正確，畫面暫時不會變（還沒有任何規則引用這些變數）**

Run: `grep -n ":root" finance-app/index.html`
Expected: 顯示新插入的 `:root {` 那一行，且前後大括號成對（`grep -c '^}' finance-app/index.html` 的數字應該比改動前多 1，因為多了一個 `:root{...}` 區塊的收尾 `}`；如果變數寫成單行 `:root { ... }` 則不會多一行 `}`，用瀏覽器開發者工具或 Playwright 開啟頁面確認畫面沒有跑版即可，不強求這個 grep 數字）

用 Playwright 開啟本地 `finance-app/index.html`（`python3 -m http.server` 起本地伺服器），截圖確認畫面顏色**尚未改變**（因為還沒有任何地方引用 `var(--xxx)`），沒有版面跑掉或報錯。

- [ ] **Step 3: Commit**

```bash
git add finance-app/index.html
git commit -m "feat: declare Morandi color palette as CSS custom properties"
```

---

### Task 2: 核心色全域取代成 CSS 變數

**Files:**
- Modify: `finance-app/index.html`（全檔案範圍的字串取代，CSS 規則與 JS 樣板字串裡的 inline style 都會被取代到）

這個任務把 11 個舊 hex 色碼，逐一用 `sed` 做全域字串取代成對應的 `var(--xxx)`。因為每個舊 hex 碼都是獨一無二的 6 碼字串（不會是其他色碼的子字串），取代順序不影響結果。每做完一個顏色，用 `grep -c` 確認舊色碼在檔案裡的殘留數量歸零（`:root` 區塊本身用的是全新的 hex 值，不會被自己取代到，不用擔心誤傷）。

- [ ] **Step 1: 取代 `#4ade80`（綠，39 處）**

```bash
sed -i '' 's/#4ade80/var(--green)/g' finance-app/index.html
grep -c '#4ade80' finance-app/index.html
```
Expected: `0`

- [ ] **Step 2: 取代 `#f87171`（紅，39 處）**

```bash
sed -i '' 's/#f87171/var(--red)/g' finance-app/index.html
grep -c '#f87171' finance-app/index.html
```
Expected: `0`

- [ ] **Step 3: 取代 `#64748b`（次要文字，37 處）**

```bash
sed -i '' 's/#64748b/var(--text-secondary)/g' finance-app/index.html
grep -c '#64748b' finance-app/index.html
```
Expected: `0`

- [ ] **Step 4: 取代 `#0f172a`（主背景，33 處）**

```bash
sed -i '' 's/#0f172a/var(--bg-base)/g' finance-app/index.html
grep -c '#0f172a' finance-app/index.html
```
Expected: `0`

- [ ] **Step 5: 取代 `#38bdf8`（強調藍，21 處）**

```bash
sed -i '' 's/#38bdf8/var(--blue)/g' finance-app/index.html
grep -c '#38bdf8' finance-app/index.html
```
Expected: `0`

- [ ] **Step 6: 取代 `#334155`（邊框/分隔線，17 處）**

```bash
sed -i '' 's/#334155/var(--border)/g' finance-app/index.html
grep -c '#334155' finance-app/index.html
```
Expected: `0`

- [ ] **Step 7: 取代 `#e2e8f0`（主文字，16 處）**

```bash
sed -i '' 's/#e2e8f0/var(--text-primary)/g' finance-app/index.html
grep -c '#e2e8f0' finance-app/index.html
```
Expected: `0`

- [ ] **Step 8: 取代 `#1e293b`（卡片背景，12 處）**

```bash
sed -i '' 's/#1e293b/var(--bg-card)/g' finance-app/index.html
grep -c '#1e293b' finance-app/index.html
```
Expected: `0`

- [ ] **Step 9: 取代 `#94a3b8`（輔助文字，10 處）**

```bash
sed -i '' 's/#94a3b8/var(--text-muted)/g' finance-app/index.html
grep -c '#94a3b8' finance-app/index.html
```
Expected: `0`

- [ ] **Step 10: 取代 `#60a5fa`（次要強調藍，9 處，併入同一個 `--blue` 變數）**

```bash
sed -i '' 's/#60a5fa/var(--blue)/g' finance-app/index.html
grep -c '#60a5fa' finance-app/index.html
```
Expected: `0`

- [ ] **Step 11: 取代 `#1e3a5f`（badge/pill 邊框，4 處）**

```bash
sed -i '' 's/#1e3a5f/var(--badge-border)/g' finance-app/index.html
grep -c '#1e3a5f' finance-app/index.html
```
Expected: `0`

- [ ] **Step 12: 全檔案掃過一次，確認 11 個舊色碼都清乾淨，且沒有動到不該動的長尾色**

```bash
grep -oE "#[0-9a-fA-F]{6}" finance-app/index.html | sort | uniq -c | sort -rn
```

Expected：輸出裡不會再出現 `#4ade80`、`#f87171`、`#64748b`、`#0f172a`、`#38bdf8`、`#334155`、`#e2e8f0`、`#1e293b`、`#94a3b8`、`#60a5fa`、`#1e3a5f` 這 11 個舊色碼；`:root` 區塊裡新宣告的 10 個新色碼（`#1C1815`／`#2A2622`／`#E5DFD6`／`#A89C8E`／`#948977`／`#8FB088`／`#D97D6C`／`#7CAFCE`／`#443E37`／`#3E4A47`）各出現 1 次（只在 `:root` 區塊宣告那一行）；`CAT_COLORS` 的十個舊類別色（`#E8735A` 等）跟其餘約 20 個長尾色維持原樣不動（Task 3 才處理類別色，長尾色這次不動）。

- [ ] **Step 13: 用 Playwright 視覺確認顏色已經套用**

用本地靜態伺服器開啟 `finance-app/index.html`，截圖「支出」分頁，確認：背景從藍黑變成暖炊灰棕、卡片色階可辨識、金額正負色（綠/紅）變成柔和的莫蘭迪色調、沒有版面跑掉。瀏覽器 console 沒有新增錯誤。

- [ ] **Step 14: Commit**

```bash
git add finance-app/index.html
git commit -m "feat: replace core hardcoded colors with Morandi CSS variables"
```

---

### Task 3: 支出類別十色改成莫蘭迪配色

**Files:**
- Modify: `finance-app/index.html`（`const CAT_COLORS={...}` 那一行，目前在既有程式碼裡搜尋 `const CAT_COLORS` 定位，先前在 Task 1/2 編輯後行號可能已偏移）

- [ ] **Step 1: 把 `CAT_COLORS` 物件的十個 hex 值換成新配色**

搜尋 `const CAT_COLORS={` 找到目前這一行（改動前是 `finance-app/index.html:725`）：

```javascript
const CAT_COLORS={日常:'#E8735A',房租:'#4F83B5',交通:'#8EA36E',旅遊:'#4B5FA6',娛樂:'#D4618A',教育:'#3A8B4E',醫療:'#B94047',贈與:'#E8A823',長期規劃:'#7B5EA7',貸款:'#475569'};
```

改成：

```javascript
const CAT_COLORS={日常:'#D4713A',房租:'#4A7FC0',交通:'#3C9470',旅遊:'#8A5CC9',娛樂:'#C15D8A',教育:'#1E9DB8',醫療:'#C24F3A',贈與:'#A4921E',長期規劃:'#A050AE',貸款:'#1E7855'};
```

這十個新 hex 值是用 dataviz skill 的 `validate_palette.js` 驗證過的組合（亮度、飽和度下限、對比度全數通過；色盲安全九對通過建議值，「贈與」跟「日常」這一對 ΔE 7.1 略低於建議下限，因為圓餅圖旁邊本來就有文字 legend 輔助辨識，這個落差是刻意接受的例外，細節見 spec 文件第 3 節）。

- [ ] **Step 2: 用 Playwright 驗證支出類別圓餅圖**

用本地靜態伺服器開啟 `finance-app/index.html`，切到「支出」分頁（月度跟年度圓餅圖都要看），也切到「統計」分頁的「支出」模式（沿用先前 stats-mode-dropdown 計畫用過的 3 年測試資料），截圖確認：
- 十個類別的圓餅圖色塊都是新的莫蘭迪色，彼此可以區分
- Legend 列表的顏色圓點、文字、金額、百分比都正常顯示，沒有因為換色跑版
- 瀏覽器 console 沒有新增錯誤

- [ ] **Step 3: Commit**

```bash
git add finance-app/index.html
git commit -m "feat: switch expense category pie chart to Morandi palette"
```

---

### Task 4: 全站視覺回歸驗證

**Files:** 無程式變更

- [ ] **Step 1: 用 Playwright 依序截圖 5 個分頁，跟改版前的畫面比對**

用本地 `finance-server`（沿用先前 Task 用過的 `DATA_DIR` 暫存目錄 + 種子資料做法）跟本地靜態伺服器，把 `finance-app/index.html` 的 API 設定指到本地後端，依序切「支出」「收入」「投資」「資產」「統計」（含儲蓄率/收入/支出三種下拉模式）五個分頁，逐一截圖確認：
- 背景、卡片、文字、進度條、badge、下拉選單邊框等元件都套用新色，視覺一致
- 沒有任何地方殘留舊的鮮豔色（藍黑背景、亮綠、亮紅、亮藍）
- 沒有版面跑掉、文字看不清楚、或元件邊界消失的狀況
- 瀏覽器 console 全程沒有新增錯誤

驗證完後 kill 掉本地啟動的 `uvicorn` 與靜態伺服器背景行程。

- [ ] **Step 2: 確認長尾色（約 20 個零星色）維持原樣**

Run: `grep -oE "#[0-9a-fA-F]{6}" finance-app/index.html | sort | uniq -c | sort -rn`
Expected：除了 `:root` 區塊的 10 個新核心色變數值、`CAT_COLORS` 的 10 個新類別色，其餘約 20 個長尾色（例如 `#dc2626`、`#fbbf24`、`#7c3aed` 等）的 hex 值跟改版前完全一樣，沒有被誤動到。

---

### Task 5: 部署確認

**Files:** 無程式變更

- [ ] **Step 1: 確認 monorepo commit 已 push**

Run: `git log origin/main..HEAD --oneline`（在 monorepo 根目錄）
Expected: 空輸出（若非空，需先跟使用者確認才能 push，因為會觸發 Netlify 正式環境部署）

- [ ] **Step 2: Push 後打開正式 Netlify 網址做最終視覺確認**

用 Playwright 開啟 `https://incandescent-mooncake-3de7e3.netlify.app`，用真實歷史資料依序截圖 5 個分頁，確認正式環境的莫蘭迪配色跟本地驗證結果一致。
