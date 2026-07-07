# 年度統計（支出類別圓環 + 收入年度結餘）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支出頁新增年度類別分佈圓環圖，收入頁新增年度收入／支出／結餘卡片。

**Architecture:** 後端新增一支 `GET /finance/summary/year/{year}` 彙總 API（`finance-server/`，獨立 repo `jenna-finance`，Render 部署）。前端在 `finance-app/index.html` 新增年份選單與兩張卡片，圓環圖渲染邏輯從既有月度邏輯抽成共用函式復用。

**Tech Stack:** FastAPI + SQLAlchemy（PostgreSQL on Render）、原生 JS + Chart.js（單一 HTML 檔案 PWA）。

**技術背景（重要）：**
- `finance-server/` 資料夾本身是一個獨立 git repo，`origin` 直接指向 `https://github.com/Jennawang123/jenna-finance.git`（Render 實際部署來源）。所有後端改動要在 `finance-server/` 目錄內 `git add/commit/push`，push 到這個 repo 的 `main` 分支才會觸發 Render 自動部署。**不要**只 push 到本 monorepo（`anesthesia-digest-bot`）——那邊的 `finance-server/` 只是本地參考副本，Render 看不到。
- `finance-app/index.html` 是前端，push 到本 monorepo（`anesthesia-digest-bot`）的 `main` 分支即可，Netlify 已設定自動部署（`incandescent-mooncake-3de7e3.netlify.app`）。
- 本地沒有 pytest / 前端測試框架，這個專案的既有驗證方式是「本機跑一次 + curl / 瀏覽器手動驗證」，不要新增測試框架。

---

### Task 1: 後端 — 新增依年份查詢收入的函式

**Files:**
- Modify: `finance-server/finance_db.py`（在 `list_income` 函式，約第 253-259 行後方新增）

- [ ] **Step 1: 新增 `list_income_by_year` 函式**

在 `finance-server/finance_db.py` 的 `list_income` 函式（第 253-259 行）後方插入：

```python
def list_income_by_year(year: str) -> list:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM income WHERE year_month LIKE :y"), {"y": f"{year}%"})
        return _rows(result)
```

- [ ] **Step 2: 本機快速驗證函式邏輯**

在 `finance-server/` 目錄下執行：

```bash
cd finance-server
DATA_DIR=/tmp/finance-test python3 -c "
import finance_db as db
db.init_db()
db.upsert_income('2026-01', '薪水', 50000)
db.upsert_income('2026-02', '薪水', 50000)
db.upsert_income('2025-12', '薪水', 45000)
rows = db.list_income_by_year('2026')
print(len(rows), sum(r['amount'] for r in rows))
"
```

Expected: 印出 `2 100000`（只抓到 2026 年的兩筆，2025-12 那筆被排除）。

- [ ] **Step 3: Commit（先不 push，累積到 Task 4 一起推）**

```bash
cd finance-server
git add finance_db.py
git commit -m "feat: add list_income_by_year for annual summary"
```

---

### Task 2: 後端 — 新增 `yearly_summary` 彙總函式

**Files:**
- Modify: `finance-server/finance_db.py`（在 `monthly_summary` 函式，約第 214-229 行後方新增）

- [ ] **Step 1: 新增 `yearly_summary` 函式**

在 `finance-server/finance_db.py` 的 `monthly_summary` 函式（第 214-229 行）後方插入：

```python
def yearly_summary(year: str) -> dict:
    txs = list_transactions(year)
    by_category: dict = {}
    for tx in txs:
        by_category[tx["category"]] = by_category.get(tx["category"], 0) + tx["amount"]
    total_expense = sum(tx["amount"] for tx in txs)
    income_rows = list_income_by_year(year)
    total_income = sum(r["amount"] for r in income_rows)
    return {
        "year": year,
        "total_expense": total_expense,
        "total_income": total_income,
        "balance": total_income - total_expense,
        "by_category": by_category,
        "transaction_count": len(txs),
    }
```

（`list_transactions(year)` 沿用既有的 `LIKE` 前綴比對，`year="2026"` 會自動比對成 `LIKE '2026%'`，不需修改。）

- [ ] **Step 2: 本機快速驗證**

```bash
cd finance-server
DATA_DIR=/tmp/finance-test2 python3 -c "
import finance_db as db
db.init_db()
db.upsert_income('2026-01', '薪水', 50000)
db.upsert_income('2026-02', '薪水', 50000)
r = db.yearly_summary('2026')
print(r)
"
```

Expected: 印出的 dict 包含 `'total_income': 100000, 'total_expense': 0, 'balance': 100000, 'transaction_count': 0`（因為這次沒插入 transactions，只驗證 income 加總正確）。

- [ ] **Step 3: Commit**

```bash
cd finance-server
git add finance_db.py
git commit -m "feat: add yearly_summary aggregation"
```

---

### Task 3: 後端 — 新增年度彙總路由

**Files:**
- Modify: `finance-server/finance_api.py`（在 `get_summary` 路由，約第 103-106 行後方新增）

- [ ] **Step 1: 新增路由**

在 `finance-server/finance_api.py` 的 `get_summary` 函式（第 103-106 行）後方插入：

```python
@router.get("/summary/year/{year}")
def get_yearly_summary(year: str, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return db.yearly_summary(year)
```

- [ ] **Step 2: 本機起服務驗證路由存在**

```bash
cd finance-server
DATA_DIR=/tmp/finance-test3 uvicorn main:app --port 8123 &
sleep 2
curl -s http://127.0.0.1:8123/openapi.json | python3 -c "import json,sys; print('/finance/summary/year/{year}' in json.load(sys.stdin)['paths'])"
curl -s http://127.0.0.1:8123/finance/summary/year/2026
kill %1
```

Expected: 第一行印出 `True`；第二行印出 `{"year":"2026","total_expense":0,"total_income":0,"balance":0,"by_category":{},"transaction_count":0}`（空資料庫，數字全 0 但格式正確，不報 500）。

- [ ] **Step 3: Commit**

```bash
cd finance-server
git add finance_api.py
git commit -m "feat: add GET /finance/summary/year/{year} route"
```

---

### Task 4: 後端 — Push 到 jenna-finance 觸發 Render 部署

**Files:** 無新檔案，純部署動作

- [ ] **Step 1: Push**

```bash
cd finance-server
git push origin main
```

- [ ] **Step 2: 等 Render 自動部署完成後驗證線上路由**

等待約 60-90 秒後執行：

```bash
curl -s https://jenna-finance.onrender.com/openapi.json | python3 -c "
import json,sys
print('/finance/summary/year/{year}' in json.load(sys.stdin)['paths'])
"
```

Expected: `True`

---

### Task 5: 前端 — 抽出共用的類別圓環圖渲染函式

**Files:**
- Modify: `finance-app/index.html:653-690`（`catChart` 變數宣告與 `renderExpenses` 函式內的圖表渲染邏輯）

**背景：** 現有 `renderExpenses()`（第 664-712 行）裡，第 669-690 行是「算類別加總 → 畫 doughnut 圖 → 畫 HTML legend」的邏輯，年度圓環圖要重用同一套邏輯，所以先抽成獨立函式，月度、年度共用。

- [ ] **Step 1: 在 `let catChart=null;`（第 653 行）後方新增第二個圖表變數，並新增共用渲染函式**

找到第 653 行：
```js
let catChart=null;
```

改成：
```js
let catChart=null;
let catChartYear=null;
const CAT_COLORS={日常:'#E8735A',房租:'#4F83B5',交通:'#8EA36E',旅遊:'#4B5FA6',娛樂:'#D4618A',教育:'#3A8B4E',醫療:'#B94047',贈與:'#E8A823',長期規劃:'#7B5EA7',貸款:'#475569'};

function renderCategoryChart(canvasId, legendId, chartVar, catMap) {
  const labels=Object.keys(catMap), vals=labels.map(c=>catMap[c]);
  const colors=labels.map(l=>CAT_COLORS[l]||'#64748b');
  const catTotal=vals.reduce((a,b)=>a+b,0);
  if(chartVar.chart) chartVar.chart.destroy();
  chartVar.chart=new Chart(document.getElementById(canvasId),{
    type:'doughnut',
    data:{labels,datasets:[{data:vals,backgroundColor:colors,borderWidth:0}]},
    options:{plugins:{legend:{display:false}},cutout:'62%'}
  });
  document.getElementById(legendId).innerHTML=labels.map((lbl,i)=>`
    <div style="display:flex;align-items:center;justify-content:space-between;padding:5px 0;border-bottom:1px solid #0f172a">
      <div style="display:flex;align-items:center;gap:8px">
        <div style="width:12px;height:12px;border-radius:3px;background:${colors[i]};flex-shrink:0"></div>
        <span style="color:#e2e8f0;font-size:13px;font-weight:500">${lbl}</span>
      </div>
      <span style="color:#e2e8f0;font-size:13px">NT$${vals[i].toLocaleString()} <span style="color:#94a3b8;font-size:12px">(${catTotal>0?(vals[i]/catTotal*100).toFixed(1):0}%)</span></span>
    </div>`).join('');
}
```

（`chartVar` 用一個物件包一層 `{chart: null}` 而不是直接傳變數本身，因為 JS 傳原始變數沒辦法在函式內部重新賦值影響外部變數；用物件的屬性可以做到。）

- [ ] **Step 2: 把 `renderExpenses()` 裡原本的圖表渲染邏輯（第 669-690 行）換成呼叫共用函式**

找到第 669-690 行原本的內容：
```js
  const catMap={};
  txs.forEach(t=>{catMap[t.category]=(catMap[t.category]||0)+t.amount;});
  const labels=Object.keys(catMap), vals=labels.map(c=>catMap[c]);
  // 和色（Japanese traditional colors）
  const CAT_COLORS={日常:'#E8735A',房租:'#4F83B5',交通:'#8EA36E',旅遊:'#4B5FA6',娛樂:'#D4618A',教育:'#3A8B4E',醫療:'#B94047',贈與:'#E8A823',長期規劃:'#7B5EA7',貸款:'#475569'};
  const colors=labels.map(l=>CAT_COLORS[l]||'#64748b');
  const catTotal=vals.reduce((a,b)=>a+b,0);
  if(catChart) catChart.destroy();
  catChart=new Chart(document.getElementById('cat-chart'),{
    type:'doughnut',
    data:{labels,datasets:[{data:vals,backgroundColor:colors,borderWidth:0}]},
    options:{plugins:{legend:{display:false}},cutout:'62%'}
  });
  // Custom HTML legend — Chart.js canvas text color unreliable; use HTML instead
  document.getElementById('cat-legend').innerHTML=labels.map((lbl,i)=>`
    <div style="display:flex;align-items:center;justify-content:space-between;padding:5px 0;border-bottom:1px solid #0f172a">
      <div style="display:flex;align-items:center;gap:8px">
        <div style="width:12px;height:12px;border-radius:3px;background:${colors[i]};flex-shrink:0"></div>
        <span style="color:#e2e8f0;font-size:13px;font-weight:500">${lbl}</span>
      </div>
      <span style="color:#e2e8f0;font-size:13px">NT$${vals[i].toLocaleString()} <span style="color:#94a3b8;font-size:12px">(${catTotal>0?(vals[i]/catTotal*100).toFixed(1):0}%)</span></span>
    </div>`).join('');
```

換成：
```js
  const catMap={};
  txs.forEach(t=>{catMap[t.category]=(catMap[t.category]||0)+t.amount;});
  const catChartRef={get chart(){return catChart;},set chart(v){catChart=v;}};
  renderCategoryChart('cat-chart','cat-legend',catChartRef,catMap);
```

- [ ] **Step 3: 瀏覽器手動驗證月度圖表沒壞**

用 `python3 -m http.server 8080` 在 `finance-app/` 目錄下起一個靜態伺服器，瀏覽器開 `http://localhost:8080`，設定 API URL 指向 `https://jenna-finance.onrender.com`，切到支出頁，確認月度類別圓環圖跟 legend 顯示正常（跟改動前肉眼看起來一致）。

- [ ] **Step 4: Commit**

```bash
git add finance-app/index.html
git commit -m "refactor: extract renderCategoryChart shared by monthly/yearly charts"
```

---

### Task 6: 前端 — 新增年份下拉選單建構函式

**Files:**
- Modify: `finance-app/index.html:636-646`（`buildMonths` 函式後方）

- [ ] **Step 1: 新增 `buildYears` 函式**

在 `finance-app/index.html` 的 `buildMonths` 函式（第 636-646 行）後方插入：

```js
function buildYears(id) {
  const sel=document.getElementById(id);
  if(sel.options.length) return sel.value;
  const nowYear=new Date().getFullYear();
  for(let i=0;i<5;i++){
    const y=String(nowYear-i);
    sel.add(new Option(y,y));
  }
  return sel.value;
}
```

- [ ] **Step 2: Commit**

```bash
git add finance-app/index.html
git commit -m "feat: add buildYears helper for annual selectors"
```

---

### Task 7: 前端 — 支出頁新增年度卡片 HTML + 載入邏輯

**Files:**
- Modify: `finance-app/index.html:194-198`（新增卡片 HTML，插入在既有類別分佈卡片之後）
- Modify: `finance-app/index.html`（`loadExpenses` 函式，第 655-662 行附近，新增 `loadYearlyExpense` 函式）
- Modify: `finance-app/index.html:623-633`（`go()` 函式，切到支出頁時初始化年度選單）

- [ ] **Step 1: 新增 HTML 卡片**

找到第 194-198 行：
```html
  <div class="card">
    <div class="label">類別分佈</div>
    <div class="chart-wrap" style="height:200px"><canvas id="cat-chart"></canvas></div>
    <div id="cat-legend" style="margin-top:12px"></div>
  </div>
```

後方（第 198 行之後、第 199 行 `<div id="tx-list">` 之前）插入：
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

- [ ] **Step 2: 新增 `loadYearlyExpense` 函式**

在 `loadExpenses` 函式（第 655-662 行）後方插入：

```js
let catChartYearRef={get chart(){return catChartYear;},set chart(v){catChartYear=v;}};

async function loadYearlyExpense() {
  if(!API) return;
  const year=buildYears('sel-exp-year');
  try {
    const s=await api(`/finance/summary/year/${year}`);
    document.getElementById('exp-year-total').textContent=`NT$${s.total_expense.toLocaleString()}`;
    renderCategoryChart('cat-chart-year','cat-legend-year',catChartYearRef,s.by_category);
  } catch(e){console.error(e);}
}
```

- [ ] **Step 3: 在 `go()` 函式裡，切到支出頁時觸發年度載入**

找到第 629 行：
```js
  if(tab==='expenses') loadExpenses();
```

改成：
```js
  if(tab==='expenses'){ loadExpenses(); loadYearlyExpense(); }
```

- [ ] **Step 4: 瀏覽器手動驗證**

延續 Task 5 Step 3 的本機靜態伺服器，切到支出頁，確認：
1. 「年度支出」卡片顯示今年度累計支出金額（跟月度總支出數字量級一致，年度應該 ≥ 單月）
2. 圓環圖與 legend 正確顯示今年度各類別佔比
3. 切換年份下拉選單，數字跟著變

- [ ] **Step 5: Commit**

```bash
git add finance-app/index.html
git commit -m "feat: add annual expense breakdown card to expenses tab"
```

---

### Task 8: 前端 — 收入頁新增年度結餘卡片 + 載入邏輯

**Files:**
- Modify: `finance-app/index.html:218-234`（新增卡片 HTML，插入在既有「本月結餘」卡片之後）
- Modify: `finance-app/index.html`（新增 `loadYearlyBalance` 函式）
- Modify: `finance-app/index.html:623-633`（`go()` 函式，切到收入頁時初始化年度選單）

- [ ] **Step 1: 新增 HTML 卡片**

找到第 218-234 行（本月結餘卡片），在其後方（第 234 行 `</div>` 之後、第 235 行 `</div>`（`page-income` 結束標籤）之前）插入：

```html
  <!-- 年度結餘 -->
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

- [ ] **Step 2: 找出現有「本月結餘」的顏色套用邏輯，比照寫法**

先確認既有月度結餘卡片的 `bal-net` 顏色邏輯（正負套色）寫在哪個函式裡：

```bash
grep -n "bal-net\|bal-income\|bal-expense" finance-app/index.html
```

Expected 找到類似：
```js
setEl('bal-income', ...);
setEl('bal-expense', ...);
setEl('bal-net', ...);
setColor('bal-net', balance>=0?'#4ade80':'#f87171');
```

把找到的確切函式名稱與寫法記下來，Step 3 要仿照同一套 `setEl`/`setColor` helper（如果該函式裡有定義局部 `setEl`/`setColor`，年度版本要在自己的函式裡也定義一份，或搬到外層共用——若已有外層共用的 `setEl`/`setColor`（例如 `loadAssets` 裡定義的那組，第 961-962 行），直接沿用即可，不用重複定義）。

- [ ] **Step 3: 新增 `loadYearlyBalance` 函式**

在收入頁相關函式（`loadIncome` 附近）新增：

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

- [ ] **Step 4: 在 `go()` 函式裡，切到收入頁時觸發年度載入**

找到第 630 行：
```js
  else if(tab==='income') loadIncome();
```

改成：
```js
  else if(tab==='income'){ loadIncome(); loadYearlyBalance(); }
```

- [ ] **Step 5: 瀏覽器手動驗證**

切到收入頁，確認：
1. 「年度結餘」卡片顯示今年度收入、支出、結餘三個數字
2. 結餘正負分別套用綠/紅色
3. 切換年份下拉選單，數字跟著變
4. 既有「本月結餘」卡片不受影響，數字維持原本邏輯

- [ ] **Step 6: Commit**

```bash
git add finance-app/index.html
git commit -m "feat: add annual balance card to income tab"
```

---

### Task 9: 前端 — Push 到 monorepo 觸發 Netlify 部署

**Files:** 無新檔案，純部署動作

- [ ] **Step 1: Push**

```bash
git push origin main
```

- [ ] **Step 2: 等 Netlify 自動部署完成後驗證線上內容**

等待約 60-90 秒後執行：

```bash
curl -s https://incandescent-mooncake-3de7e3.netlify.app/ | grep -c "loadYearlyExpense\|loadYearlyBalance"
```

Expected: `2`（兩個函式名稱都出現在線上版本裡，代表新版已部署）

- [ ] **Step 3: 手機／瀏覽器實機驗證**

打開 app，強制重新整理，分別切到支出頁、收入頁，確認年度卡片正常顯示、切換年份正常運作，且既有月度卡片沒有壞掉。

---

## Self-Review 對照 Spec

- ✅ 後端新增 `GET /finance/summary/year/{year}`（Task 1-4）
- ✅ `list_income` 精確比對問題透過新增獨立 `list_income_by_year` 解決，不動原函式（Task 1）
- ✅ 支出頁年度卡片在既有類別分佈卡片下方、交易列表上方（Task 7）
- ✅ 收入頁年度結餘卡片在既有本月結餘卡片下方，另外新增不取代（Task 8）
- ✅ 支出頁、收入頁年度選單各自獨立（`sel-exp-year` / `sel-inc-year`）（Task 6-8）
- ✅ 圓環圖渲染邏輯抽成共用函式，月度/年度復用（Task 5）
- ✅ 各自 try/catch，不阻斷其他區塊渲染（Task 7 Step 2、Task 8 Step 3 皆用獨立 try/catch）
- ✅ 後端 push 到 `jenna-finance`、前端 push 到本 monorepo 的部署路徑差異已在每個 Task 明確標註
