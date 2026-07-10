# 月份選單年份分組 + 年度結餘儲蓄率 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 月份下拉選單改用年份 `<optgroup>` 分組，讓歷史資料（2022 年起）可被選到；年度結餘卡片新增儲蓄率顯示。

**Architecture:** 純前端變更，只動 `finance-app/index.html`。`buildMonths()` 從產生扁平 24 個月選項改為往回 5 年、依年份分組產生選項；`loadYearlyBalance()` 新增儲蓄率計算與一個新的 HTML 元素。

**Tech Stack:** 原生 JS（無框架）、單一 HTML 檔案 PWA，Netlify 自動部署。

**技術背景：** `finance-app/index.html` push 到本 monorepo（`anesthesia-digest-bot`）的 `main` 分支即可，Netlify 已連 repo 自動部署到 `incandescent-mooncake-3de7e3.netlify.app`（base directory 設為 `finance-app`）。本地沒有前端測試框架，用 `node --check` 做語法檢查 + 手動瀏覽器驗證。

---

### Task 1: 月份選單改用年份分組

**Files:**
- Modify: `finance-app/index.html:666-676`（`buildMonths` 函式）

- [ ] **Step 1: 替換 `buildMonths` 函式**

找到第 666-676 行現有內容：
```js
function buildMonths(id) {
  const sel=document.getElementById(id);
  if(sel.options.length) return sel.value;
  const now=new Date();
  for(let i=0;i<24;i++){
    const d=new Date(now.getFullYear(),now.getMonth()-i,1);
    const v=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;
    sel.add(new Option(v,v));
  }
  return sel.value;
}
```

換成：
```js
function buildMonths(id) {
  const sel=document.getElementById(id);
  if(sel.options.length) return sel.value;
  const now=new Date();
  const nowYear=now.getFullYear(), nowMonth=now.getMonth();
  for(let yi=0;yi<5;yi++){
    const year=nowYear-yi;
    const group=document.createElement('optgroup');
    group.label=`${year}年`;
    const maxMonth=(yi===0)?nowMonth:11;
    for(let mi=maxMonth;mi>=0;mi--){
      const v=`${year}-${String(mi+1).padStart(2,'0')}`;
      const opt=document.createElement('option');
      opt.value=v; opt.textContent=v;
      group.appendChild(opt);
    }
    sel.appendChild(group);
  }
  return sel.value;
}
```

- [ ] **Step 2: 靜態語法驗證**

抽出 `<script>` 內容跑 Node 語法檢查（不需要瀏覽器）：

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/finance-app"
python3 -c "
import re
html = open('index.html').read()
m = re.search(r'<script>(.*)</script>', html, re.DOTALL)
open('/tmp/finance-app-script-check.js', 'w').write(m.group(1))
"
node --check /tmp/finance-app-script-check.js
```

Expected: 沒有輸出（代表語法正確）。若報錯，檢查是否漏了括號或逗號。

- [ ] **Step 3: 本機起靜態伺服器手動驗證**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/finance-app"
python3 -m http.server 8080
```

瀏覽器開 `http://localhost:8080`，設定 API URL 為 `https://jenna-finance.onrender.com`（齒輪圖示 → 貼上網址），切到支出頁，點開月份下拉選單，確認：
1. 選單裡出現「2026年」「2025年」「2024年」「2023年」「2022年」共 5 個群組標籤
2. 今年（2026年）群組只列到目前月份，不會有未來月份
3. 往年群組列滿 1-12 月
4. 選一個 2022 或 2023 年的月份（例如 2023-01），確認支出頁正確載入該月的歷史資料（先前已匯入）
5. 切到收入頁，重複同樣的驗證（`sel-inc` 也用同一個 `buildMonths` 函式）

驗證完後 `Ctrl+C` 停掉伺服器。

- [ ] **Step 4: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add finance-app/index.html
git commit -m "feat: group month selector options by year via optgroup"
```

---

### Task 2: 年度結餘卡片新增儲蓄率

**Files:**
- Modify: `finance-app/index.html:260-263`（`balance-card-year` 卡片 HTML，新增一行）
- Modify: `finance-app/index.html:946-957`（`loadYearlyBalance` 函式）

- [ ] **Step 1: 在年度結餘卡片 HTML 新增儲蓄率顯示元素**

找到第 260-264 行：
```html
    <div style="display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:14px;font-weight:600">年度結餘</span>
      <span style="font-size:22px;font-weight:800" id="bal-year-net">--</span>
    </div>
  </div>
```

改成：
```html
    <div style="display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:14px;font-weight:600">年度結餘</span>
      <span style="font-size:22px;font-weight:800" id="bal-year-net">--</span>
    </div>
    <div style="text-align:right;margin-top:4px">
      <span style="font-size:12px;color:#64748b" id="bal-year-rate">--</span>
    </div>
  </div>
```

- [ ] **Step 2: 在 `loadYearlyBalance` 新增儲蓄率計算**

找到第 946-957 行：
```js
async function loadYearlyBalance() {
  if(!API) return;
  const year=buildYears('sel-inc-year');
  try {
    const s=await api(`/finance/summary/year/${year}`);
    document.getElementById('bal-year-income').textContent=`NT$${s.total_income.toLocaleString()}`;
    document.getElementById('bal-year-expense').textContent=`NT$${s.total_expense.toLocaleString()}`;
    const netEl=document.getElementById('bal-year-net');
    netEl.textContent=`NT$${s.balance.toLocaleString()}`;
    netEl.style.color=s.balance>=0?'#4ade80':'#f87171';
  } catch(e){console.error(e);}
}
```

改成：
```js
async function loadYearlyBalance() {
  if(!API) return;
  const year=buildYears('sel-inc-year');
  try {
    const s=await api(`/finance/summary/year/${year}`);
    document.getElementById('bal-year-income').textContent=`NT$${s.total_income.toLocaleString()}`;
    document.getElementById('bal-year-expense').textContent=`NT$${s.total_expense.toLocaleString()}`;
    const netEl=document.getElementById('bal-year-net');
    netEl.textContent=`NT$${s.balance.toLocaleString()}`;
    netEl.style.color=s.balance>=0?'#4ade80':'#f87171';
    const rateEl=document.getElementById('bal-year-rate');
    if(s.total_income>0){
      const rate=(s.balance/s.total_income*100);
      rateEl.textContent=`儲蓄率 ${rate>=0?'+':''}${rate.toFixed(1)}%`;
      rateEl.style.color=rate>=0?'#4ade80':'#f87171';
    } else {
      rateEl.textContent='儲蓄率 --';
      rateEl.style.color='#64748b';
    }
  } catch(e){console.error(e);}
}
```

- [ ] **Step 3: 靜態語法驗證**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/finance-app"
python3 -c "
import re
html = open('index.html').read()
m = re.search(r'<script>(.*)</script>', html, re.DOTALL)
open('/tmp/finance-app-script-check.js', 'w').write(m.group(1))
"
node --check /tmp/finance-app-script-check.js
```

Expected: 沒有輸出。

- [ ] **Step 4: 本機手動驗證**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/finance-app"
python3 -m http.server 8080
```

瀏覽器開 `http://localhost:8080`，設定好 API URL，切到收入頁，確認：
1. 「年度結餘」卡片的結餘數字下方多一行「儲蓄率 XX.X%」
2. 選一個有收入資料的年份（例如 2024），結餘為正時儲蓄率是綠色 `+XX.X%`
3. 若選到收入為 0 的年份（例如尚無資料的未來年份），顯示「儲蓄率 --」，不報錯、不是 `NaN%`

驗證完 `Ctrl+C` 停掉伺服器。

- [ ] **Step 5: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add finance-app/index.html
git commit -m "feat: add savings rate to annual balance card"
```

---

### Task 3: Push 觸發 Netlify 部署並驗證

**Files:** 無新檔案，純部署動作

- [ ] **Step 1: 檢查遠端是否有分歧，必要時 rebase**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git fetch origin -q
git log HEAD..origin/main --oneline
```

若有輸出（例如 CI bot 的 `chore: update sent articles [skip ci]` 例行 commit），執行：

```bash
git status --short
```

若只有 `.claude/settings.local.json` 或 `miller_queue.json` 這類跟本次改動無關的既有未 commit 檔案，先暫存它們再 rebase：

```bash
git stash push -u -m "pre-rebase safety" .claude/settings.local.json miller_queue.json
git pull --rebase origin main
git push origin main
git stash pop
```

若沒有無關的未 commit 檔案，直接：

```bash
git pull --rebase origin main
git push origin main
```

- [ ] **Step 2: 等 Netlify 自動部署完成後驗證**

等待約 60-90 秒後執行：

```bash
curl -s https://incandescent-mooncake-3de7e3.netlify.app/ | grep -c "optgroup\|bal-year-rate"
```

Expected: `2`（代表 `optgroup` 產生邏輯與 `bal-year-rate` 元素都已部署上線）。若不是 2，等 60 秒後重試一次；仍不是則檢查 Netlify Deploys 頁面的 build log。

- [ ] **Step 3: 實機驗證**

打開 app，強制重新整理，分別在支出頁、收入頁確認：
1. 月份下拉選單有年份分組，可以選到 2022-2023 年的歷史月份
2. 選到歷史月份後，交易列表與類別分佈正確顯示該月資料
3. 收入頁「年度結餘」卡片顯示儲蓄率
4. 既有功能（本月結餘、年度支出圓環圖等）沒有壞掉

---

## Self-Review 對照 Spec

- ✅ 月份選單改用 `<optgroup>` 依年份分組，往回 5 年，今年只列到當月（Task 1）
- ✅ 選項 `value` 格式不變，既有讀取 `.value` 的程式碼（`loadExpenses`、`loadIncome`、`deleteMonth`）不需修改（Task 1 未觸及這些函式）
- ✅ 年度結餘卡片新增儲蓄率，公式為 `balance/total_income*100%`，收入為 0 時顯示 `--`，正負配色比照結餘（Task 2）
- ✅ 只加在年度結餘卡片，月度「本月結餘」卡片不變動（Task 2 只改 `balance-card-year` 區塊，未觸及 `balance-card`）
- ✅ 部署路徑（push 到 monorepo main、Netlify 自動部署）已在 Task 3 明確列出，含既有 CI bot 分歧的 rebase 處理方式
