# 家庭旅遊 App（family-trip-template.html）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 從 `japan-trip.html` fork 出 `family-trip-template.html`：拿掉兩人分帳/結算，改成最多 4 人的家庭成員記帳（只記付款人）；幣別從 JPY/TWD 雙選擴充為 JPY/AUD/USD/EUR/TWD 五選；城市從日本城市下拉選單改成自由輸入 + Open-Meteo geocoding 查詢確認；PWA icon 與主色調換成家庭/暖橘風格；作為可重複用於任何目的地的通用模板。

**Architecture:** 單一 HTML 檔 PWA，無 build step，延續 `japan-trip.html` 既有架構（Firebase Realtime Database 同步、Gemini 收據 OCR、Open-Meteo 天氣）。所有修改都在複製出的新檔案內進行，不動 `japan-trip.html` 本體。

**Tech Stack:** 純 HTML/CSS/JS（無 build step），Firebase Realtime Database (compat 9.23)，Gemini API（收據 OCR），Open-Meteo Forecast API（天氣）+ Open-Meteo Geocoding API（城市轉座標，新增），Python3 + Pillow（產生 PWA icon，僅開發時執行一次）。

---

## 背景知識（開始前必讀）

- `family-trip-template.html` 沒有測試框架，驗證一律用 `node --check`（語法）+ 手動在瀏覽器打開檢查。這個 app 需要使用者自己的 Firebase Realtime Database 網址才能跑完整流程（連線、讀寫），計畫裡沒有可用的測試用 Firebase 專案，所以**不做自動化的 Firebase 讀寫驗證**——每個 Task 只驗證語法正確、以及不需要 Firebase 連線就能檢查的部分（例如純函式的輸出、靜態 HTML 結構）。最後 Task 11 會請使用者自己用真實 Firebase 網址跑一次完整驗收。
- 每個 Task 都會修改同一個檔案，前一個 Task 的改動會讓行號往後移。**用 `grep -n` 找程式碼內容比對，不要依賴本文件寫的行號**（本文件裡引用的行號僅來自撰寫計畫當下讀取 `japan-trip.html` 的快照，複製成新檔案後行號不變，但後續 Task 疊加修改後就會偏移）。
- 核心資料流：`CFG` 是存在 `localStorage`（key 待 Task 1 改為 `family_trip`）並回填到 Firebase 各欄位的設定物件；`_fbListen()` 監聽 Firebase `/` 整棵樹，資料變動時呼叫 `renderSched`/`renderExp`/`renderStat`/`renderNotes` 重繪。所有記帳修改（Task 6-8）都要同時處理「新增/編輯支出表單」「行程活動的花費」兩個入口，因為兩者都會寫入 `/expenses/{id}`。

---

## Task 1: Fork 檔案 + 基本文字替換

**Files:**
- Create: `family-trip-template.html`（從 `japan-trip.html` 複製）
- Modify: `family-trip-template.html`

- [ ] **Step 1: 複製檔案**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
cp japan-trip.html family-trip-template.html
wc -l family-trip-template.html
```

Expected: 輸出行數與 `japan-trip.html` 相同（1546 行）。

- [ ] **Step 2: 用 Python 腳本做安全的字串替換**

這些字串在檔案中都是唯一或明確可辨識的位置，用 `str.replace()` 逐一替換，不用正則（避免誤傷 base64 icon 資料裡的巧合字元）：

```bash
python3 - <<'EOF'
path = "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/family-trip-template.html"
s = open(path, encoding='utf-8').read()

replacements = [
    ('<meta name="apple-mobile-web-app-title" content="日本之旅">',
     '<meta name="apple-mobile-web-app-title" content="家庭旅行">'),
    ('<title>日本之旅</title>', '<title>家庭旅行</title>'),
    ('<h1>🇯🇵 日本之旅</h1>', '<h1>🏠 家庭旅行</h1>'),
    ('<p>輸入 Firebase Realtime Database 網址開始</p>',
     '<p>輸入 Firebase Realtime Database 網址開始</p>'),  # unchanged, kept for clarity
    ('<div class="hdr-t" id="appTitle">日本之旅</div>',
     '<div class="hdr-t" id="appTitle">家庭旅行</div>'),
    ("localStorage.setItem('japan_trip',JSON.stringify(CFG));",
     "localStorage.setItem('family_trip',JSON.stringify(CFG));"),
    ("const s=localStorage.getItem('japan_trip');",
     "const s=localStorage.getItem('family_trip');"),
    ("localStorage.removeItem('japan_trip');",
     "localStorage.removeItem('family_trip');"),
]

missing = []
for old, new in replacements:
    if old not in s:
        missing.append(old)
    else:
        s = s.replace(old, new)

if missing:
    raise SystemExit("找不到以下字串，檢查是否措辭跟預期不同：\n" + "\n---\n".join(missing))

open(path, 'w', encoding='utf-8').write(s)
print("OK, replaced", len(replacements), "strings")
EOF
```

Expected: `OK, replaced 8 strings`（`localStorage.setItem('japan_trip'...)` 出現兩處，其中一處在 `doSetup()`、另一處在 `saveCfg()`，上面 replacements 只列出一次 pattern 但 `str.replace` 預設會替換所有出現處，所以兩處都會被改到；`localStorage.getItem`/`removeItem` 各只有一處）。

- [ ] **Step 3: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/family-trip-template.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_family1.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_family1.js && echo OK
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add family-trip-template.html
git commit -m "feat: fork japan-trip.html into family-trip-template.html"
```

---

## Task 2: 幣別擴充為 JPY/AUD/USD/EUR/TWD 五選

**Files:**
- Modify: `family-trip-template.html`（CSS `.cur-row`/`.cr` 區塊）
- Modify: `family-trip-template.html`（記帳表單、活動表單的幣別 HTML）
- Modify: `family-trip-template.html`（JS：新增 `PRESET_CURRENCIES`/`curSym`/`renderCurChips`，重寫 `selCur`/`selACur`，統一所有幣別符號顯示）

- [ ] **Step 1: CSS 改成可換行的通用 chip 樣式**

```bash
grep -n '\.cur-row{' family-trip-template.html
```

找到：

```css
.cur-row{display:flex;background:var(--bg);border-radius:10px;padding:3px;gap:3px;}
.cr{flex:1;padding:9px;text-align:center;border-radius:8px;cursor:pointer;font-size:14px;font-weight:700;color:var(--muted);transition:all .15s;}
.cr.aud.on{background:#fff;color:var(--blue);box-shadow:0 1px 4px rgba(0,0,0,.1);}
.cr.twd.on{background:#fff;color:var(--purple);box-shadow:0 1px 4px rgba(0,0,0,.1);}
```

改成：

```css
.cur-row{display:flex;flex-wrap:wrap;background:var(--bg);border-radius:10px;padding:3px;gap:3px;}
.cr{flex:1 1 30%;min-width:64px;padding:9px 4px;text-align:center;border-radius:8px;cursor:pointer;font-size:13px;font-weight:700;color:var(--muted);transition:all .15s;}
.cr.on{background:#fff;color:var(--blue);box-shadow:0 1px 4px rgba(0,0,0,.1);}
```

- [ ] **Step 2: 幣別徽章（expense list badge）CSS 從雙色改單一樣式**

```bash
grep -n '\.baud{' family-trip-template.html
```

找到：

```css
.baud{background:#E0F2FE;color:#0369A1;}.btwd{background:#EDE9FE;color:#6D28D9;}.bact{background:#D1FAE5;color:#065F46;}
```

改成：

```css
.bcur{background:#E0F2FE;color:#0369A1;}.bact{background:#D1FAE5;color:#065F46;}
```

- [ ] **Step 3: 記帳表單 HTML 幣別區塊改成空容器**

```bash
grep -n 'id="cur-jpy"' family-trip-template.html
```

找到（記帳 modal 內）：

```html
        <div class="cur-row"><div class="cr aud on" id="cur-jpy" onclick="selCur('JPY')">🇯🇵 JPY</div><div class="cr twd" id="cur-twd" onclick="selCur('TWD')">🇹🇼 TWD</div></div>
```

改成：

```html
        <div class="cur-row" id="cur-row-exp"></div>
```

- [ ] **Step 4: 活動表單 HTML 幣別區塊改成空容器**

```bash
grep -n 'id="acur-jpy"' family-trip-template.html
```

找到（活動 modal 內）：

```html
          <div class="cur-row"><div class="cr aud on" id="acur-jpy" onclick="selACur('JPY')">🇯🇵 JPY</div><div class="cr twd" id="acur-twd" onclick="selACur('TWD')">🇹🇼 TWD</div></div>
```

改成：

```html
          <div class="cur-row" id="cur-row-act"></div>
```

- [ ] **Step 5: 新增 `PRESET_CURRENCIES`/`curSym`/`renderCurChips`，重寫 `selCur`/`selACur`**

```bash
grep -n "^const CITIES=" family-trip-template.html
```

在 `const CITIES={...};` 這個宣告**之後**（緊接在它的 `};` 下一行）插入：

```javascript
const PRESET_CURRENCIES=[
  {code:'JPY',flag:'🇯🇵'},{code:'AUD',flag:'🇦🇺'},{code:'USD',flag:'🇺🇸'},
  {code:'EUR',flag:'🇪🇺'},{code:'TWD',flag:'🇹🇼'},
];
function curSym(c){return c==='TWD'?'NT$':c==='JPY'?'¥':c==='EUR'?'€':'$';}
function renderCurChips(containerId,selected,onSelectFn){
  document.getElementById(containerId).innerHTML=PRESET_CURRENCIES.map(c=>
    `<div class="cr ${c.code===selected?'on':''}" onclick="${onSelectFn}('${c.code}')">${c.flag} ${c.code}</div>`
  ).join('');
}
```

接著找到並替換 `selCur`/`selACur`：

```bash
grep -n "^function selCur\|^function selACur" family-trip-template.html
```

原本：

```javascript
function selACur(c){curACur=c;document.getElementById('acur-jpy').classList.toggle('on',c==='JPY');document.getElementById('acur-twd').classList.toggle('on',c==='TWD');}
```
```javascript
function selCur(c){curCur=c;document.getElementById('cur-jpy').classList.toggle('on',c==='JPY');document.getElementById('cur-twd').classList.toggle('on',c==='TWD');}
```

改成：

```javascript
function selACur(c){curACur=c;renderCurChips('cur-row-act',c,'selACur');}
```
```javascript
function selCur(c){curCur=c;renderCurChips('cur-row-exp',c,'selCur');}
```

（既有呼叫 `selCur(...)`/`selACur(...)` 的地方——`openExpM`/`openExpMPrefilled`/`openExpEdit`/`openActM`/`openActEdit`——不用改，因為函式簽章沒變，改成重繪整個 chip 容器只是內部實作換了。）

- [ ] **Step 6: 統一所有「JPY 用 ¥、其他用 NT$」的二元判斷成 `curSym()`**

```bash
grep -n "==='JPY')?'¥':'NT\$'\|==='JPY'?'¥':'NT\$'" family-trip-template.html
```

會找到 4 處（`drawDonut`、`renderPie`、`renderSched` 的 `sChips`、`renderStat` 的 `fmtTotals`、`renderSched` 的 `act-cost` 顯示、expense list 的 `eamt`——實際跑一次上面的 grep 確認完整清單，可能是 5-6 處），每一處都把 `(cur==='JPY')?'¥':'NT$'` 或 `cur==='JPY'?'¥':'NT$'` 這種寫法換成 `curSym(cur)`（變數名依上下文可能是 `cur`/`curPieCur`/`e.cur||'JPY'`，把整個三元運算式换成 `curSym(...)`，括號內放原本三元運算式判斷用的那個運算式）。例如：

```javascript
// 原本
const sym=(cur==='JPY')?'¥':'NT$',dp=0;
// 改成
const sym=curSym(cur),dp=0;
```

```javascript
// 原本（expense list item）
const sym=(e.cur||'JPY')==='JPY'?'¥':'NT$',dp=0;
// 改成
const sym=curSym(e.cur||'JPY'),dp=0;
```

逐一確認每個匹配都替換完，再跑一次同樣的 grep 確認沒有殘留：

```bash
grep -n "==='JPY')?'¥':'NT\$'\|==='JPY'?'¥':'NT\$'" family-trip-template.html
```

Expected: 沒有輸出（全部換成 `curSym`）。

- [ ] **Step 7: 幣別徽章 render 從 `baud/btwd` 改成 `bcur`**

```bash
grep -n "'baud':'btwd'" family-trip-template.html
```

找到：

```javascript
            <span class="bdg ${(e.cur||'JPY')==='JPY'?'baud':'btwd'}">${e.cur||'JPY'}</span>
```

改成：

```javascript
            <span class="bdg bcur">${e.cur||'JPY'}</span>
```

- [ ] **Step 8: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/family-trip-template.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_family2.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_family2.js && echo OK
```

Expected: `OK`

- [ ] **Step 9: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add family-trip-template.html
git commit -m "feat: expand currency chips to JPY/AUD/USD/EUR/TWD"
```

---

## Task 3: 收據掃描幣別辨識改多幣別

**Files:**
- Modify: `family-trip-template.html`（`RECEIPT_PROMPT`）
- Modify: `family-trip-template.html`（`openExpMPrefilled` 幣別 fallback/驗證）

- [ ] **Step 1: `RECEIPT_PROMPT` 從「固定填 JPY」改成五選一辨識**

```bash
grep -n "^const RECEIPT_PROMPT=" family-trip-template.html
```

找到：

```javascript
const RECEIPT_PROMPT=`你是日本收據辨識助手。請分析這張收據圖片，回傳 JSON 格式，欄位如下：
- store: 店名字串（看不清填空字串）
- amount: 含稅總金額（日圓整數，日本收據有外税8%/10%與内税，取最終合計金額）
- currency: 固定填 "JPY"
- category: 從 food/transport/hotel/shopping/ticket/activity 選一個最符合的
- date: 收據日期 YYYY-MM-DD（看不清填今天日期）
只輸出 JSON 物件，不加任何說明文字。`;
```

改成：

```javascript
const RECEIPT_PROMPT=`你是收據辨識助手。請分析這張收據圖片，回傳 JSON 格式，欄位如下：
- store: 店名字串（看不清填空字串）
- amount: 含稅總金額數字（取收據上最終合計金額）
- currency: 從 JPY/AUD/USD/EUR/TWD 五選一，依收據上的幣別符號或文字判斷；無法判斷則填 "TWD"
- category: 從 food/transport/hotel/shopping/ticket/activity 選一個最符合的
- date: 收據日期 YYYY-MM-DD（看不清填今天日期）
只輸出 JSON 物件，不加任何說明文字。`;
```

- [ ] **Step 2: `openExpMPrefilled` 驗證 Gemini 回傳的幣別，非五碼之一時 fallback 到 TWD**

```bash
grep -n "selCur(data.currency" family-trip-template.html
```

找到：

```javascript
  curCat=cat;renderCatGrid();selPayer(0);selSplit('both');selCur(data.currency||'JPY');
```

改成：

```javascript
  const safeCur=PRESET_CURRENCIES.some(c=>c.code===data.currency)?data.currency:'TWD';
  curCat=cat;renderCatGrid();selPayer(0);selSplit('both');selCur(safeCur);
```

（`selSplit('both')` 這段是分帳邏輯殘留，會在後面「移除分帳/結算邏輯」的 Task 一起拿掉，這裡先不用管它，只改幣別 fallback 那一小段。）

- [ ] **Step 3: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/family-trip-template.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_family2b.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_family2b.js && echo OK
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add family-trip-template.html
git commit -m "feat: multi-currency receipt OCR recognition"
```

---

## Task 4: 多幣別匯率 lazy fetch

**Files:**
- Modify: `family-trip-template.html`（`fetchRate` → `exchRates` map + `fetchRateFor`/`ensureRatesForExpenses`）
- Modify: `family-trip-template.html`（`bootApp`、`_fbListen` 呼叫點）

- [ ] **Step 1: 找到現有的單一匯率抓取邏輯**

```bash
grep -n "let exchRate\|async function fetchRate" family-trip-template.html
```

會看到：

```javascript
let curNT='text',curImg=null,curPieCur='JPY',lastExps={},lastNotes={},exchRate=null,curActImages=[];
```

以及：

```javascript
async function fetchRate(){
  try{
    const r=await fetch('https://open.er-api.com/v6/latest/JPY');
    const d=await r.json();
    if(d.result==='success'&&d.rates?.TWD){
      exchRate=d.rates.TWD;
      const el=document.getElementById('pieRate');
      if(el)el.textContent=`即時匯率 1 JPY ≈ NT$${exchRate.toFixed(4)}（台灣銀行參考）`;
    }
  }catch(e){exchRate=null;}
}
```

- [ ] **Step 2: 拿掉 `exchRate` 全域變數，改成 `exchRates` map**

把：

```javascript
let curNT='text',curImg=null,curPieCur='JPY',lastExps={},lastNotes={},exchRate=null,curActImages=[];
```

改成：

```javascript
let curNT='text',curImg=null,curPieCur='JPY',lastExps={},lastNotes={},exchRates={},curActImages=[];
const FALLBACK_RATES={JPY:0.21,AUD:21,USD:32,EUR:35};
const _ratesFetching=new Set();
```

- [ ] **Step 3: 把 `fetchRate()` 換成 `fetchRateFor(cur)` + `ensureRatesForExpenses(exps)`**

把整個 `async function fetchRate(){...}` 換成：

```javascript
async function fetchRateFor(cur){
  if(cur==='TWD'||exchRates[cur]!=null||_ratesFetching.has(cur))return;
  _ratesFetching.add(cur);
  try{
    const r=await fetch(`https://open.er-api.com/v6/latest/${cur}`);
    const d=await r.json();
    if(d.result==='success'&&d.rates?.TWD)exchRates[cur]=d.rates.TWD;
  }catch(e){/* 靜默失敗，drawDonut 會用 FALLBACK_RATES */}
  _ratesFetching.delete(cur);
}
function ensureRatesForExpenses(exps){
  const used=new Set(Object.values(exps).map(e=>e.cur||'JPY').filter(c=>c!=='TWD'));
  return Promise.all([...used].map(fetchRateFor));
}
function rateFor(cur){return exchRates[cur]??FALLBACK_RATES[cur]??1;}
```

- [ ] **Step 4: 更新呼叫點——`bootApp()` 不再一次性 `fetchRate()`**

```bash
grep -n "fetchRate();" family-trip-template.html
```

找到：

```javascript
  renderCatGrid();renderACGrid();initDnD();initActDnD();
  fetchRate();
  loadFirebase(()=>fetchWeather().finally(()=>connectFB()));
```

改成（拿掉 `fetchRate();` 這一行，改成註解交代改由 `_fbListen` 依實際資料觸發）：

```javascript
  renderCatGrid();renderACGrid();initDnD();initActDnD();
  // 匯率改成 lazy fetch：由 _fbListen() 收到 expenses 資料後依實際用到的幣別呼叫
  loadFirebase(()=>fetchWeather().finally(()=>connectFB()));
```

- [ ] **Step 5: `_fbListen()` 收到資料後觸發匯率抓取並在完成後重繪統計**

```bash
grep -n "lastExps=d.expenses" family-trip-template.html
```

找到：

```javascript
    lastExps=d.expenses||{};
    lastNotes=d.notes||{};
    renderSched(sched);
    renderExp(lastExps);
    renderStat(lastExps);
    renderNotes(lastNotes);
    sync(false);
```

改成：

```javascript
    lastExps=d.expenses||{};
    lastNotes=d.notes||{};
    renderSched(sched);
    renderExp(lastExps);
    renderStat(lastExps);
    renderNotes(lastNotes);
    sync(false);
    ensureRatesForExpenses(lastExps).then(()=>{if(curTab==='exp'&&curAcc==='stat')renderStat(lastExps);});
```

- [ ] **Step 6: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/family-trip-template.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_family3.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_family3.js && echo OK
```

Expected: `OK`（此時 `drawDonut`/`renderPie` 還在用舊的 `exchRate` 單一變數，語法仍合法但邏輯會在 Task 5 修正，先不用管）

- [ ] **Step 7: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add family-trip-template.html
git commit -m "feat: lazy multi-currency exchange rate fetching"
```

---

## Task 5: 圓餅圖幣別分頁與合計換算改多幣別

**Files:**
- Modify: `family-trip-template.html`（`drawDonut`、`renderPie`）

- [ ] **Step 1: 找到現有的二元 JPY/TWD 邏輯**

```bash
grep -n "^function drawDonut\|^function renderPie" family-trip-template.html
```

- [ ] **Step 2: `drawDonut` 改用 `rateFor()` 處理任意幣別的 combined 換算**

找到：

```javascript
function drawDonut(canvasId,exps,cur){
  const canvas=document.getElementById(canvasId);if(!canvas)return null;
  const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height;
  ctx.clearRect(0,0,w,h);
  const rate=exchRate||21.5,isCombined=cur==='combined';
  const totals={};
  Object.values(exps).forEach(e=>{
    if(!isCombined&&(e.cur||'JPY')!==cur)return;
    const cat=e.cat||'other';
    let amt=e.amt||0;
    if(isCombined)amt=(e.cur==='TWD')?amt:amt*rate;
    totals[cat]=(totals[cat]||0)+amt;
  });
```

改成：

```javascript
function drawDonut(canvasId,exps,cur){
  const canvas=document.getElementById(canvasId);if(!canvas)return null;
  const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height;
  ctx.clearRect(0,0,w,h);
  const isCombined=cur==='combined';
  const totals={};
  Object.values(exps).forEach(e=>{
    const eCur=e.cur||'JPY';
    if(!isCombined&&eCur!==cur)return;
    const cat=e.cat||'other';
    let amt=e.amt||0;
    if(isCombined)amt=(eCur==='TWD')?amt:amt*rateFor(eCur);
    totals[cat]=(totals[cat]||0)+amt;
  });
```

再往下找同一函式內的符號顯示：

```bash
grep -n "const sym=(cur==='JPY')?'¥':'NT\$',dp=0;" family-trip-template.html
```

（這行在 Task 2 Step 6 應該已經被換成 `curSym(cur)`；`drawDonut` 裡 `cur` 可能是 `'combined'`，`curSym('combined')` 會落到 `'$'` 分支，不正確。）找到 `drawDonut` 內那一行：

```javascript
  const sym=curSym(cur),dp=0;
  const dispTotal=isCombined?total.toFixed(0):total.toFixed(dp);
```

改成：

```javascript
  const sym=isCombined?'NT$':curSym(cur),dp=0;
  const dispTotal=isCombined?total.toFixed(0):total.toFixed(dp);
```

- [ ] **Step 3: `renderPie` 幣別分頁從二元改成迴圈**

找到：

```javascript
function renderPie(exps){
  const hasJPY=Object.values(exps).some(e=>(e.cur||'JPY')==='JPY'&&(e.amt||0)>0);
  const hasTWD=Object.values(exps).some(e=>e.cur==='TWD'&&(e.amt||0)>0);
  if(!hasJPY&&!hasTWD){document.getElementById('pieSec').innerHTML='';return;}

  // Ensure curPieCur is valid
  if(curPieCur==='JPY'&&!hasJPY)curPieCur=hasTWD?'TWD':'combined';
  if(curPieCur==='TWD'&&!hasTWD)curPieCur=hasJPY?'JPY':'combined';

  const tabs=[];
  if(hasJPY)tabs.push({k:'JPY',label:'🇯🇵 JPY',cls:''});
  if(hasTWD)tabs.push({k:'TWD',label:'🇹🇼 TWD',cls:'twd'});
  if(hasJPY&&hasTWD)tabs.push({k:'combined',label:'合計(TWD)',cls:'twd'});
```

改成：

```javascript
function renderPie(exps){
  const presentCurs=PRESET_CURRENCIES.filter(c=>Object.values(exps).some(e=>(e.cur||'JPY')===c.code&&(e.amt||0)>0));
  if(!presentCurs.length){document.getElementById('pieSec').innerHTML='';return;}

  // Ensure curPieCur is valid
  if(curPieCur!=='combined'&&!presentCurs.some(c=>c.code===curPieCur)){
    curPieCur=presentCurs[0].code;
  }

  const tabs=presentCurs.map(c=>({k:c.code,label:`${c.flag} ${c.code}`,cls:''}));
  if(presentCurs.length>1)tabs.push({k:'combined',label:'合計(TWD)',cls:'twd'});
```

- [ ] **Step 4: `pieRate` 提示文字改列出目前用到的幣別匯率**

```bash
grep -n "pie-rate" family-trip-template.html
```

找到（`renderPie` 內組出 HTML 的地方）：

```javascript
    <div class="pie-rate" id="pieRate">${exchRate?`即時匯率 1 JPY ≈ NT$${exchRate.toFixed(4)}（台灣銀行參考）`:''}</div>
```

改成：

```javascript
    <div class="pie-rate" id="pieRate">${presentCurs.filter(c=>c.code!=='TWD'&&exchRates[c.code]).map(c=>`1 ${c.code}≈NT$${exchRates[c.code].toFixed(c.code==='JPY'?4:2)}`).join(' · ')}</div>
```

- [ ] **Step 5: `switchPie` 不用改（已經是通用的 `curPieCur=cur;renderPie(lastExps);`），確認一下**

```bash
grep -n "^function switchPie" family-trip-template.html
```

Expected: `function switchPie(cur){curPieCur=cur;renderPie(lastExps);}` — 維持原樣，不用修改。

- [ ] **Step 6: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/family-trip-template.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_family4.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_family4.js && echo OK
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add family-trip-template.html
git commit -m "feat: generalize pie chart currency tabs to N currencies"
```

---

## Task 6: `CFG.members[]` 資料模型 + 動態付款人選擇器

這是最大的一個 Task，把寫死的 `p1`/`p2` 換成最多 4 人的 `CFG.members` 陣列，同時把付款人選擇器（記帳表單、活動表單各一個）改成依實際成員數量動態產生。

**Files:**
- Modify: `family-trip-template.html`（Setup / Settings 表單 HTML）
- Modify: `family-trip-template.html`（付款人選擇器 HTML → 空容器）
- Modify: `family-trip-template.html`（CSS `.pb`）
- Modify: `family-trip-template.html`（JS：`doSetup`、`bootApp`、`saveCfg`、新增 `renderPayerPicker`、`selPayer`、`selAPayer`、`openActM`/`openActEdit`/`openExpM`/`openExpMPrefilled`/`openExpEdit`、`saveExp`/`saveAct`/`moveAct`）

- [ ] **Step 1: Setup 畫面 HTML — 旅伴 1/2 換成成員 1-4**

```bash
grep -n 'id="s_p1"' family-trip-template.html
```

找到：

```html
    <div class="fr">
      <div class="fg"><label class="lb">旅伴 1</label><input class="inp" id="s_p1" value="瑜" placeholder="Jenna"></div>
      <div class="fg"><label class="lb">旅伴 2</label><input class="inp" id="s_p2" value="然" placeholder="男友"></div>
    </div>
```

改成：

```html
    <div class="fr">
      <div class="fg"><label class="lb">成員 1</label><input class="inp" id="s_m1" placeholder="爸爸"></div>
      <div class="fg"><label class="lb">成員 2</label><input class="inp" id="s_m2" placeholder="媽媽"></div>
    </div>
    <div class="fr">
      <div class="fg"><label class="lb">成員 3（選填）</label><input class="inp" id="s_m3" placeholder="小明"></div>
      <div class="fg"><label class="lb">成員 4（選填）</label><input class="inp" id="s_m4" placeholder="小美"></div>
    </div>
```

- [ ] **Step 2: Settings 畫面 HTML 同步改**

```bash
grep -n 'id="c_p1"' family-trip-template.html
```

找到：

```html
          <div class="fr">
            <div class="fg"><label class="lb">旅伴 1</label><input class="inp" id="c_p1"></div>
            <div class="fg"><label class="lb">旅伴 2</label><input class="inp" id="c_p2"></div>
          </div>
```

改成：

```html
          <div class="fr">
            <div class="fg"><label class="lb">成員 1</label><input class="inp" id="c_m1"></div>
            <div class="fg"><label class="lb">成員 2</label><input class="inp" id="c_m2"></div>
          </div>
          <div class="fr">
            <div class="fg"><label class="lb">成員 3（選填）</label><input class="inp" id="c_m3"></div>
            <div class="fg"><label class="lb">成員 4（選填）</label><input class="inp" id="c_m4"></div>
          </div>
```

- [ ] **Step 3: 付款人選擇器 HTML 改成空容器（記帳表單 + 活動表單）**

```bash
grep -n 'id="apb1"\|id="pb1"' family-trip-template.html
```

活動表單找到：

```html
      <div class="fg"><label class="lb">誰付</label><div class="pr"><div class="pb p1" id="apb1" onclick="selAPayer(0)"></div><div class="pb p2" id="apb2" onclick="selAPayer(1)"></div></div></div>
```

改成：

```html
      <div class="fg"><label class="lb">誰付</label><div class="pr" id="payer-row-act"></div></div>
```

記帳表單找到：

```html
    <div class="fg"><label class="lb">誰付錢</label><div class="pr"><div class="pb p1" id="pb1" onclick="selPayer(0)"></div><div class="pb p2" id="pb2" onclick="selPayer(1)"></div></div></div>
```

改成：

```html
    <div class="fg"><label class="lb">誰付錢</label><div class="pr" id="payer-row-exp"></div></div>
```

- [ ] **Step 4: CSS `.pb` 從雙色改單一樣式**

```bash
grep -n '\.pb\.p1\.on' family-trip-template.html
```

找到：

```css
.pb{flex:1;padding:11px;border-radius:10px;border:2px solid var(--border);background:#fff;text-align:center;cursor:pointer;font-size:14px;font-weight:600;transition:all .12s;}
.pb.p1.on{border-color:#3B82F6;background:#DBEAFE;color:#1D4ED8;}
.pb.p2.on{border-color:#EC4899;background:#FCE7F3;color:#BE185D;}
```

改成：

```css
.pb{flex:1;padding:11px;border-radius:10px;border:2px solid var(--border);background:#fff;text-align:center;cursor:pointer;font-size:14px;font-weight:600;transition:all .12s;}
.pb.on{border-color:var(--blue);background:#EDF3F6;color:var(--blue2);}
```

- [ ] **Step 5: 拿掉 `.bp1`/`.bp2` 徽章樣式（Task 2 Step 2 已把幣別徽章換成 `.bcur`，這裡是另一組——付款人徽章——會在 Task 7 一起清掉分帳相關 UI，這步先跳過不用改，留到 Task 7）**

（no-op，僅記錄：`.bp1`/`.bp2` 會在 Task 7 Step 出現時一併刪除，這裡先不動，避免這個 Task 改動範圍過大。）

- [ ] **Step 6: 新增 `renderPayerPicker`，放在 `renderCurChips` 定義之後**

```bash
grep -n "^function renderCurChips" family-trip-template.html
```

在它的結尾 `}` 之後插入：

```javascript
function renderPayerPicker(containerId,selectedIdx,onSelectFn){
  document.getElementById(containerId).innerHTML=CFG.members.map((name,i)=>
    `<div class="pb ${i===selectedIdx?'on':''}" onclick="${onSelectFn}(${i})">${esc(name)}</div>`
  ).join('');
}
```

- [ ] **Step 7: `selPayer`/`selAPayer` 改成呼叫 `renderPayerPicker`**

```bash
grep -n "^function selPayer\|^function selAPayer" family-trip-template.html
```

原本：

```javascript
function selAPayer(i){curAPayer=i;document.getElementById('apb1').classList.toggle('on',i===0);document.getElementById('apb2').classList.toggle('on',i===1);}
```
```javascript
function selPayer(i){curPayer=i;document.getElementById('pb1').classList.toggle('on',i===0);document.getElementById('pb2').classList.toggle('on',i===1);}
```

改成：

```javascript
function selAPayer(i){curAPayer=i;renderPayerPicker('payer-row-act',i,'selAPayer');}
```
```javascript
function selPayer(i){curPayer=i;renderPayerPicker('payer-row-exp',i,'selPayer');}
```

- [ ] **Step 8: `doSetup()` 建立 `CFG.members` 陣列，拿掉 `p1`/`p2`**

```bash
grep -n "^function doSetup" family-trip-template.html
```

找到：

```javascript
function doSetup(){
  const url=document.getElementById('s_url').value.trim();
  if(!url){alert('請輸入 Firebase 資料庫網址');return;}
  const city=document.getElementById('s_city').value||'東京';
  const coords=CITIES[city]||{lat:35.68,lng:139.69};
  CFG={url,title:document.getElementById('s_title').value.trim()||'岡山倉敷之旅',
    p1:document.getElementById('s_p1').value.trim()||'瑜',
    p2:document.getElementById('s_p2').value.trim()||'然',
    start:document.getElementById('s_start').value||today(),
    days:parseInt(document.getElementById('s_days').value)||7,
    photo:document.getElementById('s_photo').value.trim(),
    city,lat:coords.lat,lng:coords.lng,
    geminiKey:document.getElementById('s_gemini').value.trim()};
  localStorage.setItem('family_trip',JSON.stringify(CFG));
  bootApp();
}
```

改成（城市/geocoding 的部分先維持原本 `CITIES`/`s_city` 邏輯，Task 9 才會整個換掉——這裡先只處理 members）：

```javascript
function doSetup(){
  const url=document.getElementById('s_url').value.trim();
  if(!url){alert('請輸入 Firebase 資料庫網址');return;}
  const members=['s_m1','s_m2','s_m3','s_m4'].map(id=>document.getElementById(id).value.trim()).filter(Boolean);
  if(members.length<2){alert('請至少填寫 2 位成員');return;}
  const city=document.getElementById('s_city').value||'東京';
  const coords=CITIES[city]||{lat:35.68,lng:139.69};
  CFG={url,title:document.getElementById('s_title').value.trim()||'家庭旅行',
    members,
    start:document.getElementById('s_start').value||today(),
    days:parseInt(document.getElementById('s_days').value)||7,
    photo:document.getElementById('s_photo').value.trim(),
    city,lat:coords.lat,lng:coords.lng,
    geminiKey:document.getElementById('s_gemini').value.trim()};
  localStorage.setItem('family_trip',JSON.stringify(CFG));
  bootApp();
}
```

- [ ] **Step 9: `bootApp()` 拿掉 p1/p2 相關 DOM 寫入，改成 members 表單回填**

```bash
grep -n "^function bootApp" family-trip-template.html
```

找到：

```javascript
function bootApp(){
  document.getElementById('setup').style.display='none';
  const app=document.getElementById('app');app.style.display='flex';
  document.getElementById('appTitle').textContent=CFG.title;
  ['pb1','apb1'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=CFG.p1;});
  ['pb2','apb2'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=CFG.p2;});
  document.getElementById('sp-p1').textContent=CFG.p1+'自付';
  document.getElementById('sp-p2').textContent=CFG.p2+'自付';
  document.getElementById('asp-p1').textContent=CFG.p1+'自付';
  document.getElementById('asp-p2').textContent=CFG.p2+'自付';
  document.getElementById('c_title').value=CFG.title;
  document.getElementById('c_p1').value=CFG.p1;document.getElementById('c_p2').value=CFG.p2;
  document.getElementById('c_start').value=CFG.start;document.getElementById('c_days').value=CFG.days;
  document.getElementById('c_url').value=CFG.url;
  document.getElementById('c_photo').value=CFG.photo||'';
  document.getElementById('c_city').value=CFG.city||'東京';
  document.getElementById('c_gemini').value=CFG.geminiKey||'';
  const ph=document.getElementById('hdrPhoto');
  if(CFG.photo){ph.src=CFG.photo;ph.style.display='';}else{ph.style.display='none';}
  renderCatGrid();renderACGrid();initDnD();initActDnD();
  // 匯率改成 lazy fetch：由 _fbListen() 收到 expenses 資料後依實際用到的幣別呼叫
  loadFirebase(()=>fetchWeather().finally(()=>connectFB()));
}
```

改成（拿掉 `sp-p1`/`sp-p2`/`asp-p1`/`asp-p2` 這四行——那是分攤 UI 文字，Task 7 才會刪掉對應的 HTML，這裡先拿掉寫入避免 `getElementById(...)` 回傳 `null` 炸掉；`pb1`/`apb1` 那兩行也拿掉，因為付款人按鈕已經是動態渲染，不用在 `bootApp` 裡手動塞文字）：

```javascript
function bootApp(){
  document.getElementById('setup').style.display='none';
  const app=document.getElementById('app');app.style.display='flex';
  document.getElementById('appTitle').textContent=CFG.title;
  document.getElementById('c_title').value=CFG.title;
  [1,2,3,4].forEach(i=>{document.getElementById('c_m'+i).value=CFG.members[i-1]||'';});
  document.getElementById('c_start').value=CFG.start;document.getElementById('c_days').value=CFG.days;
  document.getElementById('c_url').value=CFG.url;
  document.getElementById('c_photo').value=CFG.photo||'';
  document.getElementById('c_city').value=CFG.city||'東京';
  document.getElementById('c_gemini').value=CFG.geminiKey||'';
  const ph=document.getElementById('hdrPhoto');
  if(CFG.photo){ph.src=CFG.photo;ph.style.display='';}else{ph.style.display='none';}
  renderCatGrid();renderACGrid();initDnD();initActDnD();
  // 匯率改成 lazy fetch：由 _fbListen() 收到 expenses 資料後依實際用到的幣別呼叫
  loadFirebase(()=>fetchWeather().finally(()=>connectFB()));
}
```

- [ ] **Step 10: `openActM`/`openActEdit`/`openExpM`/`openExpMPrefilled`/`openExpEdit` 的付款人索引改用 `CFG.members.indexOf(...)`**

```bash
grep -n "selAPayer(a.cost?.paidBy===CFG.p2?1:0)\|selPayer(e.paidBy===CFG.p2?1:0)" family-trip-template.html
```

找到（`openActEdit` 內）：

```javascript
    selACur(a.cost?.cur||'JPY');selAPayer(a.cost?.paidBy===CFG.p2?1:0);selASplit(a.cost?.split||'both');
```

改成（`selASplit` 的部分留到 Task 7 處理，這裡只改付款人索引；`Math.max(0,...)` 防呆是因為如果存的付款人名字已經被從成員清單移除，`indexOf` 會回傳 -1）：

```javascript
    selACur(a.cost?.cur||'JPY');selAPayer(Math.max(0,CFG.members.indexOf(a.cost?.paidBy)));selASplit(a.cost?.split||'both');
```

找到（`openExpEdit` 內）：

```javascript
    curCat=e.cat||'food';renderCatGrid();selPayer(e.paidBy===CFG.p2?1:0);selSplit(e.split||'both');selCur(e.cur||'JPY');
```

改成：

```javascript
    curCat=e.cat||'food';renderCatGrid();selPayer(Math.max(0,CFG.members.indexOf(e.paidBy)));selSplit(e.split||'both');selCur(e.cur||'JPY');
```

其餘呼叫 `selPayer(0)`/`selAPayer(0)` 的地方（`openActM`、`openExpM`、`openExpMPrefilled`）不用改，預設選第一位成員本來就是索引 0。

- [ ] **Step 11: `saveExp`/`saveAct`/`moveAct` 的 `paidBy` 改用 `CFG.members[curPayer]`**

```bash
grep -n "curPayer===0?CFG.p1:CFG.p2\|curAPayer===0?CFG.p1:CFG.p2" family-trip-template.html
```

會找到 3 處（`saveAct` 的 `cost` 物件、`saveAct` 的 `expenses` 寫入、`saveExp`），全部把：

```javascript
curAPayer===0?CFG.p1:CFG.p2
```

換成：

```javascript
CFG.members[curAPayer]
```

把：

```javascript
curPayer===0?CFG.p1:CFG.p2
```

換成：

```javascript
CFG.members[curPayer]
```

`moveAct` 裡的 `paidBy:act.cost.paidBy||CFG.p1` 也要改：

```bash
grep -n "paidBy:act.cost.paidBy||CFG.p1" family-trip-template.html
```

改成：

```javascript
paidBy:act.cost.paidBy||CFG.members[0]
```

- [ ] **Step 12: `saveCfg()` 儲存 members，拿掉 p1/p2 相關 DOM 更新**

```bash
grep -n "^function saveCfg" family-trip-template.html
```

找到：

```javascript
function saveCfg(){
  CFG.title=document.getElementById('c_title').value.trim()||CFG.title;
  CFG.p1=document.getElementById('c_p1').value.trim()||CFG.p1;
  CFG.p2=document.getElementById('c_p2').value.trim()||CFG.p2;
  const newStart=document.getElementById('c_start').value||CFG.start;
  const dateChanged=newStart!==CFG.start;
  CFG.start=newStart;CFG.days=parseInt(document.getElementById('c_days').value)||CFG.days;
  CFG.photo=document.getElementById('c_photo').value.trim();
  const newCity=document.getElementById('c_city').value||CFG.city;
  if(newCity!==CFG.city){CFG.city=newCity;const coords=CITIES[newCity]||{lat:35.68,lng:139.69};CFG.lat=coords.lat;CFG.lng=coords.lng;}
  CFG.geminiKey=document.getElementById('c_gemini').value.trim()||CFG.geminiKey;
  const ph=document.getElementById('hdrPhoto');
  if(CFG.photo){ph.src=CFG.photo;ph.style.display='';}else{ph.style.display='none';}
  localStorage.setItem('family_trip',JSON.stringify(CFG));
  document.getElementById('appTitle').textContent=CFG.title;
  ['pb1','apb1'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=CFG.p1;});
  ['pb2','apb2'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=CFG.p2;});
  document.getElementById('sp-p1').textContent=CFG.p1+'自付';document.getElementById('sp-p2').textContent=CFG.p2+'自付';
  document.getElementById('asp-p1').textContent=CFG.p1+'自付';document.getElementById('asp-p2').textContent=CFG.p2+'自付';
  if(dateChanged)fixDates(false);
  toast('✅ 設定已儲存'+(dateChanged?' · 行程日期已更新':''));
}
```

改成（城市那段先維持原樣，Task 9 才會整個換掉）：

```javascript
function saveCfg(){
  CFG.title=document.getElementById('c_title').value.trim()||CFG.title;
  const newMembers=['c_m1','c_m2','c_m3','c_m4'].map(id=>document.getElementById(id).value.trim()).filter(Boolean);
  if(newMembers.length<2){toast('⚠️ 至少需要 2 位成員，未更新成員名單');}else{CFG.members=newMembers;}
  const newStart=document.getElementById('c_start').value||CFG.start;
  const dateChanged=newStart!==CFG.start;
  CFG.start=newStart;CFG.days=parseInt(document.getElementById('c_days').value)||CFG.days;
  CFG.photo=document.getElementById('c_photo').value.trim();
  const newCity=document.getElementById('c_city').value||CFG.city;
  if(newCity!==CFG.city){CFG.city=newCity;const coords=CITIES[newCity]||{lat:35.68,lng:139.69};CFG.lat=coords.lat;CFG.lng=coords.lng;}
  CFG.geminiKey=document.getElementById('c_gemini').value.trim()||CFG.geminiKey;
  const ph=document.getElementById('hdrPhoto');
  if(CFG.photo){ph.src=CFG.photo;ph.style.display='';}else{ph.style.display='none';}
  localStorage.setItem('family_trip',JSON.stringify(CFG));
  document.getElementById('appTitle').textContent=CFG.title;
  if(dateChanged)fixDates(false);
  toast('✅ 設定已儲存'+(dateChanged?' · 行程日期已更新':''));
}
```

（如果某個既有 `curPayer`/`curAPayer` 選到的索引，在成員名單縮減後超出新的 `CFG.members.length`，下次打開表單時 `renderPayerPicker` 只會畫出目前 `CFG.members` 長度的按鈕，`selectedIdx` 對不到任何按鈕也不會報錯，只是沒有按鈕顯示選中狀態——可接受的邊界情況，不特別處理。）

- [ ] **Step 13: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/family-trip-template.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_family5.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_family5.js && echo OK
```

Expected: `OK`

- [ ] **Step 14: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add family-trip-template.html
git commit -m "feat: replace fixed p1/p2 with CFG.members[] and dynamic payer picker"
```

---

## Task 7: 移除分帳/結算邏輯

**Files:**
- Modify: `family-trip-template.html`（HTML：拿掉「分攤方式」UI 區塊）
- Modify: `family-trip-template.html`（CSS：拿掉 `.bc-*`/`.twd-row`/`.bp1`/`.bp2`）
- Modify: `family-trip-template.html`（JS：拿掉 `curSplit`/`curASplit`/`selSplit`/`selASplit`/`calcBal`，`saveExp`/`saveAct`/`moveAct` 拿掉 `split` 欄位，`renderExp` 拿掉 balance 卡片與 split 標籤）

- [ ] **Step 1: 拿掉記帳表單「分攤方式」HTML**

```bash
grep -n 'id="sp-both"' family-trip-template.html
```

找到：

```html
    <div class="fg"><label class="lb">分攤方式</label>
      <div class="tw"><div class="to on" id="sp-both" onclick="selSplit('both')">兩人均分</div><div class="to" id="sp-p1" onclick="selSplit('p1')"></div><div class="to" id="sp-p2" onclick="selSplit('p2')"></div></div>
    </div>
```

整段刪除。

- [ ] **Step 2: 拿掉活動表單「分攤」HTML**

```bash
grep -n 'id="asp-both"' family-trip-template.html
```

找到：

```html
      <div class="fg" style="margin-bottom:0"><label class="lb">分攤</label>
        <div class="tw"><div class="to on" id="asp-both" onclick="selASplit('both')">均分</div><div class="to" id="asp-p1" onclick="selASplit('p1')"></div><div class="to" id="asp-p2" onclick="selASplit('p2')"></div></div>
      </div>
```

整段刪除。

- [ ] **Step 3: 拿掉 `balSec` 容器**

```bash
grep -n 'id="balSec"' family-trip-template.html
```

找到：

```html
        <div id="expContent">
          <div id="balSec"></div>
          <div id="expList"></div>
        </div>
```

改成：

```html
        <div id="expContent">
          <div id="expList"></div>
        </div>
```

- [ ] **Step 4: CSS 拿掉分帳相關樣式**

```bash
grep -n '\.bc-card\|\.bc-row\|\.bc-flag\|\.bc-tot\|\.bc-ps\|\.bc-settle\|\.twd-row' family-trip-template.html
```

找到並整段刪除：

```css
/* Expenses – compact balance */
.bc-card{background:linear-gradient(135deg,var(--blue2),var(--cyan));border-radius:12px;padding:14px 16px;margin-bottom:8px;color:#fff;}
.bc-row{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:13px;}
.bc-row+.bc-row{margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,.2);}
.bc-flag{font-size:14px;font-weight:700;}
.bc-tot{font-size:18px;font-weight:800;margin-left:6px;}
.bc-ps{font-size:11px;opacity:.75;margin-top:2px;}
.bc-settle{font-size:12px;font-weight:700;background:rgba(255,255,255,.15);padding:3px 8px;border-radius:20px;white-space:nowrap;}
.bc-settle.ok{background:rgba(16,185,129,.25);}
.twd-row{background:linear-gradient(135deg,var(--purple),#B8AACC);}
```

- [ ] **Step 5: CSS 拿掉 `.bp1`/`.bp2`（付款人徽章雙色樣式，Task 6 Step 5 有標記留到這裡處理）**

```bash
grep -n '\.bp1{' family-trip-template.html
```

找到：

```css
.bp1{background:#DBEAFE;color:#1D4ED8;}.bp2{background:#FCE7F3;color:#BE185D;}
```

改成（統一成單一付款人徽章樣式）：

```css
.bpayer{background:#DBEAFE;color:#1D4ED8;}
```

- [ ] **Step 6: JS 拿掉 `curSplit`/`curASplit` 變數**

```bash
grep -n "curCat='food',curPayer=0,curSplit='both'\|curAC='sight',curACur='JPY',curAPayer=0,curASplit='both'" family-trip-template.html
```

找到：

```javascript
let curCat='food',curPayer=0,curSplit='both',curCur='JPY';
let curAC='sight',curACur='JPY',curAPayer=0,curASplit='both';
```

改成：

```javascript
let curCat='food',curPayer=0,curCur='JPY';
let curAC='sight',curACur='JPY',curAPayer=0;
```

- [ ] **Step 7: 拿掉 `selSplit`/`selASplit` 函式**

```bash
grep -n "^function selSplit\|^function selASplit" family-trip-template.html
```

刪除這兩行：

```javascript
function selASplit(m){curASplit=m;['both','p1','p2'].forEach(x=>document.getElementById('asp-'+x).classList.toggle('on',x===m));}
```
```javascript
function selSplit(m){curSplit=m;['both','p1','p2'].forEach(x=>document.getElementById('sp-'+x).classList.toggle('on',x===m));}
```

- [ ] **Step 8: 拿掉所有 `selSplit(...)`/`selASplit(...)` 呼叫**

```bash
grep -n "selSplit(\|selASplit(" family-trip-template.html
```

會在 `openActM`、`openActEdit`、`openExpM`、`openExpMPrefilled`、`openExpEdit` 裡各找到一次呼叫，直接把 `selSplit(...)`/`selASplit(...)` 這段連同前後的 `;` 從那一行拿掉。例如：

```javascript
// 原本
curAC='sight';renderACGrid();selAPayer(0);selASplit('both');selACur('JPY');
// 改成
curAC='sight';renderACGrid();selAPayer(0);selACur('JPY');
```

```javascript
// 原本
selACur(a.cost?.cur||'JPY');selAPayer(Math.max(0,CFG.members.indexOf(a.cost?.paidBy)));selASplit(a.cost?.split||'both');
// 改成
selACur(a.cost?.cur||'JPY');selAPayer(Math.max(0,CFG.members.indexOf(a.cost?.paidBy)));
```

```javascript
// 原本
curCat='food';renderCatGrid();selPayer(0);selSplit('both');selCur('JPY');
// 改成
curCat='food';renderCatGrid();selPayer(0);selCur('JPY');
```

```javascript
// 原本（openExpMPrefilled，Task 3 已經把 selCur(data.currency||'JPY') 換成 selCur(safeCur)）
curCat=cat;renderCatGrid();selPayer(0);selSplit('both');selCur(safeCur);
// 改成
curCat=cat;renderCatGrid();selPayer(0);selCur(safeCur);
```

```javascript
// 原本（openExpEdit）
curCat=e.cat||'food';renderCatGrid();selPayer(Math.max(0,CFG.members.indexOf(e.paidBy)));selSplit(e.split||'both');selCur(e.cur||'JPY');
// 改成
curCat=e.cat||'food';renderCatGrid();selPayer(Math.max(0,CFG.members.indexOf(e.paidBy)));selCur(e.cur||'JPY');
```

- [ ] **Step 9: `saveAct`/`saveExp`/`moveAct` 拿掉 `split` 欄位**

```bash
grep -n "split:cur" family-trip-template.html
```

會找到 3 處（`saveAct` 的 `cost` 物件、`saveAct` 寫入 `/expenses/`、`saveExp`），把每處的 `,split:curASplit` 或 `,split:curSplit` 從物件字面量裡刪掉。例如：

```javascript
// 原本
cost:hasCost?{amt:costAmt,cur:curACur,paidBy:CFG.members[curAPayer],split:curASplit}:null,
// 改成
cost:hasCost?{amt:costAmt,cur:curACur,paidBy:CFG.members[curAPayer]}:null,
```

```javascript
// 原本
if(hasCost){DB.ref('/expenses/'+expId).set({desc:name,amt:costAmt,cur:curACur,cat:mapActCat(curAC),paidBy:CFG.members[curAPayer],split:curASplit,date:dayData.date||'',fromAct:true,at:new Date().toISOString()});}
// 改成
if(hasCost){DB.ref('/expenses/'+expId).set({desc:name,amt:costAmt,cur:curACur,cat:mapActCat(curAC),paidBy:CFG.members[curAPayer],date:dayData.date||'',fromAct:true,at:new Date().toISOString()});}
```

```javascript
// 原本
DB.ref('/expenses/'+eid).set({desc,amt,cur:curCur,cat:curCat,paidBy:CFG.members[curPayer],split:curSplit,date:document.getElementById('e_date').value||today(),at:new Date().toISOString()})
// 改成
DB.ref('/expenses/'+eid).set({desc,amt,cur:curCur,cat:curCat,paidBy:CFG.members[curPayer],date:document.getElementById('e_date').value||today(),at:new Date().toISOString()})
```

`moveAct` 裡也要拿掉：

```bash
grep -n "split:act.cost.split" family-trip-template.html
```

```javascript
// 原本
DB.ref('/expenses/actcost_'+toDid+'_'+aid).set({desc:act.name,amt:act.cost.amt,cur:act.cost.cur||'JPY',cat:mapActCat(act.cat),paidBy:act.cost.paidBy||CFG.members[0],split:act.cost.split||'both',date:newDate,fromAct:true,at:new Date().toISOString()});
// 改成
DB.ref('/expenses/actcost_'+toDid+'_'+aid).set({desc:act.name,amt:act.cost.amt,cur:act.cost.cur||'JPY',cat:mapActCat(act.cat),paidBy:act.cost.paidBy||CFG.members[0],date:newDate,fromAct:true,at:new Date().toISOString()});
```

- [ ] **Step 10: 拿掉 `calcBal` 函式**

```bash
grep -n "^function calcBal" family-trip-template.html
```

刪除整個函式：

```javascript
function calcBal(exps,cur){
  let p1p=0,p2p=0,p1s=0,p2s=0;
  Object.values(exps).filter(e=>(e.cur||'JPY')===cur).forEach(e=>{
    const a=e.amt||0;
    if(e.paidBy===CFG.p1)p1p+=a;else p2p+=a;
    if(e.split==='p1')p1s+=a;else if(e.split==='p2')p2s+=a;else{p1s+=a/2;p2s+=a/2;}
  });
  return{p1p,p2p,total:p1p+p2p,settle:p1p-p1s};
}
```

- [ ] **Step 11: `renderExp` 拿掉 balance 卡片與 split 標籤，付款人徽章改用 `.bpayer`**

```bash
grep -n "^function renderExp" family-trip-template.html
```

找到：

```javascript
function renderExp(exps){
  const balSec=document.getElementById('balSec'),expList=document.getElementById('expList');
  const entries=Object.entries(exps);
  if(!entries.length){
    balSec.innerHTML='';
    expList.innerHTML='<div class="empty"><div class="empty-i">💰</div><div class="empty-h">尚無支出紀錄</div><div class="empty-s">點 ＋ 新增支出</div></div>';
    return;
  }
  const jpy=calcBal(exps,'JPY'),twd=calcBal(exps,'TWD');

  const balRow=(b,cur,rowCls)=>{
    if(b.total<=0)return'';
    const sym=cur==='JPY'?'¥':'NT$',dp=0;
    const sAmt=Math.abs(b.settle);
    const settleHtml=sAmt>0.005
      ?`<span class="bc-settle">${b.settle>0?esc(CFG.p2)+'→'+esc(CFG.p1):esc(CFG.p1)+'→'+esc(CFG.p2)} ${sym}${sAmt.toFixed(dp)}</span>`
      :`<span class="bc-settle ok">✅ 結清</span>`;
    return`<div class="bc-row ${rowCls}">
      <div>
        <span class="bc-flag">${cur==='JPY'?'🇯🇵':'🇹🇼'}</span><span class="bc-tot">${sym}${b.total.toFixed(dp)}</span>
        <div class="bc-ps">${esc(CFG.p1)} ${sym}${b.p1p.toFixed(dp)} &nbsp;·&nbsp; ${esc(CFG.p2)} ${sym}${b.p2p.toFixed(dp)}</div>
      </div>
      ${settleHtml}
    </div>`;
  };

  balSec.innerHTML=`<div class="bc-card">${balRow(jpy,'JPY','')}${balRow(twd,'TWD','twd-row')}</div>`;

  // Expense list
  const groups={};
  entries.forEach(([id,e])=>{const d=e.date||'';(groups[d]=groups[d]||[]).push([id,e]);});
  expList.innerHTML=Object.keys(groups).sort().reverse().map(date=>`
    <div class="edl">${fmtD(date)}</div>`+
    groups[date].map(([id,e])=>{
      const cat=CATM[e.cat]||CATM.other,isP1=e.paidBy===CFG.p1;
      const slbl=e.split==='both'?'均分':e.split==='p1'?esc(CFG.p1)+'自付':esc(CFG.p2)+'自付';
      const sym=curSym(e.cur||'JPY'),dp=0;
      return`<div class="er">
        <div class="ei" style="background:${cat.bg}">${cat.ico}</div>
        <div class="einfo">
          <div class="edesc">${esc(e.desc||'')}</div>
          <div class="emeta">
            <span class="bdg ${isP1?'bp1':'bp2'}">${esc(e.paidBy)}</span>
            <span class="bdg bcur">${e.cur||'JPY'}</span>
            ${e.fromAct?'<span class="bdg bact">📅行程</span>':''}
            ${slbl}
          </div>
        </div>
        <div class="eright">
          <div class="eamt">${sym}${(e.amt||0).toFixed(dp)}</div>
          <div style="display:flex;gap:4px;justify-content:flex-end;margin-top:4px">
            <button class="ib" onclick="openExpEdit('${id}')">✎</button>
            <button class="ib" onclick="delExp('${id}')">✕</button>
          </div>
        </div>
      </div>`;
    }).join('')
  ).join('');
}
```

改成：

```javascript
function renderExp(exps){
  const expList=document.getElementById('expList');
  const entries=Object.entries(exps);
  if(!entries.length){
    expList.innerHTML='<div class="empty"><div class="empty-i">💰</div><div class="empty-h">尚無支出紀錄</div><div class="empty-s">點 ＋ 新增支出</div></div>';
    return;
  }

  const groups={};
  entries.forEach(([id,e])=>{const d=e.date||'';(groups[d]=groups[d]||[]).push([id,e]);});
  expList.innerHTML=Object.keys(groups).sort().reverse().map(date=>`
    <div class="edl">${fmtD(date)}</div>`+
    groups[date].map(([id,e])=>{
      const cat=CATM[e.cat]||CATM.other;
      const sym=curSym(e.cur||'JPY'),dp=0;
      return`<div class="er">
        <div class="ei" style="background:${cat.bg}">${cat.ico}</div>
        <div class="einfo">
          <div class="edesc">${esc(e.desc||'')}</div>
          <div class="emeta">
            <span class="bdg bpayer">${esc(e.paidBy)}</span>
            <span class="bdg bcur">${e.cur||'JPY'}</span>
            ${e.fromAct?'<span class="bdg bact">📅行程</span>':''}
          </div>
        </div>
        <div class="eright">
          <div class="eamt">${sym}${(e.amt||0).toFixed(dp)}</div>
          <div style="display:flex;gap:4px;justify-content:flex-end;margin-top:4px">
            <button class="ib" onclick="openExpEdit('${id}')">✎</button>
            <button class="ib" onclick="delExp('${id}')">✕</button>
          </div>
        </div>
      </div>`;
    }).join('')
  ).join('');
}
```

- [ ] **Step 12: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/family-trip-template.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_family6.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_family6.js && echo OK
```

Expected: `OK`

- [ ] **Step 13: 確認沒有殘留對已刪除識別字的參照**

```bash
grep -n "CFG\.p1\|CFG\.p2\|curSplit\|curASplit\|calcBal\|selSplit\|selASplit\|'sp-\|'asp-\|bc-card\|bc-settle" family-trip-template.html
```

Expected: 沒有輸出。如果有殘留（例如 CSS 選擇器字串 `.bc-card` 忘記刪），回頭補刪。

- [ ] **Step 14: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add family-trip-template.html
git commit -m "feat: remove split/settle logic, keep paidBy-only expense tracking"
```

---

## Task 8: 統計頁改成多人花費卡片

**Files:**
- Modify: `family-trip-template.html`（CSS：新增 `.member-grid`）
- Modify: `family-trip-template.html`（JS：`calcPersonSpend`→`calcMemberSpend`，`renderStat` 改成依 `CFG.members` 動態產生卡片）

- [ ] **Step 1: CSS 新增可換行的成員卡片 grid**

```bash
grep -n '\.pie-rate{' family-trip-template.html
```

在 `.pie-rate{...}` 這行之後插入：

```css
.member-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;}
.member-card{background:var(--card);border-radius:12px;padding:14px;box-shadow:0 1px 4px rgba(0,0,0,.06);}
.member-name{font-size:12px;font-weight:700;color:var(--muted);margin-bottom:8px;}
```

- [ ] **Step 2: `calcPersonSpend` 改名 `calcMemberSpend`，拿掉 split 判斷**

```bash
grep -n "^function calcPersonSpend" family-trip-template.html
```

找到：

```javascript
function calcPersonSpend(exps,who){
  const totals=new Map();
  Object.values(exps).forEach(e=>{
    const cur=e.cur||'JPY',amt=e.amt||0;
    let myAmt=0;
    if(e.split==='p1'&&who===CFG.p1)myAmt=amt;
    else if(e.split==='p2'&&who===CFG.p2)myAmt=amt;
    else if(e.split==='both')myAmt=amt/2;
    if(myAmt>0)totals.set(cur,(totals.get(cur)||0)+myAmt);
  });
  return totals;
}
```

改成：

```javascript
function calcMemberSpend(exps,who){
  const totals=new Map();
  Object.values(exps).forEach(e=>{
    if(e.paidBy!==who)return;
    const cur=e.cur||'JPY',amt=e.amt||0;
    if(amt>0)totals.set(cur,(totals.get(cur)||0)+amt);
  });
  return totals;
}
```

- [ ] **Step 3: `renderStat` 改成依 `CFG.members` 動態產生卡片**

```bash
grep -n "^function renderStat" family-trip-template.html
```

找到：

```javascript
function renderStat(exps){
  renderPie(exps);
  const p1=calcPersonSpend(exps,CFG.p1),p2=calcPersonSpend(exps,CFG.p2);
  const fmtTotals=m=>[...m.entries()].map(([cur,tot])=>`<div style="font-size:20px;font-weight:800">${curSym(cur)}${Math.round(tot).toLocaleString('zh-TW')}</div><div style="font-size:11px;color:var(--muted)">${cur}</div>`).join('')||'<div style="color:var(--muted);font-size:13px">無記錄</div>';
  document.getElementById('personSec').innerHTML=`
    <div class="card" style="display:flex;gap:0;padding:0;overflow:hidden;margin-bottom:10px">
      <div style="flex:1;padding:16px;border-right:1px solid var(--border)">
        <div style="font-size:12px;font-weight:700;color:var(--muted);margin-bottom:8px">${esc(CFG.p1)}</div>
        ${fmtTotals(p1)}
      </div>
      <div style="flex:1;padding:16px">
        <div style="font-size:12px;font-weight:700;color:var(--muted);margin-bottom:8px">${esc(CFG.p2)}</div>
        ${fmtTotals(p2)}
      </div>
    </div>`;
}
```

（如果 Task 2 Step 6 已經把 `cur==='JPY'?'¥':'NT$'` 換成 `curSym(cur)`，`fmtTotals` 這行應該已經長這樣；如果還是舊的三元運算式，先照 Task 2 Step 6 的方式換成 `curSym(cur)` 再繼續。）

改成：

```javascript
function renderStat(exps){
  renderPie(exps);
  const fmtTotals=m=>[...m.entries()].map(([cur,tot])=>`<div style="font-size:20px;font-weight:800">${curSym(cur)}${Math.round(tot).toLocaleString('zh-TW')}</div><div style="font-size:11px;color:var(--muted)">${cur}</div>`).join('')||'<div style="color:var(--muted);font-size:13px">無記錄</div>';
  document.getElementById('personSec').innerHTML=`<div class="member-grid">${CFG.members.map(name=>`
    <div class="member-card">
      <div class="member-name">${esc(name)}</div>
      ${fmtTotals(calcMemberSpend(exps,name))}
    </div>`).join('')}</div>`;
}
```

- [ ] **Step 4: 確認沒有殘留對 `calcPersonSpend` 的呼叫**

```bash
grep -n "calcPersonSpend" family-trip-template.html
```

Expected: 沒有輸出。

- [ ] **Step 5: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/family-trip-template.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_family7.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_family7.js && echo OK
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add family-trip-template.html
git commit -m "feat: per-member spend cards replace two-person balance stats"
```

---

## Task 9: 城市改自由輸入 + Open-Meteo Geocoding 查詢確認

**Files:**
- Modify: `family-trip-template.html`（Setup / Settings 城市欄位 HTML）
- Modify: `family-trip-template.html`（JS：拿掉 `CITIES` map，新增 `geocodeCity`/`geoLookup`，`doSetup`/`saveCfg`/`bootApp` 改用 geocoding 結果）

- [ ] **Step 1: Setup 畫面城市欄位 HTML 改成輸入框 + 查詢按鈕**

```bash
grep -n 'id="s_city"' family-trip-template.html
```

找到：

```html
    <div class="fg"><label class="lb">主要城市</label>
      <select class="inp" id="s_city">
        <option value="東京">東京</option>
        <option value="大阪">大阪</option>
        <option value="京都">京都</option>
        <option value="岡山" selected>岡山</option>
        <option value="札幌">札幌</option>
        <option value="福岡">福岡</option>
      </select>
    </div>
```

改成：

```html
    <div class="fg">
      <label class="lb">主要城市</label>
      <div class="fr" style="align-items:flex-end">
        <div class="fg" style="margin-bottom:0"><input class="inp" id="s_city" placeholder="例如：京都、Rome、Paris"></div>
        <button type="button" class="btn btn-g" style="flex:0 0 auto;padding:11px 14px" onclick="geoLookup('s')">📍 查詢</button>
      </div>
      <p class="hint" id="s_geo_result" style="text-align:left;margin-top:6px"></p>
    </div>
```

- [ ] **Step 2: Settings 畫面城市欄位 HTML 同步改**

```bash
grep -n 'id="c_city"' family-trip-template.html
```

找到：

```html
          <div class="fg"><label class="lb">主要城市</label>
            <select class="inp" id="c_city">
              <option value="東京">東京</option>
              <option value="大阪">大阪</option>
              <option value="京都">京都</option>
              <option value="岡山">岡山</option>
              <option value="札幌">札幌</option>
              <option value="福岡">福岡</option>
            </select>
          </div>
```

改成：

```html
          <div class="fg">
            <label class="lb">主要城市</label>
            <div class="fr" style="align-items:flex-end">
              <div class="fg" style="margin-bottom:0"><input class="inp" id="c_city" placeholder="例如：京都、Rome、Paris"></div>
              <button type="button" class="btn btn-g" style="flex:0 0 auto;padding:11px 14px" onclick="geoLookup('c')">📍 查詢</button>
            </div>
            <p class="hint" id="c_geo_result" style="text-align:left;margin-top:6px"></p>
          </div>
```

- [ ] **Step 3: 拿掉 `CITIES` map**

```bash
grep -n "^const CITIES=" family-trip-template.html
```

刪除整個宣告：

```javascript
const CITIES={
  '東京':{lat:35.68,lng:139.69},
  '大阪':{lat:34.69,lng:135.50},
  '京都':{lat:35.01,lng:135.77},
  '岡山':{lat:34.66,lng:133.93},
  '札幌':{lat:43.06,lng:141.35},
  '福岡':{lat:33.59,lng:130.40},
};
```

（`PRESET_CURRENCIES` 是 Task 2 Step 5 插在 `CITIES` 宣告之後，拿掉 `CITIES` 之後 `PRESET_CURRENCIES` 直接接在原本 `CITIES` 出現的位置，不用動。）

- [ ] **Step 4: 新增 `geocodeCity`/`geoLookup`，放在 `fetchWeather` 定義之前**

```bash
grep -n "^async function fetchWeather" family-trip-template.html
```

在它前面插入：

```javascript
let pendingGeo=null;
async function geocodeCity(name){
  try{
    const r=await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(name)}&count=1&language=zh`);
    const d=await r.json();
    const first=d.results?.[0];
    if(!first)return null;
    const label=[first.name,first.admin1,first.country].filter(Boolean).join(', ');
    return{lat:first.latitude,lng:first.longitude,label};
  }catch(e){return null;}
}
async function geoLookup(prefix){
  const input=document.getElementById(prefix+'_city');
  const resultEl=document.getElementById(prefix+'_geo_result');
  const name=input.value.trim();
  if(!name){resultEl.textContent='';pendingGeo=null;return;}
  resultEl.textContent='🔍 定位中…';
  const geo=await geocodeCity(name);
  if(!geo){resultEl.textContent='⚠️ 找不到這個地點，請確認拼寫或換個名稱';pendingGeo=null;return;}
  pendingGeo={queriedFor:name,...geo};
  resultEl.textContent=`📍 已定位：${geo.label} (${geo.lat.toFixed(2)}, ${geo.lng.toFixed(2)})`;
}
```

- [ ] **Step 5: `doSetup()` 改用 `pendingGeo`**

```bash
grep -n "^function doSetup" family-trip-template.html
```

找到（Task 6 Step 8 之後的版本）：

```javascript
function doSetup(){
  const url=document.getElementById('s_url').value.trim();
  if(!url){alert('請輸入 Firebase 資料庫網址');return;}
  const members=['s_m1','s_m2','s_m3','s_m4'].map(id=>document.getElementById(id).value.trim()).filter(Boolean);
  if(members.length<2){alert('請至少填寫 2 位成員');return;}
  const city=document.getElementById('s_city').value||'東京';
  const coords=CITIES[city]||{lat:35.68,lng:139.69};
  CFG={url,title:document.getElementById('s_title').value.trim()||'家庭旅行',
    members,
    start:document.getElementById('s_start').value||today(),
    days:parseInt(document.getElementById('s_days').value)||7,
    photo:document.getElementById('s_photo').value.trim(),
    city,lat:coords.lat,lng:coords.lng,
    geminiKey:document.getElementById('s_gemini').value.trim()};
  localStorage.setItem('family_trip',JSON.stringify(CFG));
  bootApp();
}
```

改成：

```javascript
function doSetup(){
  const url=document.getElementById('s_url').value.trim();
  if(!url){alert('請輸入 Firebase 資料庫網址');return;}
  const members=['s_m1','s_m2','s_m3','s_m4'].map(id=>document.getElementById(id).value.trim()).filter(Boolean);
  if(members.length<2){alert('請至少填寫 2 位成員');return;}
  const cityName=document.getElementById('s_city').value.trim();
  if(!cityName){alert('請輸入城市名稱');return;}
  if(!pendingGeo||pendingGeo.queriedFor!==cityName){alert('請先點「📍 查詢」確認城市座標');return;}
  CFG={url,title:document.getElementById('s_title').value.trim()||'家庭旅行',
    members,
    start:document.getElementById('s_start').value||today(),
    days:parseInt(document.getElementById('s_days').value)||7,
    photo:document.getElementById('s_photo').value.trim(),
    city:pendingGeo.label,cityQuery:cityName,lat:pendingGeo.lat,lng:pendingGeo.lng,
    geminiKey:document.getElementById('s_gemini').value.trim()};
  localStorage.setItem('family_trip',JSON.stringify(CFG));
  bootApp();
}
```

- [ ] **Step 6: `bootApp()` 回填城市輸入框與確認文字**

```bash
grep -n "document.getElementById('c_city').value=CFG.city" family-trip-template.html
```

找到：

```javascript
  document.getElementById('c_city').value=CFG.city||'東京';
```

改成：

```javascript
  document.getElementById('c_city').value=CFG.cityQuery||'';
  document.getElementById('c_geo_result').textContent=CFG.city?`📍 目前定位：${CFG.city} (${(CFG.lat||0).toFixed(2)}, ${(CFG.lng||0).toFixed(2)})`:'';
```

- [ ] **Step 7: `saveCfg()` 改用 `pendingGeo`，只有城市文字真的變更時才要求重新查詢**

```bash
grep -n "const newCity=document.getElementById('c_city').value" family-trip-template.html
```

找到：

```javascript
  const newCity=document.getElementById('c_city').value||CFG.city;
  if(newCity!==CFG.city){CFG.city=newCity;const coords=CITIES[newCity]||{lat:35.68,lng:139.69};CFG.lat=coords.lat;CFG.lng=coords.lng;}
```

改成：

```javascript
  const newCityName=document.getElementById('c_city').value.trim();
  if(newCityName&&newCityName!==CFG.cityQuery){
    if(!pendingGeo||pendingGeo.queriedFor!==newCityName){toast('⚠️ 城市已變更，請先點「📍 查詢」確認新座標，設定未儲存城市部分');}
    else{CFG.cityQuery=newCityName;CFG.city=pendingGeo.label;CFG.lat=pendingGeo.lat;CFG.lng=pendingGeo.lng;}
  }
```

- [ ] **Step 8: `fetchWeather()` 的預設 fallback 座標從東京改成台北（不再是日本專屬 app，預設值只在極端情況下才會用到——例如舊資料沒有 lat/lng）**

```bash
grep -n "CFG.lat||35.68" family-trip-template.html
```

找到：

```javascript
    const r=await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${CFG.lat||35.68}&longitude=${CFG.lng||139.69}&hourly=temperature_2m,weathercode&timezone=auto&forecast_days=${forecastDays}&past_days=${pastDays}`);
```

改成：

```javascript
    const r=await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${CFG.lat||25.03}&longitude=${CFG.lng||121.56}&hourly=temperature_2m,weathercode&timezone=auto&forecast_days=${forecastDays}&past_days=${pastDays}`);
```

- [ ] **Step 9: 確認沒有殘留對 `CITIES` 的參照**

```bash
grep -n "\bCITIES\b" family-trip-template.html
```

Expected: 沒有輸出。

- [ ] **Step 10: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/family-trip-template.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_family8.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_family8.js && echo OK
```

Expected: `OK`

- [ ] **Step 11: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add family-trip-template.html
git commit -m "feat: free-text city input with Open-Meteo geocoding lookup"
```

---

## Task 10: PWA icon + 暖橘色主色調

**Files:**
- Create: `/tmp/family_icon.py`（一次性腳本，不進 repo）
- Modify: `family-trip-template.html`（icon `<link>` 兩處、`:root` CSS 變數）

- [ ] **Step 1: 用 Pillow 產生家庭剪影 icon**

```bash
cat > /tmp/family_icon.py <<'EOF'
from PIL import Image, ImageDraw
import base64, re

SIZE = 512
img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 圓角橘色背景
bg_color = (249, 115, 22, 255)  # #F97316
radius = 96
d.rounded_rectangle([0, 0, SIZE-1, SIZE-1], radius=radius, fill=bg_color)

white = (255, 255, 255, 255)

# 房子輪廓（屋頂三角形 + 牆面矩形），置中偏上
cx, cy = SIZE // 2, SIZE // 2
roof_w, roof_h = 220, 130
wall_w, wall_h = 170, 130
roof_top = (cx, cy - 150)
roof_left = (cx - roof_w // 2, cy - 150 + roof_h)
roof_right = (cx + roof_w // 2, cy - 150 + roof_h)
d.polygon([roof_top, roof_left, roof_right], fill=white)

wall_top = cy - 150 + roof_h - 4
d.rectangle([cx - wall_w // 2, wall_top, cx + wall_w // 2, wall_top + wall_h], fill=white)

# 挖空門（橘色背景色蓋回去）
door_w, door_h = 46, 70
d.rectangle([cx - door_w // 2, wall_top + wall_h - door_h, cx + door_w // 2, wall_top + wall_h], fill=bg_color)

# 底下三個小圓點代表家人
dot_r = 14
dot_y = cy + 150
for dx in (-60, 0, 60):
    d.ellipse([cx + dx - dot_r, dot_y - dot_r, cx + dx + dot_r, dot_y + dot_r], fill=white)

img.save('/tmp/family_icon.png')

with open('/tmp/family_icon.png', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode('ascii')

print(f'PNG size bytes: {len(open("/tmp/family_icon.png","rb").read())}')
print(f'base64 length: {len(b64)}')

path = "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/family-trip-template.html"
html = open(path, encoding='utf-8').read()

new_data_uri = f'data:image/png;base64,{b64}'

html, n1 = re.subn(
    r'(<link rel="apple-touch-icon" href=")data:image/png;base64,[^"]*(")',
    lambda m: m.group(1) + new_data_uri + m.group(2),
    html, count=1
)
html, n2 = re.subn(
    r'(<link rel="icon" type="image/png" href=")data:image/png;base64,[^"]*(")',
    lambda m: m.group(1) + new_data_uri + m.group(2),
    html, count=1
)
if n1 != 1 or n2 != 1:
    raise SystemExit(f'expected 1 replacement each, got apple-touch-icon={n1} icon={n2}')

open(path, 'w', encoding='utf-8').write(html)
print('OK, replaced both icon links')
EOF
python3 /tmp/family_icon.py
```

Expected: 印出 PNG 大小、base64 長度，以及 `OK, replaced both icon links`。

- [ ] **Step 2: 主色調從藍灰改暖橘**

```bash
grep -n "^  --blue:#7B9BAA;--blue2:#4D7A8A;--cyan:#A8C5CE;" family-trip-template.html
```

找到：

```css
  --blue:#7B9BAA;--blue2:#4D7A8A;--cyan:#A8C5CE;
```

改成：

```css
  --blue:#D08A4F;--blue2:#B06B35;--cyan:#E8B98C;
```

（變數名維持 `--blue`/`--blue2`/`--cyan` 不變——CSS 裡有 40 幾處引用這幾個變數名，改名字風險遠高於改色值；只換色值就能讓整個 app 主色調變成暖橘，效果一樣。）

- [ ] **Step 3: 確認圖片載入正常（本機開一次瀏覽器看 favicon/icon 沒有壞掉）**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
python3 -m http.server 8967 --bind 127.0.0.1 &
SERVER_PID=$!
sleep 1
echo "http://127.0.0.1:8967/family-trip-template.html"
```

用 Playwright 開啟這個網址，等頁面載入（Setup 畫面會出現），用 `mcp__playwright__browser_console_messages`（`level:"error"`）確認沒有跟 icon 載入相關的 error，截圖確認 Setup 畫面標題底色/按鈕已經是橘色系。驗證完：

```bash
kill $SERVER_PID
```

- [ ] **Step 4: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/family-trip-template.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_family9.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_family9.js && echo OK
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add family-trip-template.html
git commit -m "feat: family-themed PWA icon and warm orange accent color"
```

---

## Task 11: 端對端手動驗收（無法自動化，需要真實 Firebase）

**這個 Task 不修改程式碼**，是給執行計畫的人（或使用者本人）跑一次真實流程的檢查清單，因為前 9 個 Task 都只做了語法檢查，沒有實際跑過 Firebase 讀寫、Gemini OCR、地理定位這些需要外部服務或使用者輸入的流程。

- [ ] **Step 1: 準備一個測試用 Firebase Realtime Database**

用 Firebase Console 建一個新的測試專案（或沿用現有任一 trip app 的專案另開一個路徑），拿到 Realtime Database 網址。

- [ ] **Step 2: 本機開啟 `family-trip-template.html` 跑 Setup 流程**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
python3 -m http.server 8968 --bind 127.0.0.1
```

瀏覽器開 `http://127.0.0.1:8968/family-trip-template.html`，確認：
- 填入 Firebase 網址、標題、成員 1/2/3/4（其中留一個空白），城市欄位輸入「京都」後點「📍 查詢」，確認出現「📍 已定位：...」文字後才能成功點「開始使用」
- 不點查詢直接點「開始使用」會跳出「請先點『📍 查詢』確認城市座標」的 alert，不會建立行程

- [ ] **Step 3: 記帳流程**

進「記帳」tab，點 ＋ 新增支出：
- 幣別 chip 顯示 5 個（JPY/AUD/USD/EUR/TWD）且可正常切換選中狀態
- 「誰付錢」按鈕數量等於 Setup 填的成員數（3 人，因為留了一個空白）
- 新增一筆 EUR 支出後，切到「統計圖表」，確認圓餅圖分頁出現 EUR、且出現 3 張成員花費卡片（grid 排版，不是固定兩欄）、金額只算在有勾選的付款人身上（沒有分帳/結算文字）

- [ ] **Step 4: 行程活動花費**

進「行程」tab 新增一個活動並填花費，確認活動表單的付款人按鈕跟記帳表單一致（3 個成員），儲存後在「記帳」tab 能看到這筆自動產生的支出，付款人正確。

- [ ] **Step 5: 收據掃描（若有 Gemini API Key 可測）**

填入 Gemini API Key 後點「📷 掃描收據」，上傳一張測試收據圖片，確認辨識結果正確預填進記帳表單（幣別欄位是 5 選其一）。

- [ ] **Step 6: 設定頁**

進「設定」tab，把城市改成別的地名（例如「Rome」）但不點查詢就按「儲存設定」，確認跳出 toast 提示要先查詢、且城市沒有被更新；點「📍 查詢」後再儲存，確認 `c_geo_result` 顯示新地點且天氣資料（回到行程 tab）改成新城市的預報。

- [ ] **Step 7: 收尾**

```bash
# 找到 python3 -m http.server 8968 的 process 並關閉
pkill -f "http.server 8968"
```

把上面任何測試中發現的問題記錄下來回報，不要自己臨場修改程式碼（照這份計畫走完後如果驗收發現問題，應該回頭修對應 Task 再重新走一次語法檢查+commit 流程）。
