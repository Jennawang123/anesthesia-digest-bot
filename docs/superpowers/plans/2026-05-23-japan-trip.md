# Japan Trip App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `japan-trip.html`, a single-HTML PWA for Japan travel, by extending `trip-template.html` with Japan-specific branding, Gemini receipt scanning, per-person spending stats, and intra-day activity drag.

**Architecture:** Copy `trip-template.html` → `japan-trip.html`, then apply targeted changes across 7 tasks. All code lives in one HTML file. Firebase Realtime Database is the backend; Gemini 2.0 Flash handles receipt OCR; Open-Meteo provides weather.

**Tech Stack:** Vanilla JS, Firebase 9 compat SDK, Gemini 2.0 Flash REST API, Open-Meteo API, LocalStorage for config.

---

## Prerequisite: copy the template

- [ ] `cp "trip-template.html" "japan-trip.html"`

All tasks below modify **`japan-trip.html`** only.

---

## Task 1: Core bootstrap changes (timezone, storage key, default currency)

**Files:**
- Modify: `japan-trip.html` — `sydDate`, `localStorage` key, default currency, `renderExp` AUD references

- [ ] **Step 1: Replace timezone util and storage key**

  Find and replace these 3 lines exactly:

  Old (near line 441):
  ```js
  const sydDate=(d=new Date())=>d.toLocaleDateString('en-CA',{timeZone:'Australia/Sydney'});
  const today=()=>sydDate();
  ```
  New:
  ```js
  const japanDate=(d=new Date())=>d.toLocaleDateString('en-CA',{timeZone:'Asia/Tokyo'});
  const today=()=>japanDate();
  ```

  Old (in `doSetup`):
  ```js
  localStorage.setItem('_trip',JSON.stringify(CFG));
  ```
  New:
  ```js
  localStorage.setItem('japan_trip',JSON.stringify(CFG));
  ```

  Old (in `window.onload`):
  ```js
  const s=localStorage.getItem('_trip');
  ```
  New:
  ```js
  const s=localStorage.getItem('japan_trip');
  ```

  Old (in `saveCfg`):
  ```js
  localStorage.setItem('_trip',JSON.stringify(CFG));
  ```
  New:
  ```js
  localStorage.setItem('japan_trip',JSON.stringify(CFG));
  ```

  Old (in `changeFB`):
  ```js
  localStorage.removeItem('_trip');
  ```
  New:
  ```js
  localStorage.removeItem('japan_trip');
  ```

- [ ] **Step 2: Update default currency variable**

  Old:
  ```js
  let curCur='AUD';
  ```
  New:
  ```js
  let curCur='JPY';
  ```

  Old:
  ```js
  let curACur='AUD',curAPayer=0,curASplit='both';
  ```
  New:
  ```js
  let curACur='JPY',curAPayer=0,curASplit='both';
  ```

- [ ] **Step 3: Update app title in HTML**

  Old:
  ```html
  <meta name="apple-mobile-web-app-title" content="旅遊計畫">
  ```
  New:
  ```html
  <meta name="apple-mobile-web-app-title" content="日本之旅">
  ```

  Old:
  ```html
  <title>旅遊計畫</title>
  ```
  New:
  ```html
  <title>日本之旅</title>
  ```

  Old:
  ```html
  <div class="hdr-t" id="appTitle">雪梨之旅</div>
  ```
  New:
  ```html
  <div class="hdr-t" id="appTitle">日本之旅</div>
  ```

  Old:
  ```html
  <h1>✈️ 旅遊計畫</h1>
  ```
  New:
  ```html
  <h1>🇯🇵 日本之旅</h1>
  ```

- [ ] **Step 4: Commit**
  ```bash
  git add japan-trip.html
  git commit -m "feat: bootstrap japan-trip.html with timezone and storage key"
  ```

---

## Task 2: Setup screen — city dropdown + Gemini API key

**Files:**
- Modify: `japan-trip.html` — Setup HTML, Settings HTML, `doSetup()`, `bootApp()`, `saveCfg()`

- [ ] **Step 1: Add CITIES constant at top of script block**

  Add after the `ACTM` line (after `const ACTM=Object.fromEntries(...)`):
  ```js
  const CITIES={
    '東京':{lat:35.68,lng:139.69},
    '大阪':{lat:34.69,lng:135.50},
    '京都':{lat:35.01,lng:135.77},
    '岡山':{lat:34.66,lng:133.93},
    '札幌':{lat:43.06,lng:141.35},
    '福岡':{lat:33.59,lng:130.40},
  };
  ```

- [ ] **Step 2: Replace Setup HTML lat/lng inputs with city selector and Gemini key**

  Old (the `<div class="fr">` block with `s_lat` and `s_lng`):
  ```html
      <div class="fr">
        <div class="fg"><label class="lb">目的地緯度</label><input class="inp" id="s_lat" type="number" step="0.01" placeholder="例：35.68（東京）"></div>
        <div class="fg"><label class="lb">目的地經度</label><input class="inp" id="s_lng" type="number" step="0.01" placeholder="例：139.69（東京）"></div>
      </div>
  ```
  New:
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
      <div class="fg"><label class="lb">Gemini API Key</label><input class="inp" id="s_gemini" type="password" placeholder="AIza…"></div>
  ```

- [ ] **Step 3: Update `doSetup()` to read city + Gemini key**

  Old:
  ```js
  CFG={url,title:document.getElementById('s_title').value.trim()||'旅遊計畫',
    p1:document.getElementById('s_p1').value.trim()||'旅伴1',
    p2:document.getElementById('s_p2').value.trim()||'旅伴2',
    start:document.getElementById('s_start').value||today(),
    days:parseInt(document.getElementById('s_days').value)||7,
    photo:document.getElementById('s_photo').value.trim(),
    lat:parseFloat(document.getElementById('s_lat').value)||35.68,
    lng:parseFloat(document.getElementById('s_lng').value)||139.69};
  ```
  New:
  ```js
  const city=document.getElementById('s_city').value||'東京';
  const coords=CITIES[city]||{lat:35.68,lng:139.69};
  CFG={url,title:document.getElementById('s_title').value.trim()||'日本之旅',
    p1:document.getElementById('s_p1').value.trim()||'旅伴1',
    p2:document.getElementById('s_p2').value.trim()||'旅伴2',
    start:document.getElementById('s_start').value||today(),
    days:parseInt(document.getElementById('s_days').value)||7,
    photo:document.getElementById('s_photo').value.trim(),
    city,lat:coords.lat,lng:coords.lng,
    geminiKey:document.getElementById('s_gemini').value.trim()};
  ```

- [ ] **Step 4: Replace Settings HTML lat/lng with city selector and Gemini key**

  In the settings card, old:
  ```html
          <div class="fr">
            <div class="fg"><label class="lb">緯度</label><input class="inp" id="c_lat" type="number" step="0.01"></div>
            <div class="fg"><label class="lb">經度</label><input class="inp" id="c_lng" type="number" step="0.01"></div>
          </div>
  ```
  New:
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
          <div class="fg"><label class="lb">Gemini API Key</label><input class="inp" id="c_gemini" type="password" placeholder="AIza…"></div>
  ```

- [ ] **Step 5: Update `bootApp()` to populate settings city/gemini + remove lat/lng**

  In `bootApp()`, old:
  ```js
  document.getElementById('c_lat').value=CFG.lat||'';
  document.getElementById('c_lng').value=CFG.lng||'';
  ```
  New:
  ```js
  document.getElementById('c_city').value=CFG.city||'東京';
  document.getElementById('c_gemini').value=CFG.geminiKey||'';
  ```

- [ ] **Step 6: Update `saveCfg()` to save city + Gemini key**

  In `saveCfg()`, old:
  ```js
  CFG.lat=parseFloat(document.getElementById('c_lat').value)||CFG.lat;
  CFG.lng=parseFloat(document.getElementById('c_lng').value)||CFG.lng;
  ```
  New:
  ```js
  const newCity=document.getElementById('c_city').value||CFG.city;
  if(newCity!==CFG.city){CFG.city=newCity;const coords=CITIES[newCity]||{lat:35.68,lng:139.69};CFG.lat=coords.lat;CFG.lng=coords.lng;}
  CFG.geminiKey=document.getElementById('c_gemini').value.trim()||CFG.geminiKey;
  ```

- [ ] **Step 7: Commit**
  ```bash
  git add japan-trip.html
  git commit -m "feat: setup screen with city dropdown and Gemini API key"
  ```

---

## Task 3: Japan visual identity (PWA icon + header photo)

**Files:**
- Modify: `japan-trip.html` — canvas icon script, default header photo

- [ ] **Step 1: Replace plane icon with torii gate**

  The canvas icon script currently draws a plane. Replace the entire `(function(){...})()` icon block with:

  ```js
  (function(){
    const S=512,c=document.createElement('canvas');c.width=c.height=S;
    const x=c.getContext('2d');
    // Background gradient (warm red)
    const bg=x.createLinearGradient(0,0,0,S);
    bg.addColorStop(0,'#C0392B');bg.addColorStop(1,'#E74C3C');
    x.fillStyle=bg;x.beginPath();x.roundRect(0,0,S,S,96);x.fill();
    // Torii gate — white silhouette
    x.fillStyle='rgba(255,255,255,0.95)';
    // Top rail (kasagi)
    x.beginPath();x.roundRect(80,140,352,30,6);x.fill();
    // Second rail (nuki)
    x.beginPath();x.roundRect(110,195,292,22,5);x.fill();
    // Left pillar
    x.beginPath();x.roundRect(148,217,34,200,6);x.fill();
    // Right pillar
    x.beginPath();x.roundRect(330,217,34,200,6);x.fill();
    // Left cap (shimagi)
    x.beginPath();x.moveTo(80,140);x.lineTo(148,100);x.lineTo(182,140);x.closePath();x.fill();
    // Right cap
    x.beginPath();x.moveTo(432,140);x.lineTo(364,100);x.lineTo(330,140);x.closePath();x.fill();
    ['icon','apple-touch-icon'].forEach(r=>{const l=document.createElement('link');l.rel=r;l.href=c.toDataURL('image/png');document.head.appendChild(l);});
  })();
  ```

- [ ] **Step 2: Set default header photo to Japan landscape**

  In `bootApp()`, after the `hdrPhoto` logic, the template already checks `CFG.photo`. Change the default title shown when no photo:

  Old setup hint text:
  ```html
    <p class="hint">Firebase Console → Realtime Database → 建立資料庫（測試模式）→ 複製網址</p>
  ```

  This is fine to keep. No change needed for photo logic — users paste their own URL. The photo field is optional.

- [ ] **Step 3: Commit**
  ```bash
  git add japan-trip.html
  git commit -m "feat: Japan torii gate PWA icon"
  ```

---

## Task 4: Currency AUD → JPY + exchange rate JPY/TWD

**Files:**
- Modify: `japan-trip.html` — currency constants, HTML toggles, `fetchRate()`, `calcBal()`, `renderExp()`, `renderPie()`, `drawDonut()`, act/exp form currency selectors

- [ ] **Step 1: Update `fetchRate()` to fetch JPY/TWD**

  Old:
  ```js
  async function fetchRate(){
    try{
      const r=await fetch('https://open.er-api.com/v6/latest/AUD');
      const d=await r.json();
      if(d.result==='success'&&d.rates?.TWD){
        exchRate=d.rates.TWD;
        const el=document.getElementById('pieRate');
        if(el)el.textContent=`即時匯率 1 AUD ≈ NT$${exchRate.toFixed(2)}（台灣銀行參考）`;
      }
    }catch(e){exchRate=null;}
  }
  ```
  New:
  ```js
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

- [ ] **Step 2: Update `calcBal()` to use JPY instead of AUD**

  Old:
  ```js
  Object.values(exps).filter(e=>(e.cur||'AUD')===cur).forEach(e=>{
  ```
  New:
  ```js
  Object.values(exps).filter(e=>(e.cur||'JPY')===cur).forEach(e=>{
  ```

- [ ] **Step 3: Update `calcDaySpend()` fallback currency**

  Old:
  ```js
  const cur=e.cur||'AUD';
  ```
  New:
  ```js
  const cur=e.cur||'JPY';
  ```

- [ ] **Step 4: Update `renderExp()` — balance row and expense list**

  Old (calling calcBal):
  ```js
  const aud=calcBal(exps,'AUD'),twd=calcBal(exps,'TWD');
  ```
  New:
  ```js
  const jpy=calcBal(exps,'JPY'),twd=calcBal(exps,'TWD');
  ```

  Old (balRow call):
  ```js
  balSec.innerHTML=`<div class="bc-card">${balRow(aud,'AUD','')}${balRow(twd,'TWD','twd-row')}</div>`;
  ```
  New:
  ```js
  balSec.innerHTML=`<div class="bc-card">${balRow(jpy,'JPY','')}${balRow(twd,'TWD','twd-row')}</div>`;
  ```

  In `balRow` function, old:
  ```js
  const sym=cur==='AUD'?'$':'NT$',dp=cur==='AUD'?2:0;
  ```
  New:
  ```js
  const sym=cur==='JPY'?'¥':'NT$',dp=0;
  ```

  Old (flag emoji):
  ```js
  <span class="bc-flag">${cur==='AUD'?'🇦🇺':'🇹🇼'}</span>
  ```
  New:
  ```js
  <span class="bc-flag">${cur==='JPY'?'🇯🇵':'🇹🇼'}</span>
  ```

  Old (expense list sym/dp):
  ```js
  const sym=(e.cur||'AUD')==='AUD'?'$':'NT$',dp=(e.cur||'AUD')==='AUD'?2:0;
  ```
  New:
  ```js
  const sym=(e.cur||'JPY')==='JPY'?'¥':'NT$',dp=0;
  ```

  Old (expense list badge):
  ```js
  <span class="bdg ${(e.cur||'AUD')==='AUD'?'baud':'btwd'}">${e.cur||'AUD'}</span>
  ```
  New:
  ```js
  <span class="bdg ${(e.cur||'JPY')==='JPY'?'baud':'btwd'}">${e.cur||'JPY'}</span>
  ```

- [ ] **Step 5: Update `renderPie()` currency detection and tabs**

  Old:
  ```js
  const hasAUD=Object.values(exps).some(e=>(e.cur||'AUD')==='AUD'&&(e.amt||0)>0);
  ```
  New:
  ```js
  const hasJPY=Object.values(exps).some(e=>(e.cur||'JPY')==='JPY'&&(e.amt||0)>0);
  ```

  Old:
  ```js
  if(curPieCur==='AUD'&&!hasAUD)curPieCur=hasTWD?'TWD':'combined';
  if(curPieCur==='TWD'&&!hasTWD)curPieCur=hasAUD?'AUD':'combined';
  ```
  New:
  ```js
  if(curPieCur==='JPY'&&!hasJPY)curPieCur=hasTWD?'TWD':'combined';
  if(curPieCur==='TWD'&&!hasTWD)curPieCur=hasJPY?'JPY':'combined';
  ```

  Old tabs array:
  ```js
  if(hasAUD)tabs.push({k:'AUD',label:'🇦🇺 AUD',cls:''});
  if(hasTWD)tabs.push({k:'TWD',label:'🇹🇼 TWD',cls:'twd'});
  if(hasAUD&&hasTWD)tabs.push({k:'combined',label:'合計(TWD)',cls:'twd'});
  ```
  New:
  ```js
  if(hasJPY)tabs.push({k:'JPY',label:'🇯🇵 JPY',cls:''});
  if(hasTWD)tabs.push({k:'TWD',label:'🇹🇼 TWD',cls:'twd'});
  if(hasJPY&&hasTWD)tabs.push({k:'combined',label:'合計(TWD)',cls:'twd'});
  ```

  In `renderPie`, old (also `!hasAUD&&!hasTWD` guard):
  ```js
  if(!hasAUD&&!hasTWD){document.getElementById('pieSec').innerHTML='';return;}
  ```
  New:
  ```js
  if(!hasJPY&&!hasTWD){document.getElementById('pieSec').innerHTML='';return;}
  ```

- [ ] **Step 6: Update `drawDonut()` sym/dp logic**

  Old:
  ```js
  const sym=(cur==='AUD')?'$':'NT$',dp=(cur==='AUD')?2:0;
  ```
  (appears twice — in the canvas center text and in the legend)
  New (replace both):
  ```js
  const sym=(cur==='JPY')?'¥':'NT$',dp=0;
  ```

  Old (combined rate calc):
  ```js
  let amt=e.amt||0;
  if(isCombined)amt=(e.cur==='TWD')?amt:amt*rate;
  ```
  New (JPY→TWD conversion):
  ```js
  let amt=e.amt||0;
  if(isCombined)amt=(e.cur==='TWD')?amt:amt*rate;
  ```
  *(no change needed — logic works for JPY too)*

  Old (curPieCur sym in legend):
  ```js
  const sym=(curPieCur==='AUD')?'$':'NT$',dp=(curPieCur==='AUD')?2:0;
  ```
  New:
  ```js
  const sym=(curPieCur==='JPY')?'¥':'NT$',dp=0;
  ```

- [ ] **Step 7: Update HTML currency toggle buttons**

  In expense modal (`m-exp`), old:
  ```html
  <div class="cur-row"><div class="cr aud on" id="cur-aud" onclick="selCur('AUD')">🇦🇺 AUD</div><div class="cr twd" id="cur-twd" onclick="selCur('TWD')">🇹🇼 TWD</div></div>
  ```
  New:
  ```html
  <div class="cur-row"><div class="cr aud on" id="cur-jpy" onclick="selCur('JPY')">🇯🇵 JPY</div><div class="cr twd" id="cur-twd" onclick="selCur('TWD')">🇹🇼 TWD</div></div>
  ```

  In activity modal (`m-act`), old:
  ```html
  <div class="cur-row"><div class="cr aud on" id="acur-aud" onclick="selACur('AUD')">🇦🇺 AUD</div><div class="cr twd" id="acur-twd" onclick="selACur('TWD')">🇹🇼 TWD</div></div>
  ```
  New:
  ```html
  <div class="cur-row"><div class="cr aud on" id="acur-jpy" onclick="selACur('JPY')">🇯🇵 JPY</div><div class="cr twd" id="acur-twd" onclick="selACur('TWD')">🇹🇼 TWD</div></div>
  ```

- [ ] **Step 8: Update `selCur()` and `selACur()` JS functions**

  Old:
  ```js
  function selCur(c){curCur=c;document.getElementById('cur-aud').classList.toggle('on',c==='AUD');document.getElementById('cur-twd').classList.toggle('on',c==='TWD');}
  ```
  New:
  ```js
  function selCur(c){curCur=c;document.getElementById('cur-jpy').classList.toggle('on',c==='JPY');document.getElementById('cur-twd').classList.toggle('on',c==='TWD');}
  ```

  Old:
  ```js
  function selACur(c){curACur=c;document.getElementById('acur-aud').classList.toggle('on',c==='AUD');document.getElementById('acur-twd').classList.toggle('on',c==='TWD');}
  ```
  New:
  ```js
  function selACur(c){curACur=c;document.getElementById('acur-jpy').classList.toggle('on',c==='JPY');document.getElementById('acur-twd').classList.toggle('on',c==='TWD');}
  ```

- [ ] **Step 9: Update `openExpM()` and `openActM()` default currency**

  In `openExpM()`, old:
  ```js
  curCat='food';renderCatGrid();selPayer(0);selSplit('both');selCur('AUD');
  ```
  New:
  ```js
  curCat='food';renderCatGrid();selPayer(0);selSplit('both');selCur('JPY');
  ```

  In `openExpEdit()`, old:
  ```js
  selPayer(e.paidBy===CFG.p2?1:0);selSplit(e.split||'both');selCur(e.cur||'AUD');
  ```
  New:
  ```js
  selPayer(e.paidBy===CFG.p2?1:0);selSplit(e.split||'both');selCur(e.cur||'JPY');
  ```

  In `openActM()`, old:
  ```js
  curAC='sight';renderACGrid();selAPayer(0);selASplit('both');selACur('AUD');
  ```
  New:
  ```js
  curAC='sight';renderACGrid();selAPayer(0);selASplit('both');selACur('JPY');
  ```

  In `openActEdit()`, old:
  ```js
  selACur(a.cost?.cur||'AUD');
  ```
  New:
  ```js
  selACur(a.cost?.cur||'JPY');
  ```

- [ ] **Step 10: Update `renderSched` day-spend chip symbols**

  Old:
  ```js
  const sym=cur==='AUD'?'$':'NT$';
  const ico=cur==='AUD'?'💵':'💴';
  ```
  New:
  ```js
  const sym=cur==='JPY'?'¥':'NT$';
  const ico=cur==='JPY'?'💴':'💴';
  ```

- [ ] **Step 11: Update `renderSched` act-cost display**

  Old:
  ```js
  const sym=(act.cost?.cur||'AUD')==='AUD'?'$':'NT$';
  const dp=(act.cost?.cur||'AUD')==='AUD'?2:0;
  ```
  New:
  ```js
  const sym=(act.cost?.cur||'JPY')==='JPY'?'¥':'NT$';
  const dp=0;
  ```

- [ ] **Step 12: Update `moveAct` default currency**

  Old:
  ```js
  DB.ref('/expenses/actcost_'+toDid+'_'+aid).set({desc:act.name,amt:act.cost.amt,cur:act.cost.cur||'AUD',cat:mapActCat(act.cat),paidBy:act.cost.paidBy||CFG.p1,split:act.cost.split||'both',date:newDate,fromAct:true,at:new Date().toISOString()});
  ```
  New:
  ```js
  DB.ref('/expenses/actcost_'+toDid+'_'+aid).set({desc:act.name,amt:act.cost.amt,cur:act.cost.cur||'JPY',cat:mapActCat(act.cat),paidBy:act.cost.paidBy||CFG.p1,split:act.cost.split||'both',date:newDate,fromAct:true,at:new Date().toISOString()});
  ```

- [ ] **Step 13: Commit**
  ```bash
  git add japan-trip.html
  git commit -m "feat: replace AUD with JPY, update exchange rate to JPY/TWD"
  ```

---

## Task 5: Statistics tab — replace 記事本 with 統計

**Files:**
- Modify: `japan-trip.html` — tab bar HTML, page HTML, `goTab()`, `fabTap()`, `renderExp()`, new `calcPersonSpend()` and `renderStat()` functions

- [ ] **Step 1: Replace 記事本 tab with 統計 tab in tab bar HTML**

  Old:
  ```html
  <div class="ti"    id="t-notes" onclick="goTab('notes')"><span class="ti-i">📝</span><span class="ti-l">記事本</span></div>
  ```
  New:
  ```html
  <div class="ti"    id="t-stat"  onclick="goTab('stat')" ><span class="ti-i">📊</span><span class="ti-l">統計</span></div>
  ```

- [ ] **Step 2: Replace 記事本 page with 統計 page in HTML**

  Old:
  ```html
    <div class="page" id="page-notes">
      <div class="bx" id="notesList"></div>
    </div>
  ```
  New:
  ```html
    <div class="page" id="page-stat">
      <div class="bx" id="statBox"></div>
    </div>
  ```

- [ ] **Step 3: Move pie section to stat page**

  In the expense page HTML, the `pieSec` div currently lives in `page-exp`. Move pie to stat page.

  Old (in `page-exp`):
  ```html
      <div class="bx">
        <div id="balSec"></div>
        <div id="pieSec"></div>
        <div id="expList"></div>
      </div>
  ```
  New:
  ```html
      <div class="bx">
        <div id="balSec"></div>
        <div id="expList"></div>
      </div>
  ```

  In `page-stat`, after `<div class="bx" id="statBox">`, add `pieSec` and stat content container:
  ```html
    <div class="page" id="page-stat">
      <div class="bx">
        <div id="pieSec"></div>
        <div id="personSec"></div>
      </div>
    </div>
  ```

- [ ] **Step 4: Update `goTab()` to handle stat tab**

  Old:
  ```js
  fab.style.background=t==='exp'?'#F4A261':t==='notes'?'#10B981':'var(--blue)';
  ```
  New:
  ```js
  fab.style.background=t==='exp'?'#F4A261':'var(--blue)';
  fab.style.display=t==='cfg'||t==='stat'?'none':'flex';
  ```

  Old:
  ```js
  fab.style.display=t==='cfg'?'none':'flex';
  ```
  Remove this line (replaced above).

- [ ] **Step 5: Update `fabTap()` — remove notes**

  Old:
  ```js
  function fabTap(){
    if(curTab==='sched')openActM('day1');
    else if(curTab==='exp')openExpM();
    else if(curTab==='notes')openNoteM();
  }
  ```
  New:
  ```js
  function fabTap(){
    if(curTab==='sched')openActM('day1');
    else if(curTab==='exp')openExpM();
  }
  ```

- [ ] **Step 6: Add `calcPersonSpend()` function**

  Add after `calcDaySpend()`:
  ```js
  function calcPersonSpend(exps, who){
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

- [ ] **Step 7: Add `renderStat()` function**

  Add after `renderPie()`:
  ```js
  function renderStat(exps){
    renderPie(exps);
    const p1=calcPersonSpend(exps,CFG.p1),p2=calcPersonSpend(exps,CFG.p2);
    const fmtTotals=m=>[...m.entries()].map(([cur,tot])=>`<div style="font-size:20px;font-weight:800">${cur==='JPY'?'¥':'NT$'}${Math.round(tot).toLocaleString('zh-TW')}</div><div style="font-size:11px;color:var(--muted)">${cur}</div>`).join('')||'<div style="color:var(--muted);font-size:13px">無記錄</div>';
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

- [ ] **Step 8: Call `renderStat()` from Firebase listener**

  In `connectFB()` inside the `on('value')` callback, old:
  ```js
  lastExps=d.expenses||{};
  renderSched(sched);
  renderExp(lastExps);
  renderNotes(d.notes||{});
  ```
  New:
  ```js
  lastExps=d.expenses||{};
  renderSched(sched);
  renderExp(lastExps);
  renderStat(lastExps);
  ```

- [ ] **Step 9: Remove notes-related `renderNotes` call and modal from HTML**

  Remove the `<!-- Note -->` modal block and `m-note` overlay from HTML. Also remove the `renderNotes` function call and the notes functions block from JS (lines starting with `// ─── Notes`). This is optional cleanup — leaving them in place doesn't break anything.

- [ ] **Step 10: Commit**
  ```bash
  git add japan-trip.html
  git commit -m "feat: add statistics tab with pie chart and per-person spending"
  ```

---

## Task 6: Receipt scanning (Gemini 2.0 Flash OCR)

**Files:**
- Modify: `japan-trip.html` — FAB, new file input HTML, new `scanReceipt()` and `openExpMPrefilled()` functions

- [ ] **Step 1: Add CSS for FAB scan menu**

  Add in `<style>` block after the `.fab` rule:
  ```css
  .fab-menu{position:fixed;bottom:calc(var(--tab-h) + var(--safe-b) + 76px);right:16px;display:flex;flex-direction:column;gap:8px;z-index:98;opacity:0;pointer-events:none;transform:translateY(10px);transition:opacity .18s,transform .18s;}
  .fab-menu.open{opacity:1;pointer-events:auto;transform:translateY(0);}
  .fab-item{display:flex;align-items:center;gap:10px;background:#fff;border-radius:24px;padding:10px 16px;box-shadow:0 2px 10px rgba(0,0,0,.15);cursor:pointer;font-size:14px;font-weight:600;white-space:nowrap;}
  .fab-item:active{opacity:.7;}
  ```

- [ ] **Step 2: Add FAB menu HTML and hidden file input**

  Replace the existing `<button class="fab"...>＋</button>` with:
  ```html
  <div class="fab-menu" id="fabMenu">
    <div class="fab-item" onclick="closeFabMenu();openExpM()">✏️ 手動輸入</div>
    <div class="fab-item" onclick="closeFabMenu();document.getElementById('receiptFile').click()">📷 掃描收據</div>
  </div>
  <input type="file" id="receiptFile" accept="image/*" capture="environment" style="display:none" onchange="onReceiptPick(event)">
  <button class="fab" id="fab" onclick="fabTap()">＋</button>
  ```

- [ ] **Step 3: Add scanning prompt constant**

  Add at the top of the `<script>` block (after `const CATS=[...]`):
  ```js
  const RECEIPT_PROMPT=`你是日本收據辨識助手。請分析這張收據圖片，只回傳以下 JSON，不加任何說明：
  {"store":"店名（若看不清則填空字串）","amount":金額數字（日圓整數含稅）,"currency":"JPY","category":"food|transport|hotel|shopping|ticket|activity","date":"YYYY-MM-DD（若看不清則填今天）"}
  注意：日本收據常見外税(8%/10%)與内税，請確認取含税最終金額。`;
  ```

- [ ] **Step 4: Add `scanReceipt()` function**

  Add after `fetchRate()`:
  ```js
  async function scanReceipt(base64Image){
    if(!CFG.geminiKey)return null;
    try{
      const res=await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${CFG.geminiKey}`,
        {method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({contents:[{parts:[
          {text:RECEIPT_PROMPT},
          {inline_data:{mime_type:'image/jpeg',data:base64Image}}
        ]}]})}
      );
      const json=await res.json();
      const raw=json.candidates?.[0]?.content?.parts?.[0]?.text||'';
      const cleaned=raw.replace(/```json|```/g,'').trim();
      return JSON.parse(cleaned);
    }catch(e){return null;}
  }
  ```

- [ ] **Step 5: Add `onReceiptPick()` handler**

  Add after `scanReceipt()`:
  ```js
  function onReceiptPick(ev){
    const f=ev.target.files[0];ev.target.value='';if(!f)return;
    const reader=new FileReader();
    reader.onload=async e=>{
      toast('🔍 辨識收據中…');
      const base64=e.target.result.split(',')[1];
      const data=await scanReceipt(base64);
      if(data&&data.amount>0){
        openExpMPrefilled(data);
      }else{
        toast('⚠️ 辨識失敗，請手動輸入');
        openExpM();
      }
    };
    reader.readAsDataURL(f);
  }
  ```

- [ ] **Step 6: Add `openExpMPrefilled()` function**

  Add after `openExpM()`:
  ```js
  function openExpMPrefilled(data){
    document.getElementById('m-exp-t').textContent='確認支出（收據辨識）';
    document.getElementById('me-id').value='';
    document.getElementById('e_desc').value=data.store||'';
    document.getElementById('e_amt').value=data.amount||'';
    document.getElementById('e_date').value=data.date||today();
    const cat=(['food','transport','hotel','shopping','ticket','activity'].includes(data.category))?data.category:'food';
    curCat=cat;renderCatGrid();selPayer(0);selSplit('both');selCur(data.currency||'JPY');
    openM('m-exp');setTimeout(()=>document.getElementById('e_amt').focus(),280);
  }
  ```

- [ ] **Step 7: Update `fabTap()` to toggle FAB menu when on expense tab**

  Old:
  ```js
  function fabTap(){
    if(curTab==='sched')openActM('day1');
    else if(curTab==='exp')openExpM();
  }
  ```
  New:
  ```js
  let fabMenuOpen=false;
  function fabTap(){
    if(curTab==='sched'){openActM('day1');return;}
    if(curTab==='exp'){
      fabMenuOpen=!fabMenuOpen;
      document.getElementById('fabMenu').classList.toggle('open',fabMenuOpen);
      return;
    }
  }
  function closeFabMenu(){fabMenuOpen=false;document.getElementById('fabMenu').classList.remove('open');}
  ```

  Also close fab menu when tab switches. In `goTab()`, add at end:
  ```js
  closeFabMenu();
  ```

- [ ] **Step 8: Commit**
  ```bash
  git add japan-trip.html
  git commit -m "feat: Gemini receipt scanning with pre-fill expense form"
  ```

---

## Task 7: Intra-day activity drag (reorder within same day)

**Files:**
- Modify: `japan-trip.html` — `renderSched()` act sort, `saveAct()` order field, new `initActDnD()` function

- [ ] **Step 1: Add drag handle CSS**

  In `<style>`, add after `.act-row`:
  ```css
  .act-handle{width:18px;font-size:14px;color:var(--border);cursor:grab;flex-shrink:0;display:flex;align-items:center;user-select:none;}
  .act-handle:active{cursor:grabbing;}
  ```

- [ ] **Step 2: Add drag handle to act-row in `renderSched()`**

  Old act-row template string:
  ```js
  return `<div class="act-row" draggable="true" data-did="${did}" data-aid="${aid}">
    <div class="act-ico" ...>
  ```
  New (add handle before ico, remove `draggable` from row itself for cross-day drag to still work):
  ```js
  return `<div class="act-row" draggable="true" data-did="${did}" data-aid="${aid}">
    <div class="act-handle" data-did="${did}" data-aid="${aid}">⠿</div>
    <div class="act-ico" ...>
  ```

- [ ] **Step 3: Update act sort in `renderSched()` to use `order` field**

  Old:
  ```js
  const acts=Object.entries(day.acts||{}).sort((a,b)=>(a[1].time||'').localeCompare(b[1].time||''));
  ```
  New:
  ```js
  const acts=Object.entries(day.acts||{}).sort((a,b)=>{
    const oa=a[1].order!=null?a[1].order:999999;
    const ob=b[1].order!=null?b[1].order:999999;
    if(oa!==ob)return oa-ob;
    return(a[1].time||'').localeCompare(b[1].time||'');
  });
  ```

- [ ] **Step 4: Add `order` support when saving activity in `saveAct()`**

  First, add a module-level variable near the top of the script (after `const DG={...}`):
  ```js
  let curActOrder=0;
  ```

  In `openActEdit()`, after reading the act from Firebase, add:
  ```js
  curActOrder=a.order||0;
  ```
  So `openActEdit` becomes:
  ```js
  function openActEdit(did,aid){
    DB.ref('/schedule/'+did+'/acts/'+aid).once('value',snap=>{
      const a=snap.val();if(!a)return;
      document.getElementById('m-act-t').textContent='編輯活動';
      document.getElementById('ma-did').value=did;document.getElementById('ma-aid').value=aid;
      document.getElementById('a_time').value=a.time||'';document.getElementById('a_name').value=a.name||'';
      document.getElementById('a_loc').value=a.loc||'';document.getElementById('a_note').value=a.note||'';
      document.getElementById('a_cost').value=a.cost?.amt||'';
      curAC=a.cat||'sight';renderACGrid();
      selACur(a.cost?.cur||'JPY');selAPayer(a.cost?.paidBy===CFG.p2?1:0);selASplit(a.cost?.split||'both');
      curActOrder=a.order||0;
      openM('m-act');
    });
  }
  ```

  In `saveAct()`, inside the `DB.ref('/schedule/'+did).once('value'...)` callback, replace obj definition:

  Old:
  ```js
  const obj={cat:curAC,name,time:document.getElementById('a_time').value,
    loc:document.getElementById('a_loc').value.trim(),note:document.getElementById('a_note').value.trim(),
    cost:hasCost?{amt:costAmt,cur:curACur,paidBy:curAPayer===0?CFG.p1:CFG.p2,split:curASplit}:null};
  const id=aid||('a'+uid());
  ```
  New:
  ```js
  const existingActs=Object.values(dayData.acts||{});
  const maxOrder=existingActs.length?Math.max(...existingActs.map(a=>a.order||0)):0;
  const isNew=!aid;
  const obj={cat:curAC,name,time:document.getElementById('a_time').value,
    loc:document.getElementById('a_loc').value.trim(),note:document.getElementById('a_note').value.trim(),
    cost:hasCost?{amt:costAmt,cur:curACur,paidBy:curAPayer===0?CFG.p1:CFG.p2,split:curASplit}:null,
    order:isNew?(maxOrder+1):curActOrder};
  const id=aid||('a'+uid());
  ```

- [ ] **Step 5: Add `initActDnD()` function for within-day drag**

  Add after `initDnD()`:
  ```js
  const ADG={on:false,did:null,aid:null,srcEl:null,srcIdx:null};
  function initActDnD(){
    const box=document.getElementById('schedBox');
    box.addEventListener('dragstart',e=>{
      const handle=e.target.closest('.act-handle');
      const row=e.target.closest('.act-row');
      if(!handle||!row)return;
      ADG.on=true;ADG.did=row.dataset.did;ADG.aid=row.dataset.aid;ADG.srcEl=row;
      e.dataTransfer.setData('actdnd',JSON.stringify({did:row.dataset.did,aid:row.dataset.aid}));
      e.dataTransfer.effectAllowed='move';
      setTimeout(()=>row.classList.add('dragging'),0);
    });
    box.addEventListener('dragend',e=>{
      ADG.on=false;
      e.target.closest&&e.target.closest('.act-row')?.classList.remove('dragging');
      document.querySelectorAll('.act-row.drag-over-act').forEach(r=>r.classList.remove('drag-over-act'));
    });
    box.addEventListener('dragover',e=>{
      if(!ADG.on)return;
      const row=e.target.closest('.act-row');
      if(!row||row===ADG.srcEl||row.dataset.did!==ADG.did)return;
      e.preventDefault();e.dataTransfer.dropEffect='move';
      document.querySelectorAll('.act-row.drag-over-act').forEach(r=>r.classList.remove('drag-over-act'));
      row.classList.add('drag-over-act');
    });
    box.addEventListener('drop',e=>{
      if(!ADG.on)return;
      const tgtRow=e.target.closest('.act-row');
      if(!tgtRow||tgtRow===ADG.srcEl||tgtRow.dataset.did!==ADG.did){ADG.on=false;return;}
      e.preventDefault();e.stopPropagation();
      const did=ADG.did;
      const dayCard=document.getElementById('dc-'+did);
      const rows=[...dayCard.querySelectorAll('.act-row')];
      const srcIdx=rows.findIndex(r=>r.dataset.aid===ADG.aid);
      const tgtIdx=rows.findIndex(r=>r.dataset.aid===tgtRow.dataset.aid);
      if(srcIdx<0||tgtIdx<0||srcIdx===tgtIdx){ADG.on=false;return;}
      // Reorder: assign new order values based on visual positions
      const aids=rows.map(r=>r.dataset.aid);
      aids.splice(srcIdx,1);aids.splice(tgtIdx,0,ADG.aid);
      const updates={};
      aids.forEach((a,i)=>updates['/schedule/'+did+'/acts/'+a+'/order']=i);
      DB.ref('/').update(updates);
      ADG.on=false;
    });
  }
  ```

- [ ] **Step 6: Add drag-over CSS for act rows**

  In `<style>`:
  ```css
  .act-row.drag-over-act{border-top:2px solid var(--blue);}
  ```

- [ ] **Step 7: Call `initActDnD()` from `bootApp()`**

  Old:
  ```js
  renderCatGrid();renderACGrid();initDnD();
  ```
  New:
  ```js
  renderCatGrid();renderACGrid();initDnD();initActDnD();
  ```

- [ ] **Step 8: Commit**
  ```bash
  git add japan-trip.html
  git commit -m "feat: intra-day activity drag-to-reorder"
  ```

---

## Task 8: Final wiring + open in browser

**Files:**
- Modify: `japan-trip.html` — tab emoji, `renderExp` no longer calls `renderPie`, settings adds Gemini key display

- [ ] **Step 1: Update expense tab emoji to JPY**

  Old:
  ```html
  <div class="ti"    id="t-exp"   onclick="goTab('exp')"  ><span class="ti-i">💰</span><span class="ti-l">記帳</span></div>
  ```
  New:
  ```html
  <div class="ti"    id="t-exp"   onclick="goTab('exp')"  ><span class="ti-i">💴</span><span class="ti-l">記帳</span></div>
  ```

- [ ] **Step 2: Remove `renderPie()` call from `renderExp()`**

  In `renderExp()`, old:
  ```js
  balSec.innerHTML=`<div class="bc-card">${balRow(jpy,'JPY','')}${balRow(twd,'TWD','twd-row')}</div>`;
  renderPie(exps);
  ```
  New:
  ```js
  balSec.innerHTML=`<div class="bc-card">${balRow(jpy,'JPY','')}${balRow(twd,'TWD','twd-row')}</div>`;
  ```
  (Pie is now rendered only via `renderStat()`)

- [ ] **Step 3: Open in browser and do a full walkthrough**

  ```bash
  open "japan-trip.html"
  ```

  Test checklist:
  - Setup screen appears with city dropdown and Gemini key field
  - Fill in Firebase URL, select 岡山, enter any name for p1/p2
  - App loads, header shows
  - 行程 tab: day cards show, day-within drag handle visible
  - 記帳 tab: FAB expands to show ✏️/📷 options; ✏️ opens expense form in JPY
  - 統計 tab: pie chart appears after adding expenses; per-person card shows
  - Receipt scan: 📷 triggers file picker (won't call Gemini without valid key, should open blank form)

- [ ] **Step 4: Final commit**
  ```bash
  git add japan-trip.html
  git commit -m "feat: complete Japan trip app - JPY currency, receipt scan, statistics tab, intra-day drag"
  ```
