# Travel Atlas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `travel-atlas.html`, a single-HTML dark-themed PWA that shows a "Travel Atlas" overview (stats, glow map, region/year charts, filterable trip list) and lets the user browse/add per-trip journal entries with photos, then seed it with migrated data from Notion + Apple Notes.

**Architecture:** New single HTML file (not derived from `trip-template.html` — that file's schedule/expense/drag-drop code is unrelated to a journal app and would mostly be deleted). It reuses the proven *patterns* from `trip-template.html`/`japan-trip.html`: Firebase Realtime Database via `DB.ref(...)`, a setup screen that takes a pasted Firebase URL, the tabbar/sheet/toast/card CSS component vocabulary, and utils (`uid`, `esc`, `toast`, `openM`/`closeM`). New on top: Firebase Storage for photo uploads, a canvas-drawn glow map + donut/bar charts, and an offline outbox synced on reconnect.

**Tech Stack:** Vanilla JS, Firebase 9 compat SDK (`database` + `storage`), Canvas 2D for map/charts, LocalStorage for config + offline outbox. Migration: a small Node script using the Firebase JS SDK (test-mode rules, same trust model as the app) to push seed JSON into the user's real database.

---

## File Structure

- Create: `travel-atlas.html` — the entire app (HTML + CSS + JS in one file), built up incrementally across Tasks 1–10.
- Create: `scripts/seed-travel-atlas.mjs` — one-time Node script that reads `seed-data/travel-atlas-seed.json` and writes it into the user's Firebase RTDB via the Firebase JS SDK.
- Create: `seed-data/travel-atlas-seed.json` — merged Notion + Apple Notes content, shaped to match the `/trips` schema.

---

## Task 1: App shell — setup screen, dark theme, boot, RTDB + Storage connect

**Files:**
- Create: `travel-atlas.html`

- [ ] **Step 1: Write the base file**

Create `travel-atlas.html` with this content:

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="旅遊足跡">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@600;700&family=Noto+Sans+TC:wght@400;500;600;700&display=swap" rel="stylesheet">
<title>Travel Atlas</title>
<script>
(function(){
  const S=512,c=document.createElement('canvas');c.width=c.height=S;
  const x=c.getContext('2d');
  const bg=x.createLinearGradient(0,0,S,S);
  bg.addColorStop(0,'#0B1220');bg.addColorStop(1,'#132038');
  x.fillStyle=bg;x.beginPath();x.roundRect(0,0,S,S,96);x.fill();
  x.strokeStyle='#4ADE80';x.lineWidth=10;
  x.beginPath();x.arc(S/2,S/2,150,0,Math.PI*2);x.stroke();
  x.fillStyle='#F4C95D';
  [[180,180],[340,210],[260,320],[190,360]].forEach(([px,py])=>{x.beginPath();x.arc(px,py,14,0,Math.PI*2);x.fill();});
  ['icon','apple-touch-icon'].forEach(r=>{const l=document.createElement('link');l.rel=r;l.href=c.toDataURL('image/png');document.head.appendChild(l);});
})();
</script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-database-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-storage-compat.js"></script>
<style>
:root{
  --bg:#0B1220;--bg2:#0E1830;--card:rgba(255,255,255,.06);--card-solid:#152238;
  --text:#EAF0FB;--muted:#8CA0C4;--border:rgba(255,255,255,.10);
  --teal:#4ADE80;--teal2:#22C55E;--gold:#F4C95D;--red:#F87171;
  --tab-h:60px;--safe-b:env(safe-area-inset-bottom,0px);
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent;}
body{font-family:-apple-system,BlinkMacSystemFont,'PingFang TC',sans-serif;background:var(--bg);color:var(--text);height:100dvh;display:flex;flex-direction:column;overflow:hidden;}

/* Setup */
#setup{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100dvh;padding:28px 20px;background:linear-gradient(160deg,#0B1220,#132038 60%,#0E2A28);}
#setup h1{font-family:'Noto Serif TC',serif;font-size:30px;font-weight:700;color:#fff;margin-bottom:6px;text-align:center;}
#setup p{font-size:14px;color:var(--muted);margin-bottom:26px;text-align:center;}
.scard{background:var(--card-solid);border:1px solid var(--border);border-radius:20px;padding:22px;width:100%;max-width:420px;}
.hint{font-size:11px;color:var(--muted);margin-top:10px;text-align:center;line-height:1.6;}

/* App */
#app{display:none;flex-direction:column;height:100dvh;}
.hdr{position:relative;height:64px;flex-shrink:0;display:flex;align-items:center;padding:0 16px;border-bottom:1px solid var(--border);background:var(--bg2);}
.hdr-t{font-family:'Noto Serif TC',serif;font-size:19px;font-weight:700;color:#fff;}
.hdr-s{font-size:11px;color:var(--muted);display:flex;align-items:center;gap:5px;margin-left:10px;}
.dot{width:7px;height:7px;border-radius:50%;background:var(--teal);}
.dot.busy{background:var(--gold);animation:pulse 1s infinite;}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.content{flex:1;overflow-y:auto;overflow-x:hidden;-webkit-overflow-scrolling:touch;padding-bottom:calc(var(--tab-h) + var(--safe-b) + 8px);}
.tabbar{position:fixed;bottom:0;left:0;right:0;height:calc(var(--tab-h) + var(--safe-b));padding-bottom:var(--safe-b);background:var(--bg2);border-top:1px solid var(--border);display:flex;z-index:100;}
.ti{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;cursor:pointer;color:var(--muted);user-select:none;transition:color .15s;}
.ti.on{color:var(--teal);}.ti-i{font-size:22px;line-height:1;}.ti-l{font-size:10px;font-weight:600;}
.page{display:none;}.page.on{display:block;}
.fab{position:fixed;bottom:calc(var(--tab-h) + var(--safe-b) + 14px);right:16px;width:54px;height:54px;border-radius:50%;border:none;cursor:pointer;background:var(--teal);color:#0B1220;font-size:28px;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 18px rgba(74,222,128,.35);z-index:99;transition:transform .12s;}
.fab:active{transform:scale(.9);}

/* Shared */
.bx{padding:12px 16px;}
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:16px;margin-bottom:10px;backdrop-filter:blur(6px);}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:11px 18px;border-radius:10px;border:none;font-size:15px;font-weight:600;cursor:pointer;transition:opacity .15s,transform .1s;font-family:inherit;}
.btn:active{opacity:.8;transform:scale(.97);}
.btn-b{background:var(--teal);color:#0B1220;}.btn-g{background:rgba(255,255,255,.08);color:var(--text);}.btn-r{background:var(--red);color:#fff;}.btn-w{width:100%;}
.ib{width:28px;height:28px;border-radius:7px;border:none;background:rgba(255,255,255,.08);cursor:pointer;font-size:13px;display:flex;align-items:center;justify-content:center;color:var(--muted);}
.fg{margin-bottom:14px;}
.lb{display:block;font-size:12px;font-weight:700;color:var(--muted);margin-bottom:5px;text-transform:uppercase;letter-spacing:.5px;}
.inp,.ta{width:100%;padding:11px 13px;border:1.5px solid var(--border);border-radius:10px;font-size:16px;font-family:inherit;background:rgba(255,255,255,.04);color:var(--text);outline:none;transition:border-color .2s;}
.inp::placeholder,.ta::placeholder{color:var(--muted);}
.inp:focus,.ta:focus{border-color:var(--teal);}
.ta{resize:none;min-height:72px;}
.fr{display:flex;gap:10px;}.fr .fg{flex:1;}
.tw{display:flex;background:rgba(255,255,255,.06);border-radius:10px;padding:3px;gap:3px;}
.to{flex:1;padding:8px 4px;text-align:center;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600;color:var(--muted);transition:all .15s;}
.to.on{background:var(--teal);color:#0B1220;}
.empty{text-align:center;padding:52px 20px;color:var(--muted);}
.empty-i{font-size:46px;margin-bottom:12px;}.empty-h{font-size:16px;font-weight:600;color:var(--text);}.empty-s{font-size:14px;margin-top:4px;}
.toast{position:fixed;bottom:calc(var(--tab-h) + var(--safe-b) + 70px);left:50%;transform:translateX(-50%);background:rgba(20,30,50,.92);border:1px solid var(--border);color:#fff;padding:9px 20px;border-radius:20px;font-size:14px;z-index:300;opacity:0;transition:opacity .25s;pointer-events:none;white-space:nowrap;}
.toast.show{opacity:1;}
.ov{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:200;align-items:flex-end;}
.ov.open{display:flex;}
.sheet{background:var(--card-solid);border:1px solid var(--border);border-radius:20px 20px 0 0;width:100%;max-height:93dvh;overflow-y:auto;padding:16px 20px calc(20px + var(--safe-b));animation:up .22s ease;}
@keyframes up{from{transform:translateY(100%)}to{transform:translateY(0)}}
.hdl{width:38px;height:4px;background:var(--border);border-radius:2px;margin:0 auto 14px;}
.st{font-size:18px;font-weight:700;margin-bottom:18px;}
</style>
</head>
<body>

<div id="setup">
  <h1>🌍 Travel Atlas</h1>
  <p>輸入 Firebase Realtime Database 網址與 Storage bucket 開始</p>
  <div class="scard">
    <div class="fg"><label class="lb">Firebase 資料庫網址</label><input class="inp" id="s_url" type="url" placeholder="https://xxx-default-rtdb.firebaseio.com"></div>
    <div class="fg"><label class="lb">Storage Bucket</label><input class="inp" id="s_bucket" placeholder="例：xxx.appspot.com"></div>
    <button class="btn btn-b btn-w" onclick="doSetup()">開始使用 →</button>
    <p class="hint">Firebase Console → Realtime Database（測試模式）→ 複製網址；Storage → 啟用 → 複製 bucket 名稱</p>
  </div>
</div>

<div id="app">
  <div class="hdr">
    <div class="hdr-t">🌍 Travel Atlas</div>
    <div class="hdr-s"><span class="dot" id="syncDot"></span><span id="syncTxt">已同步</span></div>
  </div>
  <div class="content">
    <div class="page on" id="page-atlas"><div class="bx" id="atlasBox"><div class="empty"><div class="empty-i">🌍</div><div class="empty-h">載入中…</div></div></div></div>
    <div class="page" id="page-trips"><div class="bx" id="tripsBox"><div class="empty"><div class="empty-i">🧳</div><div class="empty-h">載入中…</div></div></div></div>
    <div class="page" id="page-detail"><div class="bx" id="detailBox"></div></div>
    <div class="page" id="page-cfg">
      <div class="bx">
        <div class="card">
          <div class="fg"><label class="lb">資料庫網址</label><input class="inp" id="c_url" type="url"></div>
          <div class="fg"><label class="lb">Storage Bucket</label><input class="inp" id="c_bucket"></div>
          <button class="btn btn-g btn-w" onclick="changeFB()">變更 Firebase 連線</button>
        </div>
      </div>
    </div>
  </div>
  <button class="fab" id="fab" onclick="fabTap()">＋</button>
  <div class="tabbar">
    <div class="ti on" id="t-atlas" onclick="goTab('atlas')"><span class="ti-i">🌍</span><span class="ti-l">Atlas</span></div>
    <div class="ti"    id="t-trips" onclick="goTab('trips')"><span class="ti-i">🧳</span><span class="ti-l">旅程</span></div>
    <div class="ti"    id="t-cfg"   onclick="goTab('cfg')"  ><span class="ti-i">⚙️</span><span class="ti-l">設定</span></div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let CFG={},DB=null,STORAGE=null,curTab='atlas',curDetailTripId=null;

// ─── Utils ───────────────────────────────────────────
const uid=()=>Date.now().toString(36)+Math.random().toString(36).slice(2,6);
const esc=s=>String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2200);}
function sync(on){document.getElementById('syncDot').className='dot'+(on?' busy':'');document.getElementById('syncTxt').textContent=on?'同步中…':'已同步';}
function openM(id){document.getElementById(id).classList.add('open');}
function closeM(id){document.getElementById(id).classList.remove('open');}
document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('.ov').forEach(el=>el.addEventListener('click',e=>{if(e.target===el)el.classList.remove('open');}));
});

// ─── Setup / Boot ────────────────────────────────────
function doSetup(){
  const url=document.getElementById('s_url').value.trim();
  const bucket=document.getElementById('s_bucket').value.trim();
  if(!url){alert('請輸入 Firebase 資料庫網址');return;}
  if(!bucket){alert('請輸入 Storage bucket');return;}
  CFG={url,bucket};
  localStorage.setItem('travel_atlas_cfg',JSON.stringify(CFG));
  bootApp();
}
window.onload=()=>{
  const s=localStorage.getItem('travel_atlas_cfg');
  if(s){CFG=JSON.parse(s);bootApp();}
};
function bootApp(){
  document.getElementById('setup').style.display='none';
  document.getElementById('app').style.display='flex';
  document.getElementById('c_url').value=CFG.url;
  document.getElementById('c_bucket').value=CFG.bucket;
  connectFB();
}
function changeFB(){
  const url=document.getElementById('c_url').value.trim();
  const bucket=document.getElementById('c_bucket').value.trim();
  if(!url||!bucket){toast('⚠️ 網址與 bucket 都要填');return;}
  CFG={url,bucket};
  localStorage.setItem('travel_atlas_cfg',JSON.stringify(CFG));
  location.reload();
}

// ─── Firebase ────────────────────────────────────────
function connectFB(){
  sync(true);
  try{
    if(!firebase.apps.length)firebase.initializeApp({databaseURL:CFG.url.trim().replace(/\/$/,''),storageBucket:CFG.bucket.trim()});
    DB=firebase.database();
    STORAGE=firebase.storage();
    DB.ref('/trips').on('value',snap=>{
      const trips=snap.val()||{};
      onTripsUpdate(trips);
      sync(false);
    },err=>{sync(false);toast('⚠️ Firebase 錯誤：'+err.message);});
  }catch(e){sync(false);toast('⚠️ Firebase 初始化失敗');console.error(e);}
}
// Filled in by later tasks — receives the live /trips object on every change.
function onTripsUpdate(trips){window.__TRIPS__=trips;}

// ─── Tabs ────────────────────────────────────────────
function goTab(t){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('on'));
  document.querySelectorAll('.ti').forEach(x=>x.classList.remove('on'));
  document.getElementById('page-'+t)?.classList.add('on');
  document.getElementById('t-'+t)?.classList.add('on');
  curTab=t;
  const fab=document.getElementById('fab');
  fab.style.display=(t==='cfg'||t==='detail')?'none':'flex';
}
function fabTap(){ /* wired to openAddEntrySheet() in Task 9 */ }
</script>
</body>
</html>
```

- [ ] **Step 2: Verify it boots**

  Open `travel-atlas.html` directly in a browser (`open travel-atlas.html` on macOS). Enter any placeholder Firebase RTDB URL and bucket name (real project not required yet — you're only checking the setup → app transition renders). Confirm:
  - Setup screen shows dark background, teal button
  - After submitting, tabbar with 🌍 Atlas / 🧳 旅程 / ⚙️ 設定 appears
  - Switching tabs shows the correct "載入中…" empty state per page
  - The sync dot briefly turns gold, then settles (or shows an error toast if the URL is fake — either is fine at this step)

- [ ] **Step 3: Commit**

```bash
git add travel-atlas.html
git commit -m "feat: scaffold Travel Atlas app shell with dark theme and RTDB/Storage boot"
```

---

## Task 2: Data layer — trips/entries CRUD helpers and derived stats

**Files:**
- Modify: `travel-atlas.html` — insert before the `// ─── Tabs ─────` comment

- [ ] **Step 1: Add CRUD + stats functions**

```js
// ─── Data layer ──────────────────────────────────────
const REGIONS=[
  {id:'east-asia',name:'東亞',color:'#4ADE80'},
  {id:'se-asia',name:'東南亞',color:'#38BDF8'},
  {id:'south-asia',name:'南亞',color:'#F472B6'},
  {id:'europe',name:'歐洲',color:'#F4C95D'},
  {id:'americas',name:'美洲',color:'#FB923C'},
  {id:'oceania',name:'大洋洲',color:'#A78BFA'},
];
const REGIONM=Object.fromEntries(REGIONS.map(r=>[r.id,r]));

function tripsRef(){return DB.ref('/trips');}
function entriesRef(tripId){return DB.ref('/trips/'+tripId+'/entries');}

function createTrip(trip){
  const id=uid();
  tripsRef().child(id).set(trip);
  return id;
}
function updateTrip(tripId,patch){tripsRef().child(tripId).update(patch);}
function deleteTrip(tripId){tripsRef().child(tripId).remove();}

function createEntry(tripId,entry){
  const id=uid();
  entriesRef(tripId).child(id).set(entry);
  return id;
}
function updateEntry(tripId,entryId,patch){entriesRef(tripId).child(entryId).update(patch);}
function deleteEntry(tripId,entryId){entriesRef(tripId).child(entryId).remove();}

// Derived stats from the live /trips snapshot object
function computeStats(trips){
  const list=Object.entries(trips||{}).map(([id,t])=>({id,...t}));
  const countries=new Set();
  list.forEach(t=>(t.countryCode||[]).forEach(c=>countries.add(c)));
  const years=list.map(t=>(t.startDate||'').slice(0,4)).filter(Boolean).map(Number);
  const startYear=years.length?Math.min(...years):new Date().getFullYear();
  const regionCounts=REGIONS.map(r=>({...r,value:list.filter(t=>t.region===r.id).length})).filter(r=>r.value>0);
  const yearCounts=[];
  const curYear=new Date().getFullYear();
  for(let y=startYear;y<=curYear;y++){
    yearCounts.push({year:y,count:list.filter(t=>Number((t.startDate||'').slice(0,4))===y).length,highlight:y===curYear});
  }
  return{trips:list,tripCount:list.length,countryCount:countries.size,startYear,regionCounts,yearCounts};
}
```

- [ ] **Step 2: Wire it into `onTripsUpdate` and verify in console**

  Replace the placeholder from Task 1:

  Old:
  ```js
  function onTripsUpdate(trips){window.__TRIPS__=trips;}
  ```
  New:
  ```js
  function onTripsUpdate(trips){window.__STATS__=computeStats(trips);}
  ```

  Reload the app, open browser devtools console, run `window.__STATS__` — confirm it returns `{trips:[], tripCount:0, countryCount:0, startYear:<current year>, regionCounts:[], yearCounts:[...]}` against an empty database.

- [ ] **Step 3: Commit**

```bash
git add travel-atlas.html
git commit -m "feat: add trips/entries CRUD helpers and derived stats computation"
```

---

## Task 3: Atlas home — stats row, glow map, donut + bar charts

**Files:**
- Modify: `travel-atlas.html`

- [ ] **Step 1: Add Atlas-page CSS**

  Insert before the closing `</style>`:

```css
.stat-row{display:flex;gap:10px;margin-bottom:12px;}
.stat{flex:1;text-align:center;}
.stat-n{font-size:24px;font-weight:800;color:var(--text);}
.stat-l{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-top:2px;}
.map-wrap{position:relative;border-radius:16px;overflow:hidden;margin-bottom:12px;border:1px solid var(--border);background:radial-gradient(ellipse at center,#0E2A3A,#081120);}
.map-wrap canvas{display:block;width:100%;}
.map-tip{position:absolute;background:rgba(10,20,35,.92);border:1px solid var(--border);border-radius:8px;padding:6px 10px;font-size:12px;color:#fff;pointer-events:none;transform:translate(-50%,-120%);white-space:nowrap;display:none;}
.chart-row{display:flex;gap:10px;}
.chart-card{flex:1;}
.chart-card canvas{width:100%;display:block;}
.chart-title{font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;}
.legend-row{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);margin-top:4px;}
.legend-dot{width:8px;height:8px;border-radius:3px;flex-shrink:0;}
```

- [ ] **Step 2: Add the Atlas render function**

  Insert before `// ─── Tabs ─────`:

```js
// ─── Atlas home ──────────────────────────────────────
function renderAtlas(stats){
  const box=document.getElementById('atlasBox');
  if(!stats.tripCount){
    box.innerHTML='<div class="empty"><div class="empty-i">🌍</div><div class="empty-h">還沒有旅程</div><div class="empty-s">點右下角 ＋ 新增第一趟旅程</div></div>';
    return;
  }
  box.innerHTML=`
    <div class="stat-row">
      <div class="stat"><div class="stat-n">${stats.tripCount}</div><div class="stat-l">趟旅行</div></div>
      <div class="stat"><div class="stat-n">${stats.countryCount}</div><div class="stat-l">個國家</div></div>
      <div class="stat"><div class="stat-n">${new Date().getFullYear()-stats.startYear+1}</div><div class="stat-l">年來</div></div>
    </div>
    <div class="map-wrap"><canvas id="mapCanvas" width="400" height="260"></canvas><div class="map-tip" id="mapTip"></div></div>
    <div class="chart-row">
      <div class="card chart-card"><div class="chart-title">地區分佈</div><canvas id="donutCanvas" width="140" height="140"></canvas>
        <div id="donutLegend"></div>
      </div>
      <div class="card chart-card"><div class="chart-title">年度足跡</div><canvas id="barCanvas" width="140" height="140"></canvas></div>
    </div>`;
  drawMap(stats.trips);
  drawDonut(document.getElementById('donutCanvas'),stats.regionCounts);
  document.getElementById('donutLegend').innerHTML=stats.regionCounts.map(r=>
    `<div class="legend-row"><span class="legend-dot" style="background:${r.color}"></span>${r.name} · ${r.value}</div>`
  ).join('');
  drawYearlyBars(document.getElementById('barCanvas'),stats.yearCounts);
}

// Equirectangular lat/lng → canvas x/y
function project(lat,lng,w,h){return{x:(lng+180)/360*w,y:(90-lat)/180*h};}

function drawMap(trips){
  const canvas=document.getElementById('mapCanvas');
  const ctx=canvas.getContext('2d');
  const w=canvas.width,h=canvas.height;
  ctx.clearRect(0,0,w,h);
  // Procedural dot-grid background (not a literal coastline — a stylized atlas texture)
  ctx.fillStyle='rgba(255,255,255,.05)';
  for(let y=8;y<h;y+=14){for(let x=8;x<w;x+=14){ctx.beginPath();ctx.arc(x,y,1,0,Math.PI*2);ctx.fill();}}
  const pins=[];
  trips.forEach(t=>{
    if(t.lat==null||t.lng==null)return;
    const{x,y}=project(t.lat,t.lng,w,h);
    pins.push({x,y,title:t.title,id:t.id});
    const grad=ctx.createRadialGradient(x,y,0,x,y,10);
    grad.addColorStop(0,'rgba(74,222,128,.9)');grad.addColorStop(1,'rgba(74,222,128,0)');
    ctx.fillStyle=grad;ctx.beginPath();ctx.arc(x,y,10,0,Math.PI*2);ctx.fill();
    ctx.fillStyle='#DFFFE8';ctx.beginPath();ctx.arc(x,y,2.5,0,Math.PI*2);ctx.fill();
  });
  canvas.onclick=e=>{
    const r=canvas.getBoundingClientRect();
    const scale=canvas.width/r.width;
    const mx=(e.clientX-r.left)*scale,my=(e.clientY-r.top)*scale;
    const hit=pins.find(p=>Math.hypot(p.x-mx,p.y-my)<10);
    const tip=document.getElementById('mapTip');
    if(hit){
      tip.style.display='block';tip.textContent=hit.title;
      tip.style.left=(hit.x/canvas.width*100)+'%';tip.style.top=(hit.y/canvas.height*100)+'%';
      tip.onclick=()=>openTripDetail(hit.id);
    }else{tip.style.display='none';}
  };
}

function drawDonut(canvas,data){
  const ctx=canvas.getContext('2d');
  const w=canvas.width,h=canvas.height,cx=w/2,cy=h/2,r=Math.min(w,h)/2-10,rw=16;
  ctx.clearRect(0,0,w,h);
  const total=data.reduce((s,d)=>s+d.value,0)||1;
  let start=-Math.PI/2;
  data.forEach(d=>{
    const angle=(d.value/total)*Math.PI*2;
    ctx.beginPath();ctx.arc(cx,cy,r,start,start+angle);
    ctx.strokeStyle=d.color;ctx.lineWidth=rw;ctx.stroke();
    start+=angle;
  });
  ctx.fillStyle='#EAF0FB';ctx.font='bold 18px sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.fillText(String(total),cx,cy);
}

function drawYearlyBars(canvas,yearCounts){
  const ctx=canvas.getContext('2d');
  const w=canvas.width,h=canvas.height,pad=6;
  ctx.clearRect(0,0,w,h);
  if(!yearCounts.length)return;
  const max=Math.max(1,...yearCounts.map(y=>y.count));
  const bw=(w-pad*2)/yearCounts.length;
  yearCounts.forEach((y,i)=>{
    const bh=(y.count/max)*(h-20);
    const x=pad+i*bw+bw*0.2;
    ctx.fillStyle=y.highlight?'#F4C95D':'rgba(255,255,255,.35)';
    ctx.beginPath();ctx.roundRect(x,h-bh-16,bw*0.6,bh,3);ctx.fill();
    ctx.fillStyle='rgba(255,255,255,.5)';ctx.font='8px sans-serif';ctx.textAlign='center';
    ctx.fillText(String(y.year).slice(2),x+bw*0.3,h-4);
  });
}
```

- [ ] **Step 3: Call `renderAtlas` from `onTripsUpdate`**

  Old:
  ```js
  function onTripsUpdate(trips){window.__STATS__=computeStats(trips);}
  ```
  New:
  ```js
  function onTripsUpdate(trips){
    window.__STATS__=computeStats(trips);
    renderAtlas(window.__STATS__);
    renderTripsList(window.__STATS__.trips);
  }
  ```
  (`renderTripsList` is defined in Task 5 — leave the call in place; it will throw until then, which is expected and fixed by the end of Task 5.)

- [ ] **Step 4: Manually seed one test trip and verify rendering**

  In the browser console (with a real test Firebase project connected):
  ```js
  createTrip({title:'測試沖繩',destination:'沖繩',region:'east-asia',startDate:'2023-11-01',endDate:'2023-11-07',tags:['海島'],status:'visited',countryCode:['JP'],lat:26.5,lng:127.9});
  ```
  Confirm the Atlas tab shows: stat row with `1 / 1 / 1`, a glowing pin near Japan on the map, a donut with one teal (east-asia) segment, and a bar chart with one highlighted bar for the current year. Clicking the pin should not yet navigate (Task 5 implements `openTripDetail`) — a console error is expected until then.

- [ ] **Step 5: Commit**

```bash
git add travel-atlas.html
git commit -m "feat: render Travel Atlas home with stats, glow map, donut and yearly bar chart"
```

---

## Task 4: Trip list page with region filter pills

**Files:**
- Modify: `travel-atlas.html`

- [ ] **Step 1: Add trip-list CSS**

```css
.filter-row{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;}
.filter-pill{padding:6px 14px;border-radius:20px;font-size:12px;font-weight:700;border:1.5px solid var(--border);background:rgba(255,255,255,.04);color:var(--muted);cursor:pointer;}
.filter-pill.on{background:var(--teal);color:#0B1220;border-color:var(--teal);}
.trip-row{display:flex;align-items:center;gap:12px;padding:13px 14px;margin-bottom:8px;cursor:pointer;}
.trip-flag{font-size:22px;flex-shrink:0;}
.trip-info{flex:1;min-width:0;}
.trip-title{font-weight:700;font-size:15px;}
.trip-meta{font-size:12px;color:var(--muted);margin-top:2px;}
```

- [ ] **Step 2: Add `renderTripsList` and filter state**

  Insert before `// ─── Tabs ─────`:

```js
// ─── Trip list ───────────────────────────────────────
let curRegionFilter='all';

function renderTripsList(trips){
  const box=document.getElementById('tripsBox');
  if(!trips.length){
    box.innerHTML='<div class="empty"><div class="empty-i">🧳</div><div class="empty-h">還沒有旅程</div></div>';
    return;
  }
  const pills=['<div class="filter-pill '+(curRegionFilter==='all'?'on':'')+'" onclick="setRegionFilter(\'all\')">全部</div>']
    .concat(REGIONS.filter(r=>trips.some(t=>t.region===r.id)).map(r=>
      `<div class="filter-pill ${curRegionFilter===r.id?'on':''}" onclick="setRegionFilter('${r.id}')">${r.name}</div>`
    ));
  const filtered=curRegionFilter==='all'?trips:trips.filter(t=>t.region===curRegionFilter);
  const sorted=[...filtered].sort((a,b)=>(b.startDate||'').localeCompare(a.startDate||''));
  box.innerHTML=`<div class="filter-row">${pills.join('')}</div>`+
    sorted.map(t=>`
      <div class="card trip-row" onclick="openTripDetail('${t.id}')">
        <div class="trip-flag">${countryFlags(t.countryCode)}</div>
        <div class="trip-info">
          <div class="trip-title">${esc(t.title)}</div>
          <div class="trip-meta">${(t.startDate||'').slice(0,7).replace('-','.')} · ${REGIONM[t.region]?.name||''}</div>
        </div>
      </div>`).join('');
}
function setRegionFilter(r){curRegionFilter=r;renderTripsList(window.__STATS__.trips);}

const COUNTRY_FLAG={JP:'🇯🇵',AU:'🇦🇺',IT:'🇮🇹',FI:'🇫🇮',TW:'🇹🇼',KR:'🇰🇷',TH:'🇹🇭',IS:'🇮🇸',NZ:'🇳🇿',HR:'🇭🇷',CA:'🇨🇦'};
function countryFlags(codes){return(codes||[]).map(c=>COUNTRY_FLAG[c]||'🏳️').join('')||'🏳️';}
```

- [ ] **Step 3: Verify**

  Reload with the test trip from Task 3 still in the database. Go to the 旅程 tab — confirm the trip row shows 🇯🇵 flag, title, `2023.11 · 東亞`, and a filter pill row with "全部" and "東亞" both selectable. Clicking "東亞" should keep the row visible; the click on the row itself will error until Task 5 adds `openTripDetail` — expected for now.

- [ ] **Step 4: Commit**

```bash
git add travel-atlas.html
git commit -m "feat: add trip list page with region filter pills"
```

---

## Task 5: Trip detail page (cover, timeline entries, entry viewer)

**Files:**
- Modify: `travel-atlas.html`

- [ ] **Step 1: Add detail-page CSS**

```css
.detail-cover{height:180px;border-radius:16px;background:linear-gradient(150deg,var(--bg2),#0E2A3A);background-size:cover;background-position:center;margin-bottom:12px;display:flex;align-items:flex-end;padding:16px;border:1px solid var(--border);}
.detail-title{font-family:'Noto Serif TC',serif;font-size:22px;font-weight:700;color:#fff;text-shadow:0 2px 10px rgba(0,0,0,.6);}
.detail-meta{font-size:12px;color:var(--muted);margin-bottom:14px;}
.tag-pill{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;background:rgba(74,222,128,.15);color:var(--teal);margin:0 6px 6px 0;}
.entry-row{display:flex;gap:12px;padding:13px 14px;margin-bottom:8px;cursor:pointer;}
.entry-thumb{width:52px;height:52px;border-radius:10px;object-fit:cover;flex-shrink:0;background:rgba(255,255,255,.06);}
.entry-info{flex:1;min-width:0;}
.entry-loc{font-size:12px;color:var(--teal);font-weight:700;}
.entry-date{font-size:11px;color:var(--muted);}
.entry-text{font-size:13px;color:var(--text);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.photo-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:10px;}
.photo-grid img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px;}
```

- [ ] **Step 2: Add `openTripDetail` and `renderTripDetail`**

```js
// ─── Trip detail ─────────────────────────────────────
function openTripDetail(tripId){
  curDetailTripId=tripId;
  goTab('detail');
  entriesRef(tripId).on('value',snap=>renderTripDetail(tripId,snap.val()||{}));
}
function renderTripDetail(tripId,entries){
  const trip=(window.__STATS__.trips||[]).find(t=>t.id===tripId);
  if(!trip)return;
  const box=document.getElementById('detailBox');
  const list=Object.entries(entries).map(([id,e])=>({id,...e})).sort((a,b)=>(a.date||'').localeCompare(b.date||''));
  box.innerHTML=`
    <div class="detail-cover" style="${trip.coverPhotoUrl?`background-image:url('${trip.coverPhotoUrl}')`:''}">
      <div><div class="detail-title">${esc(trip.title)}</div></div>
    </div>
    <div class="detail-meta">${(trip.startDate||'').replace(/-/g,'.')} – ${(trip.endDate||'').replace(/-/g,'.')} · ${REGIONM[trip.region]?.name||''}</div>
    <div>${(trip.tags||[]).map(tag=>`<span class="tag-pill">${esc(tag)}</span>`).join('')}</div>
    <div style="margin-top:14px">
      ${list.length?list.map(e=>`
        <div class="card entry-row" onclick="openEntryView('${tripId}','${e.id}')">
          ${e.photos&&e.photos[0]?`<img class="entry-thumb" src="${e.photos[0]}">`:'<div class="entry-thumb"></div>'}
          <div class="entry-info">
            <div class="entry-loc">${esc(e.location||'')}</div>
            <div class="entry-date">${(e.date||'').replace(/-/g,'.')}</div>
            <div class="entry-text">${esc(e.text||'')}</div>
          </div>
        </div>`).join(''):'<div class="empty"><div class="empty-i">📔</div><div class="empty-h">還沒有日記</div></div>'}
    </div>
    <button class="btn btn-g btn-w" style="margin-top:8px" onclick="goTab('trips')">← 回旅程列表</button>`;
}
function openEntryView(tripId,entryId){
  entriesRef(tripId).child(entryId).once('value',snap=>{
    const e=snap.val();if(!e)return;
    const photos=(e.photos||[]).map(p=>`<img src="${p}">`).join('');
    document.getElementById('detailBox').insertAdjacentHTML('beforeend',`
      <div class="ov open" onclick="if(event.target===this)this.remove()">
        <div class="sheet">
          <div class="hdl"></div>
          <div class="st">${(e.date||'').replace(/-/g,'.')} · ${esc(e.location||'')}</div>
          <p style="font-size:14px;line-height:1.7;white-space:pre-wrap">${esc(e.text||'')}</p>
          ${photos?`<div class="photo-grid">${photos}</div>`:''}
        </div>
      </div>`);
  });
}
```

- [ ] **Step 3: Wire `goTab('detail')` into the page-routing CSS**

  `page-detail` already exists in the Task 1 HTML skeleton, so no markup change is needed — confirm `goTab('detail')` correctly hides the tabbar highlight (no tab in the tabbar maps to `detail`, which is intentional: it's reached only via drill-down, not a tab).

- [ ] **Step 4: Verify end-to-end**

  Reload with the test trip. From Atlas map, click the glowing pin → should land on the detail page showing the cover block, title, dates, tags, and "還沒有日記" empty state. From the 旅程 tab, click the trip row → same result. Click "← 回旅程列表" → returns to the 旅程 tab.

  Then manually add one entry via console:
  ```js
  createEntry('<the-trip-id-from-Task-3>',{date:'2023-11-02',location:'那霸市場',text:'第一天在那霸吃了海葡萄跟塔可飯，超市場超熱鬧。',category:'food',photos:[]});
  ```
  Confirm it appears as a timeline row, and clicking it opens the bottom sheet with the full text.

- [ ] **Step 5: Commit**

```bash
git add travel-atlas.html
git commit -m "feat: add trip detail page with journal entry timeline and entry viewer"
```

---

## Task 6: Add Trip sheet

**Files:**
- Modify: `travel-atlas.html`

- [ ] **Step 1: Add the sheet markup**

  Insert before `<div class="toast" id="toast"></div>`:

```html
<div class="ov" id="m-trip">
  <div class="sheet">
    <div class="hdl"></div><div class="st">新增旅程</div>
    <div class="fg"><label class="lb">標題</label><input class="inp" id="mt_title" placeholder="例：2026/07 京都"></div>
    <div class="fg"><label class="lb">目的地</label><input class="inp" id="mt_dest" placeholder="例：京都"></div>
    <div class="fg"><label class="lb">地區</label><div class="tw" id="mt_region"></div></div>
    <div class="fr">
      <div class="fg"><label class="lb">出發日期</label><input class="inp" id="mt_start" type="date"></div>
      <div class="fg"><label class="lb">結束日期</label><input class="inp" id="mt_end" type="date"></div>
    </div>
    <div class="fr">
      <div class="fg"><label class="lb">緯度</label><input class="inp" id="mt_lat" type="number" step="0.01" placeholder="例：26.21"></div>
      <div class="fg"><label class="lb">經度</label><input class="inp" id="mt_lng" type="number" step="0.01" placeholder="例：127.68"></div>
    </div>
    <div class="fg"><label class="lb">標籤（逗號分隔）</label><input class="inp" id="mt_tags" placeholder="海島, 潛水"></div>
    <div class="fr"><button class="btn btn-g" style="flex:1" onclick="closeM('m-trip')">取消</button><button class="btn btn-b" style="flex:2" onclick="saveTrip()">建立</button></div>
  </div>
</div>
```

- [ ] **Step 2: Add JS to populate the region picker and save**

```js
// ─── Add Trip ────────────────────────────────────────
let selTripRegion='east-asia';
function openAddTripSheet(){
  document.getElementById('mt_region').innerHTML=REGIONS.map(r=>
    `<div class="to ${r.id===selTripRegion?'on':''}" onclick="selTripRegionPick('${r.id}')">${r.name}</div>`
  ).join('');
  ['mt_title','mt_dest','mt_start','mt_end','mt_lat','mt_lng','mt_tags'].forEach(id=>document.getElementById(id).value='');
  openM('m-trip');
}
function selTripRegionPick(id){
  selTripRegion=id;
  document.querySelectorAll('#mt_region .to').forEach(el=>el.classList.remove('on'));
  event.target.classList.add('on');
}
function saveTrip(){
  const title=document.getElementById('mt_title').value.trim();
  const start=document.getElementById('mt_start').value;
  if(!title||!start){toast('⚠️ 標題與出發日期必填');return;}
  const id=createTrip({
    title,
    destination:document.getElementById('mt_dest').value.trim(),
    region:selTripRegion,
    startDate:start,
    endDate:document.getElementById('mt_end').value||start,
    lat:parseFloat(document.getElementById('mt_lat').value)||null,
    lng:parseFloat(document.getElementById('mt_lng').value)||null,
    tags:document.getElementById('mt_tags').value.split(',').map(s=>s.trim()).filter(Boolean),
    status:'visited',
    countryCode:[],
  });
  closeM('m-trip');
  toast('✅ 已建立旅程');
  openTripDetail(id);
}
```

- [ ] **Step 3: Verify**

  Trigger `openAddTripSheet()` from the console, fill in title "測試墨爾本" + today's date, pick region 大洋洲, save. Confirm a toast appears, the sheet closes, and you land on the new trip's detail page. Confirm the Atlas tab's stat row now shows 2 trips.

- [ ] **Step 4: Commit**

```bash
git add travel-atlas.html
git commit -m "feat: add create-trip sheet"
```

---

## Task 7: Add Entry sheet with photo picker + Storage upload

**Files:**
- Modify: `travel-atlas.html`

- [ ] **Step 1: Add the sheet markup**

  Insert after the `m-trip` sheet:

```html
<div class="ov" id="m-entry">
  <div class="sheet">
    <div class="hdl"></div><div class="st">新增日記</div>
    <input type="hidden" id="me_tripid">
    <div class="fg"><label class="lb">日期</label><input class="inp" id="me_date" type="date"></div>
    <div class="fg"><label class="lb">地點</label><input class="inp" id="me_loc" placeholder="例：那霸市場"></div>
    <div class="fg"><label class="lb">分類</label><div class="tw" id="me_cat"></div></div>
    <div class="fg"><label class="lb">內文</label><textarea class="ta" id="me_text" placeholder="今天做了什麼、有什麼感受…"></textarea></div>
    <div class="fg"><label class="lb">照片</label>
      <div class="photo-grid" id="mePhotoPreview"></div>
      <button class="btn btn-g btn-w" style="margin-top:8px" onclick="document.getElementById('mePhotoFile').click()">📷 選擇照片</button>
      <input type="file" id="mePhotoFile" accept="image/*" multiple style="display:none" onchange="onEntryPhotosPick(event)">
    </div>
    <div class="fr"><button class="btn btn-g" style="flex:1" onclick="closeM('m-entry')">取消</button><button class="btn btn-b" style="flex:2" onclick="saveEntry()">儲存</button></div>
  </div>
</div>
```

- [ ] **Step 2: Add entry-category constants + sheet JS**

```js
// ─── Add Entry ───────────────────────────────────────
const ENTRY_CATS=[{id:'food',name:'美食'},{id:'sight',name:'景點'},{id:'hotel',name:'住宿'},{id:'transport',name:'交通'}];
let selEntryCat='sight',pendingPhotoFiles=[];

function openAddEntrySheet(){
  if(!curDetailTripId){toast('⚠️ 請先進入一趟旅程再新增日記');return;}
  document.getElementById('me_tripid').value=curDetailTripId;
  document.getElementById('me_date').value=new Date().toLocaleDateString('en-CA');
  document.getElementById('me_loc').value='';
  document.getElementById('me_text').value='';
  pendingPhotoFiles=[];
  document.getElementById('mePhotoPreview').innerHTML='';
  document.getElementById('me_cat').innerHTML=ENTRY_CATS.map(c=>
    `<div class="to ${c.id===selEntryCat?'on':''}" onclick="selEntryCatPick('${c.id}')">${c.name}</div>`
  ).join('');
  openM('m-entry');
}
function selEntryCatPick(id){
  selEntryCat=id;
  document.querySelectorAll('#me_cat .to').forEach(el=>el.classList.remove('on'));
  event.target.classList.add('on');
}
function onEntryPhotosPick(ev){
  pendingPhotoFiles=Array.from(ev.target.files||[]);
  const prev=document.getElementById('mePhotoPreview');
  prev.innerHTML='';
  pendingPhotoFiles.forEach(f=>{
    const img=document.createElement('img');
    img.src=URL.createObjectURL(f);
    prev.appendChild(img);
  });
}
async function uploadEntryPhotos(tripId,entryId,files){
  const urls=[];
  for(const file of files){
    const path=`trips/${tripId}/entries/${entryId}/${uid()}-${file.name}`;
    const ref=STORAGE.ref().child(path);
    await ref.put(file);
    urls.push(await ref.getDownloadURL());
  }
  return urls;
}
async function saveEntry(){
  const tripId=document.getElementById('me_tripid').value;
  const date=document.getElementById('me_date').value;
  if(!date){toast('⚠️ 日期必填');return;}
  const entryId=createEntry(tripId,{
    date,
    location:document.getElementById('me_loc').value.trim(),
    text:document.getElementById('me_text').value.trim(),
    category:selEntryCat,
    photos:[],
  });
  closeM('m-entry');
  toast('✅ 已儲存日記');
  if(pendingPhotoFiles.length){
    toast('📤 上傳照片中…');
    try{
      const urls=await uploadEntryPhotos(tripId,entryId,pendingPhotoFiles);
      updateEntry(tripId,entryId,{photos:urls});
      toast('✅ 照片已上傳');
    }catch(e){toast('⚠️ 照片上傳失敗，可稍後重試');console.error(e);}
  }
}
```

- [ ] **Step 3: Wire the FAB**

  Replace the Task 1 placeholder:

  Old:
  ```js
  function fabTap(){ /* wired to openAddEntrySheet() in Task 9 */ }
  ```
  New:
  ```js
  function fabTap(){
    if(curTab==='detail')openAddEntrySheet();
    else if(curTab==='trips')toast('請先點進一趟旅程再新增日記');
    else openAddTripSheet();
  }
  ```

- [ ] **Step 4: Verify end-to-end**

  From the trip detail page created in Task 6, tap the FAB → entry sheet opens. Fill date/location/text, pick 2 photos from disk, save. Confirm: toast sequence (儲存→上傳中→已上傳), the entry appears in the timeline with a thumbnail, and opening it shows both photos in the grid. Check the Firebase console Storage tab to confirm the files landed under `trips/<id>/entries/<id>/`.

- [ ] **Step 5: Commit**

```bash
git add travel-atlas.html
git commit -m "feat: add entry sheet with multi-photo picker and Storage upload"
```

---

## Task 8: Offline outbox for entries

**Files:**
- Modify: `travel-atlas.html`

- [ ] **Step 1: Add outbox helpers**

  Insert before `// ─── Add Entry ─────`:

```js
// ─── Offline outbox ──────────────────────────────────
function outboxRead(){return JSON.parse(localStorage.getItem('travel_atlas_outbox')||'[]');}
function outboxWrite(items){localStorage.setItem('travel_atlas_outbox',JSON.stringify(items));}
function outboxAdd(item){const items=outboxRead();items.push(item);outboxWrite(items);}
async function outboxFlush(){
  if(!navigator.onLine||!DB)return;
  const items=outboxRead();
  if(!items.length)return;
  toast('🔄 同步離線紀錄中…');
  for(const item of items){
    createEntry(item.tripId,item.entry);
  }
  outboxWrite([]);
  toast('✅ 離線紀錄已同步');
}
window.addEventListener('online',outboxFlush);
```

- [ ] **Step 2: Fall back to the outbox when `saveEntry` can't reach Firebase**

  Modify `saveEntry` (from Task 7) — wrap the `createEntry` call:

  Old:
  ```js
  async function saveEntry(){
    const tripId=document.getElementById('me_tripid').value;
    const date=document.getElementById('me_date').value;
    if(!date){toast('⚠️ 日期必填');return;}
    const entryId=createEntry(tripId,{
      date,
      location:document.getElementById('me_loc').value.trim(),
      text:document.getElementById('me_text').value.trim(),
      category:selEntryCat,
      photos:[],
    });
  ```
  New:
  ```js
  async function saveEntry(){
    const tripId=document.getElementById('me_tripid').value;
    const date=document.getElementById('me_date').value;
    if(!date){toast('⚠️ 日期必填');return;}
    const entry={
      date,
      location:document.getElementById('me_loc').value.trim(),
      text:document.getElementById('me_text').value.trim(),
      category:selEntryCat,
      photos:[],
    };
    if(!navigator.onLine){
      outboxAdd({tripId,entry});
      closeM('m-entry');
      toast('📴 離線中，已暫存，連網後自動同步（照片需連網後重新上傳）');
      return;
    }
    const entryId=createEntry(tripId,entry);
  ```

  Leave the rest of the function (toast + photo upload block) unchanged — it now runs only in the online path.

- [ ] **Step 3: Flush the outbox on boot**

  In `connectFB`, right after `STORAGE=firebase.storage();`, add:
  ```js
  outboxFlush();
  ```

- [ ] **Step 4: Verify**

  In devtools, use the Network tab's "Offline" throttling preset. Add an entry — confirm the toast says "離線中，已暫存…" and no error is thrown. Turn the network back online — confirm the "🔄 同步離線紀錄中…" then "✅ 離線紀錄已同步" toasts fire and the entry appears in the timeline (photos will be absent, matching the documented limitation).

- [ ] **Step 5: Commit**

```bash
git add travel-atlas.html
git commit -m "feat: queue journal entries in localStorage outbox when offline, sync on reconnect"
```

---

## Task 9: Settings page cleanup + manual QA pass

**Files:**
- Modify: `travel-atlas.html`

- [ ] **Step 1: Confirm the 設定 tab already works**

  The `page-cfg` markup from Task 1 already has the "變更 Firebase 連線" form. No new code needed — this step is a check, not a change.

- [ ] **Step 2: Full manual walkthrough (matches the spec's Testing section)**

  With a real Firebase test project connected, and airplane mode off:
  1. Fresh setup: clear `localStorage`, reload, enter DB URL + bucket → lands on Atlas home with 0 trips
  2. Add trip via FAB (on Atlas tab) → appears in 旅程 tab, filterable by its region
  3. Open trip → add 2 entries with photos on different dates → confirm timeline sorted oldest→newest
  4. Atlas home now shows updated stat row, a second glow pin (if lat/lng given), updated donut/bar
  5. Toggle offline, add an entry, toggle online, confirm outbox sync toast and entry appears
  6. Reload the page entirely → confirm session persists (no setup screen shown again) and all data still renders

  Record any bug found as a new checklist item and fix before moving to Task 10.

- [ ] **Step 3: Commit** (only if Step 2 required fixes)

```bash
git add travel-atlas.html
git commit -m "fix: address issues found in Travel Atlas manual QA pass"
```

---

## Task 10: Data migration — seed script + Notion/Notes content

**Files:**
- Create: `seed-data/travel-atlas-seed.json`
- Create: `scripts/seed-travel-atlas.mjs`

- [ ] **Step 1: Ask the user for the still-missing Apple Notes content**

  This step is a conversation action, not a code change: for each already-identified visited trip (2023/11 沖繩, 2024/04 東京櫻花, 2025/03 墨爾本, 2025/05 多羅米蒂, 2025/08 東京熱海, 2025/12 京都楓葉, 2026/01 長野雪地健行, 2026/02 芬蘭極光), ask the user to paste the relevant Apple Notes text (diary/心得) and provide any photos they want migrated. Skip trips they say have no real diary content — those get a Trip entry with no journal entries, addable later in-app.

- [ ] **Step 2: Build `seed-data/travel-atlas-seed.json`**

  Shape it as an array of trip objects, each with an `entries` array, using the Notion-derived `destination`/`region`/approximate dates already gathered in this session plus whatever text the user pasted in Step 1. Example shape (fill with real content, not placeholder text):

```json
[
  {
    "title": "2023/11 沖繩",
    "destination": "沖繩",
    "region": "east-asia",
    "startDate": "2023-11-01",
    "endDate": "2023-11-07",
    "lat": 26.21,
    "lng": 127.68,
    "tags": ["離島", "海島", "聖誕節"],
    "status": "visited",
    "countryCode": ["JP"],
    "entries": [
      {"date": "2023-11-02", "location": "那霸", "text": "<使用者提供的備忘錄內容>", "category": "food", "photos": []}
    ]
  }
]
```

  Photos: if the user hands over image files, place them under `seed-data/photos/<trip-slug>/` and reference the local file path in a `localPhotoPaths` array per entry (the seed script uploads these to Storage and rewrites them into `photos` URLs — see Step 4).

- [ ] **Step 3: Write the seed script**

```js
// scripts/seed-travel-atlas.mjs
import { readFileSync } from 'node:fs';
import { initializeApp } from 'firebase/app';
import { getDatabase, ref, push, set } from 'firebase/database';
import { getStorage, ref as sref, uploadBytes, getDownloadURL } from 'firebase/storage';

const [,, dbUrl, bucket] = process.argv;
if (!dbUrl || !bucket) {
  console.error('Usage: node scripts/seed-travel-atlas.mjs <databaseURL> <storageBucket>');
  process.exit(1);
}

const app = initializeApp({ databaseURL: dbUrl, storageBucket: bucket });
const db = getDatabase(app);
const storage = getStorage(app);

const trips = JSON.parse(readFileSync(new URL('../seed-data/travel-atlas-seed.json', import.meta.url)));

for (const trip of trips) {
  const { entries = [], ...tripFields } = trip;
  const tripRef = push(ref(db, '/trips'));
  await set(tripRef, tripFields);
  console.log(`Trip created: ${trip.title} (${tripRef.key})`);

  for (const entry of entries) {
    const { localPhotoPaths = [], ...entryFields } = entry;
    const photoUrls = [];
    for (const localPath of localPhotoPaths) {
      const bytes = readFileSync(new URL(`../${localPath}`, import.meta.url));
      const fileRef = sref(storage, `trips/${tripRef.key}/entries/seed-${Date.now()}-${localPath.split('/').pop()}`);
      await uploadBytes(fileRef, bytes);
      photoUrls.push(await getDownloadURL(fileRef));
    }
    const entryRef = push(ref(db, `/trips/${tripRef.key}/entries`));
    await set(entryRef, { ...entryFields, photos: photoUrls });
  }
}
console.log('Seed complete.');
```

- [ ] **Step 4: Install the one dependency and run it**

```bash
npm install firebase --no-save
node scripts/seed-travel-atlas.mjs "https://<your-project>-default-rtdb.firebaseio.com" "<your-project>.appspot.com"
```

  Expected output: one `Trip created: ...` line per trip, ending with `Seed complete.`

- [ ] **Step 5: Verify in the app**

  Open `travel-atlas.html`, connect with the same DB URL/bucket used above. Confirm the Atlas home stat row matches the number of seeded trips, the map shows a pin per trip with lat/lng, and each trip's detail page shows the migrated entries with correct text and photos.

- [ ] **Step 6: Commit**

```bash
git add seed-data scripts/seed-travel-atlas.mjs
git commit -m "feat: add Travel Atlas migration seed data and seed script"
```

---

## Self-Review Notes

- **Spec coverage:** dark theme (Task 1), stats/map/charts (Task 3), trip list + region filter (Task 4), trip detail timeline (Task 5), add trip/entry with photo upload (Tasks 6–7), offline outbox (Task 8), RTDB+Storage architecture (Task 1), migration (Task 10), manual QA in lieu of automated tests (Task 9) — all spec sections are covered.
- **Type consistency:** `tripId`/`entryId` naming, `REGIONS`/`REGIONM`, `computeStats()` return shape, and `photos`/`countryCode` array fields are used consistently from Task 2 onward; verified no renamed fields across tasks.
- **No placeholders:** all steps contain complete, runnable code; the one open item (Apple Notes text content) is explicitly scoped as a user-input step in Task 10, not a code TODO.
