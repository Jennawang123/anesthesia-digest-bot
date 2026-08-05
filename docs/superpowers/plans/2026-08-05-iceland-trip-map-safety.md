# 冰島版每日地圖／安全資訊／Day 導覽列／住宿總整理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為 `iceland-trip.html` 加上每日地圖、附近警局／急診安全資訊、Day 導覽列與住宿總整理，並補上讓這些功能在無訊號時仍可用的 localStorage 快照層。

**Architecture:** 單檔 HTML PWA，無 build step，所有程式碼寫在既有的 `<script>` 區塊內。活動座標由 Nominatim 解析後快取回 Firebase `/schedule/{did}/acts/{aid}/geo`；每日安全資訊由 Overpass + OSRM 預抓後快取回 `/safety/{did}`。Firebase 資料整包鏡射到 localStorage 供離線讀取。所有外部查詢都經過距離合理性檢查，防止地理編碼服務回傳看似正常實則錯誤的結果。

**Tech Stack:** 原生 JS（無框架）、Firebase Realtime Database compat SDK、Leaflet 1.9.4（CDN 延遲載入）、Nominatim、Photon、Overpass API、OSRM

**Spec:** `docs/superpowers/specs/2026-08-05-iceland-trip-map-safety-design.md`

---

## 檔案結構

本專案是單檔 PWA，不新增檔案。所有改動集中在 `iceland-trip.html`，依區塊歸位：

| 區塊 | 位置 | 本次新增的責任 |
|---|---|---|
| CSS | `<style>` 內，約 `:43-220` | day-strip、day-map、safety-card、overview、狀態面板的樣式 |
| HTML 結構 | `:271-360` | `#dayStrip`、`#overviewBox` 容器；設定頁狀態面板 |
| 工具函式 | `:493-535` 附近 | `haversine()`、`stripImages()`、快照存取 |
| 地理解析 | 新區塊，置於 `geocodeCity()`（`:536`）之後 | `geoCandidates()`、`sanityCheck()`、`geoResolve()`、`geoQueue`、`ensureActGeo()` |
| 安全資訊 | 新區塊，置於地理解析之後 | `dayBaseLatLng()`、`fetchSafety()`、`ensureSafety()` |
| 渲染 | `renderSched()`（`:1114`）附近 | `renderDayStrip()`、`renderOverview()`、`dayMapHtml()`、`mountDayMap()`、`safetyHtml()` |
| 自我測試 | 檔案末端 `</script>` 前 | `window._selftest()` |

**測試策略**：本專案無測試框架，spec 已明訂不引入（會破壞 single-file 架構）。取代方案是內嵌 `window._selftest()`，內含純函式的斷言，在瀏覽器 console 執行。純函式（`haversine`、`geoCandidates`、`stripImages`、`sanityCheck`、`dayBaseLatLng`）走 TDD：先寫斷言、跑到失敗、再實作。涉及 DOM 與網路的部分改用明確的手動驗證步驟。

---

## Task 0: 驗證四個外部 API 在瀏覽器可用

先前的可行性測試全部用 curl 完成。瀏覽器有 CORS 限制，且 `fetch` **無法設定 `User-Agent`**（規範禁止，設了會被忽略並產生 console 警告）。Nominatim 政策要求以 User-Agent 或 Referer 識別來源，瀏覽器會自動送出 Referer，這是可接受的識別方式。這一步確認四個服務都能從瀏覽器直接呼叫，避免整份實作做完才發現被 CORS 擋掉。

**Files:** 無（純驗證）

- [ ] **Step 1: 開啟已部署的冰島版 app，在 DevTools console 貼入以下程式碼**

```js
(async()=>{
  const r=[];
  const t=async(name,fn)=>{try{r.push([name,'✅',await fn()]);}catch(e){r.push([name,'❌',e.message]);}};

  await t('Nominatim',async()=>{
    const d=await (await fetch('https://nominatim.openstreetmap.org/search?q=Seljalandsfoss&format=json&limit=1&countrycodes=is,no')).json();
    return d[0] ? `${d[0].lat},${d[0].lon}` : '空結果';
  });
  await t('Photon',async()=>{
    const d=await (await fetch('https://photon.komoot.io/api?q=Seljalandsfoss&limit=1')).json();
    return d.features?.[0]?.geometry?.coordinates?.join(',') ?? '空結果';
  });
  await t('Overpass',async()=>{
    const q='[out:json][timeout:25];node[amenity=police](around:30000,63.4188,-19.0055);out center tags;';
    const d=await (await fetch('https://overpass-api.de/api/interpreter',{method:'POST',body:q})).json();
    return `${d.elements.length} 筆`;
  });
  await t('OSRM',async()=>{
    const d=await (await fetch('https://router.project-osrm.org/route/v1/driving/-16.3722,64.0142;-15.2082,64.2539?overview=false')).json();
    return d.code==='Ok' ? `${(d.routes[0].distance/1000).toFixed(1)}km` : d.code;
  });
  console.table(r);
})();
```

- [ ] **Step 2: 確認四項全部為 ✅**

預期輸出（數值可能微幅不同）：

```
Nominatim  ✅  63.6154571,-19.9881686
Photon     ✅  -19.9881686,63.6154571
Overpass   ✅  1 筆
OSRM       ✅  75.2km
```

**若有任何一項是 ❌**：記下錯誤訊息並停止，不要繼續後續任務。CORS 被擋代表該服務需要改走替代方案（例如換 Overpass 鏡像站 `https://overpass.kumi.systems/api/interpreter`），這會改變後續任務的實作，必須先回報。

- [ ] **Step 3: 不需 commit**

本任務無檔案改動。

---

## Task 1: 快照工具函式（`stripImages` + `haversine`）

兩個純函式，是後續所有任務的基礎。

**Files:**
- Modify: `iceland-trip.html`（工具函式區，`:497` 的 `fmtD` 之後）
- Modify: `iceland-trip.html`（檔案末端 `</script>` 之前，新增 `_selftest`）

- [ ] **Step 1: 寫失敗的測試**

在 `iceland-trip.html` 檔案末端、`</script>` 標籤的前一行插入：

```js
// ─── 自我測試（開發用，在 console 執行 _selftest()）─────────────
function _selftest(){
  const out=[];let pass=0,fail=0;
  const ok=(name,cond,extra='')=>{cond?pass++:fail++;out.push(`${cond?'✅':'❌'} ${name}${extra&&!cond?'  → '+extra:''}`);};
  const near=(a,b,tol)=>Math.abs(a-b)<=tol;

  // ---- stripImages ----
  {
    const src={config:{title:'x'},schedule:{day1:{date:'2026-09-14',acts:{a1:{name:'溫泉',loc:'Blue Lagoon',images:['data:image/jpeg;base64,AAAA']}}}}};
    const r=stripImages(src);
    ok('stripImages 移除 images', r.schedule.day1.acts.a1.images===undefined);
    ok('stripImages 保留其他欄位', r.schedule.day1.acts.a1.loc==='Blue Lagoon');
    ok('stripImages 保留 config', r.config.title==='x');
    ok('stripImages 不改動原物件', src.schedule.day1.acts.a1.images.length===1);
  }

  // ---- haversine（實測座標）----
  {
    ok('haversine 冰川湖→東南城鎮 62.4km', near(haversine(64.0142,-16.3722,64.2539,-15.2082),62.4,1.0),
       String(haversine(64.0142,-16.3722,64.2539,-15.2082)));
    ok('haversine 溫泉→首都 38.1km', near(haversine(63.8792,-22.4443,64.1360,-21.9270),38.1,1.0),
       String(haversine(63.8792,-22.4443,64.1360,-21.9270)));
    ok('haversine 同點為 0', haversine(64,-19,64,-19)===0);
  }

  console.log(out.join('\n')+`\n\n通過 ${pass} / 失敗 ${fail}`);
  return fail===0;
}
window._selftest=_selftest;
```

- [ ] **Step 2: 在瀏覽器 console 執行 `_selftest()`，確認失敗**

Run: 開啟 app → DevTools console → `_selftest()`

Expected: `ReferenceError: stripImages is not defined`

- [ ] **Step 3: 實作兩個純函式**

在 `iceland-trip.html:497`（`const fmtD=...` 那一行）之後插入：

```js
// 兩點間大圓距離（公里）。安全資訊的 fallback 距離與 sanityCheck 的距離門檻都用它。
function haversine(lat1,lng1,lat2,lng2){
  const R=6371,rad=d=>d*Math.PI/180;
  const dLat=rad(lat2-lat1),dLng=rad(lng2-lng1);
  const a=Math.sin(dLat/2)**2+Math.cos(rad(lat1))*Math.cos(rad(lat2))*Math.sin(dLng/2)**2;
  return 2*R*Math.asin(Math.sqrt(a));
}
// 深層複製並拿掉所有活動照片。照片是 base64（單張 100-500KB、每活動上限 6 張），
// localStorage 單一網域只有 5MB，不排除會整個寫入失敗，連行程文字都存不進去。
function stripImages(data){
  const c=JSON.parse(JSON.stringify(data||{}));
  Object.values(c.schedule||{}).forEach(day=>{
    Object.values(day.acts||{}).forEach(act=>{delete act.images;});
  });
  Object.values(c.notes||{}).forEach(n=>{delete n.images;});
  return c;
}
```

- [ ] **Step 4: 再次執行 `_selftest()`，確認全部通過**

Run: DevTools console → `_selftest()`

Expected:
```
✅ stripImages 移除 images
✅ stripImages 保留其他欄位
✅ stripImages 保留 config
✅ stripImages 不改動原物件
✅ haversine 冰川湖→東南城鎮 62.4km
✅ haversine 溫泉→首都 38.1km
✅ haversine 同點為 0

通過 7 / 失敗 0
```

- [ ] **Step 5: Commit**

```bash
git add iceland-trip.html
git commit -m "feat(iceland): 加入 haversine 與 stripImages 工具函式與自我測試"
```

---

## Task 2: localStorage 快照讀寫

**Files:**
- Modify: `iceland-trip.html:629`（`saveDevice` 之後加入快照函式）
- Modify: `iceland-trip.html:790-817`（`_fbListen` 內寫入快照）
- Modify: `iceland-trip.html:688-697`（`bootApp` 先用快照渲染）

- [ ] **Step 1: 加入快照存取函式**

在 `iceland-trip.html:629`（`function saveDevice(){...}` 那一行）之後插入：

```js
// ─── 離線快照 ───────────────────────────────────────
// Firebase RTDB 的 web SDK 沒有磁碟持久化（setPersistenceEnabled 只有 iOS/Android 有），
// 沒有這層快照，沒訊號時整個 app 是空白的——而安全資訊要用的正是沒訊號的時候。
const SNAP_KEY='iceland_trip_snap';
function snapSave(data){
  try{
    localStorage.setItem(SNAP_KEY,JSON.stringify({at:new Date().toISOString(),data:stripImages(data)}));
  }catch(e){
    // 配額爆了就把快照清掉，不要讓它擋住其他 localStorage 寫入（連線資訊比快照重要）
    console.warn('快照寫入失敗，已清除：',e.message);
    try{localStorage.removeItem(SNAP_KEY);}catch(_){}
  }
}
function snapLoad(){
  try{
    const raw=localStorage.getItem(SNAP_KEY);
    if(!raw)return null;
    const o=JSON.parse(raw);
    return (o&&o.data)?o:null;
  }catch(e){return null;}
}
```

- [ ] **Step 2: 在 `_fbListen` 收到資料時寫入快照**

在 `iceland-trip.html` 找到 `_fbListen()` 內的這一行（約 `:814`）：

```js
    sync(false);
```

改成：

```js
    snapSave(d);
    sync('ok');
```

- [ ] **Step 3: `bootApp` 先用快照渲染**

在 `iceland-trip.html` 找到 `bootApp()` 內的這一行（約 `:696`）：

```js
  loadFirebase(()=>connectFB());
```

在它之前插入：

```js
  // 先用上次的快照把畫面畫出來，Firebase 連上後再覆蓋。沒訊號時這就是唯一的資料來源。
  const snap=snapLoad();
  if(snap){
    const d=snap.data;
    lastSched=d.schedule||{};lastExps=d.expenses||{};lastNotes=d.notes||{};lastSafety=d.safety||{};
    if(d.config)applyTripCfg(d.config);
    renderSched(lastSched);renderExp(lastExps);renderStat(lastExps);renderNotes(lastNotes);
  }
```

- [ ] **Step 4: 宣告 `lastSafety` 全域變數**

在 `iceland-trip.html:486` 找到這一行：

```js
let curNT='text',curImg=null,curPieCur='JPY',lastExps={},lastNotes={},lastSched={},exchRates={},curActImages=[];
```

改成：

```js
let curNT='text',curImg=null,curPieCur='JPY',lastExps={},lastNotes={},lastSched={},exchRates={},curActImages=[],lastSafety={};
```

- [ ] **Step 5: 在 `_fbListen` 內接住 `/safety`**

在 `iceland-trip.html` 找到 `_fbListen()` 內的這一行（約 `:801`）：

```js
    lastSched=sched;
```

改成：

```js
    lastSched=sched;
    lastSafety=d.safety||{};
```

- [ ] **Step 6: 手動驗證離線可用**

1. 開啟 app，等待「已同步」
2. DevTools → Application → Local Storage，確認有 `iceland_trip_snap`，展開 `data` 應看得到 `schedule` 但 `acts.*.images` 不存在
3. DevTools → Network → 勾選 **Offline**
4. 重新整理頁面
5. 預期：行程日卡照常出現（不是「載入中…」），活動名稱與地點都在

- [ ] **Step 7: Commit**

```bash
git add iceland-trip.html
git commit -m "feat(iceland): 加入 localStorage 快照，離線可開啟行程"
```

---

## Task 3: `sync()` 三態與離線指示

**Files:**
- Modify: `iceland-trip.html:43-44`（CSS 加 `.dot.off`）
- Modify: `iceland-trip.html:504`（`sync` 改三態）
- Modify: `iceland-trip.html:817`（listener 錯誤處理改用新狀態）
- Modify: `iceland-trip.html:696` 附近（`bootApp` 註冊 online/offline 事件）

- [ ] **Step 1: 加入離線狀態的 CSS**

在 `iceland-trip.html:44` 找到這一行：

```css
.dot.busy{background:var(--orange);animation:pulse 1s infinite;}
```

在它之後插入：

```css
.dot.off{background:#9A8F89;}
```

- [ ] **Step 2: 改寫 `sync()` 為三態**

在 `iceland-trip.html:504` 找到這一行：

```js
function sync(on){document.getElementById('syncDot').className='dot'+(on?' busy':'');document.getElementById('syncTxt').textContent=on?'同步中…':'已同步';}
```

改成：

```js
// 三態：'ok' 已同步 / 'busy' 同步中 / 'offline' 離線（顯示快照時間，讓人知道看到的是什麼時候的資料）
function sync(state){
  if(state===true)state='busy';
  if(state===false)state='ok';
  const dot=document.getElementById('syncDot'),txt=document.getElementById('syncTxt');
  if(state==='offline'){
    const snap=snapLoad();
    const t=snap?new Date(snap.at).toLocaleString('zh-TW',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'';
    dot.className='dot off';
    txt.textContent=t?`離線 · ${t} 的資料`:'離線';
  }else if(state==='busy'){
    dot.className='dot busy';txt.textContent='同步中…';
  }else{
    dot.className='dot';txt.textContent='已同步';
  }
}
```

保留 `true`/`false` 的相容轉換，因為 `sync(true)` 在既有程式碼多處被呼叫（例如 `:776` 的 `connectFB`），這次不逐一改寫。

- [ ] **Step 3: listener 錯誤時改顯示離線**

在 `iceland-trip.html` 找到 `_fbListen()` 結尾的錯誤處理（約 `:817`）：

```js
  },err=>{sync(false);toast('⚠️ Firebase 錯誤：'+err.message);});
```

改成：

```js
  },err=>{sync(navigator.onLine?'ok':'offline');toast('⚠️ Firebase 錯誤：'+err.message);});
```

- [ ] **Step 4: 註冊 online / offline 事件**

在 `iceland-trip.html` 的 `bootApp()` 內，Step 3 加入的快照渲染程式碼之後、`loadFirebase(()=>connectFB());` 之前插入：

```js
  if(!navigator.onLine)sync('offline');
  window.addEventListener('offline',()=>sync('offline'));
  window.addEventListener('online',()=>sync('busy'));
```

- [ ] **Step 5: 手動驗證**

1. 開啟 app，確認顯示「已同步」、圓點是綠色
2. DevTools → Network → 勾選 Offline
3. 預期：狀態列變成「離線 · 8/5 19:35 的資料」、圓點轉灰
4. 取消 Offline
5. 預期：狀態回到「已同步」、圓點轉綠

- [ ] **Step 6: Commit**

```bash
git add iceland-trip.html
git commit -m "feat(iceland): 同步狀態改三態，離線時顯示快照時間"
```

---

## Task 4: `geoCandidates()` 候選查詢字串

**Files:**
- Modify: `iceland-trip.html`（`geocodeCity()` 之前，約 `:535`）
- Modify: `iceland-trip.html`（`_selftest` 內加斷言）

- [ ] **Step 1: 寫失敗的測試**

在 `_selftest()` 內，`// ---- haversine ----` 區塊之後插入：

```js
  // ---- geoCandidates（全部取自使用者真實資料的實測結果）----
  {
    const has=(raw,want)=>geoCandidates(raw).includes(want);
    ok('去尾端距離標記', has('Blue Lagoon 9.6km','Blue Lagoon'));
    ok('破折號取前段', has('Reykjavík Natura - Berjaya Iceland Hotels','Reykjavík Natura'));
    ok('去尾端雜訊詞', has('Fjaðrárgljúfur Masjid','Fjaðrárgljúfur'));
    ok('取最長非通用詞', has('Glacier Walk on Solheimajokull Glacier','Solheimajokull'));
    ok('原字串一定是第一個候選', geoCandidates('Seljalandsfoss')[0]==='Seljalandsfoss');
    ok('候選不重複', (()=>{const c=geoCandidates('Blue Lagoon 9.6km');return c.length===new Set(c).size;})());
    ok('空字串回空陣列', geoCandidates('').length===0);
    ok('單一地名不產生多餘候選', geoCandidates('Skógafoss').length===1);
  }
```

- [ ] **Step 2: 執行 `_selftest()`，確認失敗**

Run: DevTools console → `_selftest()`

Expected: `ReferenceError: geoCandidates is not defined`

- [ ] **Step 3: 實作 `geoCandidates`**

在 `iceland-trip.html:535`（`async function geocodeCity(name){` 那一行）之前插入：

```js
// ─── 地理編碼：候選查詢字串 ─────────────────────────
// 不是用一套正規化規則去猜，而是產生一串候選依序實查，第一個通過檢查的就採用。
// 這四條規則全部來自 2026-08-05 對使用者真實 loc 的實測，不是想像出來的。
const GEO_GENERIC=['glacier','walk','tour','restaurant','cafe','hotel','apartment','apartments',
  'wholesale','masjid','museum','centre','center','on','the','of','and','iceland','norway'];
function geoCandidates(raw){
  const s=String(raw||'').trim();
  if(!s)return [];
  const out=[s];
  const push=v=>{v=String(v||'').trim();if(v&&v.length>1&&!out.includes(v))out.push(v);};

  // 1) 去掉尾端的距離標記：「Blue Lagoon 9.6km」
  push(s.replace(/[\s,]+\d+(\.\d+)?\s*(km|公里|m|公尺)\s*$/i,''));

  // 2) 破折號／連字號取前段：「Reykjavík Natura - Berjaya Iceland Hotels」
  const dash=s.split(/\s+[-–—]\s+/)[0];
  if(dash!==s)push(dash);

  // 3) 去掉通用詞後的剩餘：「Fjaðrárgljúfur Masjid」→「Fjaðrárgljúfur」
  const toks=s.replace(/[,()]/g,' ').split(/\s+/).filter(Boolean);
  const kept=toks.filter(t=>!GEO_GENERIC.includes(t.toLowerCase().replace(/[^\p{L}]/gu,'')));
  if(kept.length&&kept.length<toks.length)push(kept.join(' '));

  // 4) 最長的非通用詞：「Glacier Walk on Solheimajokull Glacier」→「Solheimajokull」
  if(kept.length>1){
    const longest=kept.slice().sort((a,b)=>b.length-a.length)[0];
    push(longest);
  }
  return out;
}
```

- [ ] **Step 4: 執行 `_selftest()`，確認全部通過**

Run: DevTools console → `_selftest()`

Expected: 新增的 8 條 `geoCandidates` 斷言全部 ✅，總計 `通過 15 / 失敗 0`

- [ ] **Step 5: Commit**

```bash
git add iceland-trip.html
git commit -m "feat(iceland): 加入地理編碼候選字串產生器"
```

---

## Task 5: `sanityCheck()` 合理性檢查

**Files:**
- Modify: `iceland-trip.html`（`geoCandidates` 之後）
- Modify: `iceland-trip.html`（`_selftest` 內加斷言）

- [ ] **Step 1: 寫失敗的測試**

在 `_selftest()` 內，`// ---- geoCandidates ----` 區塊之後插入：

```js
  // ---- sanityCheck ----
  {
    // 南岸東段那天的既有座標（Pakkhús 與 Fjallsárlón）
    const refs=[{lat:64.2502,lng:-15.2040},{lat:64.0142,lng:-16.3722}];
    const IS={lat:64.25,lng:-15.21,cc:'is'};
    const NEAR={lat:64.10,lng:-16.00,cc:'is'};
    const FAR={lat:64.0945,lng:-21.8925,cc:'is'};   // Photon 誤配的 Garðabær，距離約 300km
    const NO ={lat:60.3943,lng:5.3259,cc:'no'};     // 挪威 Bergen
    const DE ={lat:52.52,lng:13.40,cc:'de'};

    ok('同區座標通過', sanityCheck(IS,refs,'nominatim')===true);
    ok('鄰近座標通過', sanityCheck(NEAR,refs,'nominatim')===true);
    ok('300km 外的座標被擋', sanityCheck(FAR,refs,'nominatim')===false);
    ok('非 is/no 國家被擋', sanityCheck(DE,refs,'nominatim')===false);
    ok('挪威座標本身國家合格', sanityCheck(NO,[],'nominatim')===true);
    ok('Nominatim 無參照時可採用', sanityCheck(IS,[],'nominatim')===true);
    ok('Photon 無參照時一律拒絕', sanityCheck(IS,[],'photon')===false);
    ok('Photon 有參照且合理則通過', sanityCheck(IS,refs,'photon')===true);
    ok('Photon 有參照但不合理被擋', sanityCheck(FAR,refs,'photon')===false);
  }
```

- [ ] **Step 2: 執行 `_selftest()`，確認失敗**

Run: DevTools console → `_selftest()`

Expected: `ReferenceError: sanityCheck is not defined`

- [ ] **Step 3: 實作 `sanityCheck`**

在 `iceland-trip.html` 的 `geoCandidates()` 函式之後插入：

```js
// 距離門檻。冰島一天的行程通常在此範圍內，超過代表查到的是別的地方。
const GEO_MAX_KM=200;
// 合理性檢查。地理編碼服務查不到時不會誠實回報，而會給出看似正常實則錯誤的結果：
//  - Photon 查某公寓會回名稱完全不同的另一家，或回相隔 300km 的同名地物
//  - Nominatim 限定 countrycodes=is 查「Bergen」會回冰島東部某條街的建築（差 1400km）
// 所以任何來源的結果都要獨立驗證，不能因為「有回結果」就採信。
//
// refs 是當天其他已知座標（[{lat,lng}]），src 是 'nominatim' | 'photon'。
function sanityCheck(hit,refs,src){
  if(!hit||typeof hit.lat!=='number'||typeof hit.lng!=='number')return false;
  // 第一道：國家
  if(hit.cc&&!['is','no'].includes(String(hit.cc).toLowerCase()))return false;
  // 第二道：與當天其他座標的距離
  const pts=(refs||[]).filter(r=>r&&typeof r.lat==='number'&&typeof r.lng==='number');
  if(!pts.length){
    // 無參照可比對時，兩種來源的信任度不同：
    // Nominatim 有 countrycodes 限定範圍，錯誤模式已知且有限，可採用；
    // Photon 是不可靠來源，沒有第二個座標交叉驗證就不該採信，否則一旦採信了錯誤座標，
    // 它會成為後續檢查的基準，反而把正確的座標擋掉。
    return src!=='photon';
  }
  const cLat=pts.reduce((s,p)=>s+p.lat,0)/pts.length;
  const cLng=pts.reduce((s,p)=>s+p.lng,0)/pts.length;
  return haversine(hit.lat,hit.lng,cLat,cLng)<=GEO_MAX_KM;
}
```

- [ ] **Step 4: 執行 `_selftest()`，確認全部通過**

Run: DevTools console → `_selftest()`

Expected: 新增的 9 條斷言全部 ✅，總計 `通過 24 / 失敗 0`

- [ ] **Step 5: Commit**

```bash
git add iceland-trip.html
git commit -m "feat(iceland): 加入地理編碼合理性檢查，擋掉服務編造的座標"
```

---

## Task 6: `geoResolve()` 與節流佇列

**Files:**
- Modify: `iceland-trip.html`（`sanityCheck` 之後）

本任務涉及網路，不走 TDD，改以真實地點手動驗證。

- [ ] **Step 1: 實作查詢與佇列**

在 `iceland-trip.html` 的 `sanityCheck()` 函式之後插入：

```js
// ─── 地理編碼：查詢與節流佇列 ───────────────────────
// 注意：fetch 不能設 User-Agent（規範禁止，設了會被忽略還會噴 console 警告）。
// Nominatim 政策要求以 User-Agent 或 Referer 識別，瀏覽器會自動送 Referer，這是可接受的識別方式。
const GEO_CC='is,no';
async function geoNominatim(q){
  // addressdetails=1 不可省：不帶這個參數，回應裡根本沒有 address 物件，
  // country_code 永遠取不到，國家檢查會退回預設值而形同虛設（已實測確認）。
  const u=`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=1&addressdetails=1&countrycodes=${GEO_CC}`;
  const r=await fetch(u);
  if(!r.ok)throw new Error('nominatim '+r.status);
  const d=await r.json();
  if(!d.length)return null;
  const cc=d[0].address?.country_code;
  if(!cc)return null;   // 拿不到國家就不採信，寧可留白也不猜
  return {lat:parseFloat(d[0].lat),lng:parseFloat(d[0].lon),cc,label:d[0].display_name};
}
async function geoPhoton(q){
  const r=await fetch(`https://photon.komoot.io/api?q=${encodeURIComponent(q)}&limit=1`);
  if(!r.ok)throw new Error('photon '+r.status);
  const d=await r.json();
  const f=d.features?.[0];
  if(!f)return null;
  const cc=(f.properties?.countrycode||'').toLowerCase();
  // Photon 是不可靠來源，沒有國家資訊就無法過第一道檢查，直接視為查無。
  // sanityCheck 的國家檢查對空 cc 是靜默放行的，所以要在這裡先擋掉。
  if(!cc)return null;
  const c=f.geometry.coordinates;
  return {lat:c[1],lng:c[0],cc,label:f.properties?.name||q};
}

// 1.1 秒節流的序列佇列。Nominatim 政策要求每秒至多 1 次請求，這條不能省。
const geoQueue={q:[],running:false};
function geoEnqueue(fn){
  return new Promise((res,rej)=>{
    geoQueue.q.push({fn,res,rej});
    if(!geoQueue.running)geoRun();
  });
}
async function geoRun(){
  geoQueue.running=true;
  while(geoQueue.q.length){
    const {fn,res,rej}=geoQueue.q.shift();
    try{res(await fn());}catch(e){rej(e);}
    await new Promise(r=>setTimeout(r,1100));
  }
  geoQueue.running=false;
}

// 解析單一地點。回傳 {lat,lng,src,q} 或 {fail:reason}
async function geoResolve(raw,refs){
  const cands=geoCandidates(raw);
  if(!cands.length)return {fail:'no-match'};
  let sawNetwork=false,sawReject=false;
  for(const c of cands){
    let hit=null;
    try{hit=await geoNominatim(c);}
    catch(e){sawNetwork=true;continue;}
    if(!hit)continue;
    if(sanityCheck(hit,refs,'nominatim'))return {lat:hit.lat,lng:hit.lng,src:'nominatim',q:c};
    sawReject=true;
  }
  // Nominatim 全數失敗才試 Photon，且套用同一套檢查（它最會編答案）
  for(const c of cands){
    let hit=null;
    try{hit=await geoPhoton(c);}
    catch(e){sawNetwork=true;continue;}
    if(!hit)continue;
    if(sanityCheck(hit,refs,'photon'))return {lat:hit.lat,lng:hit.lng,src:'photon',q:c};
    sawReject=true;
  }
  if(sawReject)return {fail:'sanity-reject'};
  if(sawNetwork)return {fail:'network'};
  return {fail:'no-match'};
}
```

- [ ] **Step 2: 手動驗證真實案例**

在 DevTools console 逐一執行（每次等待回應）：

```js
await geoResolve('Seljalandsfoss',[])
// 預期：{lat:63.6154…, lng:-19.9881…, src:'nominatim', q:'Seljalandsfoss'}

await geoResolve('Blue Lagoon 9.6km',[])
// 預期：{lat:63.879…, lng:-22.444…, src:'nominatim', q:'Blue Lagoon'}
// 重點是 q 已經是清理後的字串

await geoResolve('Glacier Walk on Solheimajokull Glacier',[])
// 預期：{lat:63.566…, lng:-19.295…, src:'nominatim', q:'Solheimajokull'}

await geoResolve('Nonexistent Guesthouse Hvalfjordur',[])
// 預期：{fail:'sanity-reject'} 或 {fail:'no-match'}
// Photon 對查不到的住宿會硬回一個名稱不符的結果，但此處無參照座標，依規則拒絕 Photon
```

- [ ] **Step 3: 驗證錯誤座標確實被擋**

這一步驗證距離檢查有沒有真的生效，是整條管線最重要的一道防線。

```js
// 以冰島南岸東段的兩個座標當參照，查一個挪威城市。
// 在 countrycodes=is,no 之下 Nominatim 會正確回傳挪威 Bergen（60.39, 5.33），
// 國家檢查會放行（no 是合法國家），必須靠距離檢查擋下——它距離參照中心約 1500km。
await geoResolve('Bergen',[{lat:64.2502,lng:-15.2040},{lat:64.0142,lng:-16.3722}])
// 預期：{fail:'sanity-reject'}
```

若此步驟回傳了座標而非 `sanity-reject`，代表距離檢查沒生效，**停止並回報**。這個案例通過，等於同時證明了兩種已知的錯誤模式都被擋住：跨國誤配，以及同國境內數百公里的誤配。

- [ ] **Step 4: Commit**

```bash
git add iceland-trip.html
git commit -m "feat(iceland): 加入地理編碼查詢與 1.1 秒節流佇列"
```

---

## Task 7: `ensureActGeo()` 掃描與寫回 Firebase

**Files:**
- Modify: `iceland-trip.html`（`geoResolve` 之後）
- Modify: `iceland-trip.html`（`_fbListen` 內呼叫）

- [ ] **Step 1: 實作掃描與寫回**

在 `iceland-trip.html` 的 `geoResolve()` 函式之後插入：

```js
// 取出某天所有已知座標，供 sanityCheck 當參照
function dayKnownPoints(day){
  return Object.values(day?.acts||{})
    .filter(a=>a.geo&&typeof a.geo.lat==='number')
    .map(a=>({lat:a.geo.lat,lng:a.geo.lng}));
}
let _geoScanning=false;
// 掃出「有 loc、無 geo、且不是已知查不到」的活動排進佇列。
// reason:'network' 的失敗視為可重試（服務當下不通，下次開 app 再試）；
// 'no-match' 與 'sanity-reject' 不自動重試，避免無限打 API——要重查得改 loc 或按「立即更新」。
async function ensureActGeo(sched,force=false){
  if(_geoScanning)return;
  _geoScanning=true;
  try{
    for(const [did,day] of Object.entries(sched||{})){
      const refs=dayKnownPoints(day);
      const resolved=Object.entries(day.acts||{}).filter(([aid,a])=>a.geo)
        .map(([aid,a])=>({aid,lat:a.geo.lat,lng:a.geo.lng,loc:a.loc}));
      for(const [aid,act] of Object.entries(day.acts||{})){
        if(!act.loc||act.geo)continue;
        if(!force&&act.geoFail&&act.geoFail.reason!=='network')continue;
        const res=await geoEnqueue(()=>geoResolve(act.loc,refs));
        const base='/schedule/'+did+'/acts/'+aid;
        if(res.fail){
          await DB.ref(base+'/geoFail').set({at:new Date().toISOString(),tried:geoCandidates(act.loc),reason:res.fail});
        }else{
          await DB.ref(base+'/geo').set({lat:res.lat,lng:res.lng,q:res.q,src:res.src,at:new Date().toISOString()});
          await DB.ref(base+'/geoFail').remove();
          refs.push({lat:res.lat,lng:res.lng});
          resolved.push({aid,lat:res.lat,lng:res.lng,loc:act.loc});
        }
      }
      await pruneDayOutliers(did,resolved);
    }
  }finally{_geoScanning=false;}
}

// 當天全部解析完後，用中位中心複查一次。這是為了消除順序依賴：
// 當天第一筆解析時 refs 必定是空的，sanityCheck 的距離檢查對它形同略過，
// 若它誤配，就成為當天所有後續判斷的錨點，反而把正確的座標一一擋掉。
// 用中位數而非平均，離群點才不會把中心拉向自己。
// 少於 3 筆無法判斷誰是離群（2 筆相距很遠時，沒有依據說哪一筆才是錯的），跳過。
async function pruneDayOutliers(did,resolved){
  if(resolved.length<3)return;
  const med=a=>{const s=a.slice().sort((x,y)=>x-y),m=s.length>>1;return s.length%2?s[m]:(s[m-1]+s[m])/2;};
  const cLat=med(resolved.map(r=>r.lat)),cLng=med(resolved.map(r=>r.lng));
  for(const r of resolved){
    if(haversine(r.lat,r.lng,cLat,cLng)<=GEO_MAX_KM)continue;
    await DB.ref('/schedule/'+did+'/acts/'+r.aid+'/geo').remove();
    await DB.ref('/schedule/'+did+'/acts/'+r.aid+'/geoFail')
      .set({at:new Date().toISOString(),tried:geoCandidates(r.loc||''),reason:'sanity-reject'});
  }
}
```

- [ ] **Step 2: 在 listener 內觸發**

在 `iceland-trip.html` 的 `_fbListen()` 內找到這一行（Task 2 Step 2 已改過的那段附近，約 `:815`）：

```js
    if(CFG.lat!=null)syncWeather(sched);
```

在它之後插入：

```js
    if(navigator.onLine)ensureActGeo(sched);
```

- [ ] **Step 3: 手動驗證**

1. 重新整理 app，開著 DevTools → Network
2. 預期：每隔約 1.1 秒出現一次 `nominatim.openstreetmap.org` 請求
3. 等待跑完（12 筆約 20-40 秒，含 Photon 重試）
4. 在 console 執行：

```js
Object.entries(lastSched).flatMap(([did,d])=>Object.values(d.acts||{}).map(a=>[did,a.name,a.loc,a.geo?`${a.geo.lat.toFixed(3)},${a.geo.lng.toFixed(3)}`:('❌ '+(a.geoFail?.reason||''))]))
```

預期：9 筆有座標、3 筆為 `❌`（兩筆公寓型住宿、一筆連鎖賣場），失敗原因為 `no-match` 或 `sanity-reject`

5. 再次重新整理，確認 **不會**重新查詢已成功或已標記失敗的項目（Network 面板應無 nominatim 請求）

- [ ] **Step 4: Commit**

```bash
git add iceland-trip.html
git commit -m "feat(iceland): 自動解析活動座標並快取回 Firebase"
```

---

## Task 8: 設定頁離線資料狀態面板

**Files:**
- Modify: `iceland-trip.html:341` 附近（設定頁 HTML，「Firebase」區塊之前）
- Modify: `iceland-trip.html`（`ensureActGeo` 之後加入渲染函式）
- Modify: `iceland-trip.html`（`_fbListen` 內呼叫渲染）

- [ ] **Step 1: 加入面板 HTML**

在 `iceland-trip.html` 找到設定頁的這一段（約 `:341`）：

```html
        <div class="slbl" style="margin-top:8px">Firebase</div>
```

在它之前插入：

```html
        <div class="slbl" style="margin-top:8px">離線資料</div>
        <div class="card">
          <div id="offlineStat" style="font-size:17px;line-height:1.9"></div>
          <button class="btn btn-b btn-w" style="margin-top:12px" onclick="refreshOfflineData()">立即更新</button>
        </div>
```

- [ ] **Step 2: 實作面板渲染與更新按鈕**

在 `iceland-trip.html` 的 `ensureActGeo()` 函式之後插入：

```js
// ─── 設定頁：離線資料狀態 ───────────────────────────
function renderOfflineStat(){
  const el=document.getElementById('offlineStat');
  if(!el)return;
  const days=Object.entries(lastSched||{});
  let total=0,done=0;
  const failed=[],rejected=[];
  days.forEach(([did,day])=>{
    Object.values(day.acts||{}).forEach(a=>{
      if(!a.loc)return;
      total++;
      if(a.geo)done++;
      else if(a.geoFail?.reason==='sanity-reject')rejected.push(a.loc);
      else if(a.geoFail)failed.push(a.loc);
    });
  });
  const safeReady=days.filter(([did])=>lastSafety&&lastSafety[did]).length;
  const snap=snapLoad();
  const rows=[
    `地點定位　<b>${done} / ${total}</b> 已完成`,
    `安全資訊　<b>${safeReady} / ${days.length}</b> 天已就緒`,
  ];
  if(failed.length)rows.push(`<span style="color:var(--muted)">查不到座標：${failed.map(esc).join('、')}</span>`);
  if(rejected.length)rows.push(`<span style="color:var(--orange)">位置可疑已略過：${rejected.map(esc).join('、')}</span>`);
  if(snap)rows.push(`<span style="color:var(--muted);font-size:15px">快照更新於 ${new Date(snap.at).toLocaleString('zh-TW')}</span>`);
  el.innerHTML=rows.join('<br>');
}
async function refreshOfflineData(){
  if(!navigator.onLine){toast('⚠️ 目前離線，請連上網路再更新');return;}
  toast('🔄 更新中…');
  await ensureActGeo(lastSched,true);
  await ensureSafety(lastSched,true);
  renderOfflineStat();
  toast('✅ 離線資料已更新');
}
```

`refreshOfflineData` 呼叫的 `ensureSafety` 在 Task 11 才實作。本任務完成後點擊「立即更新」會在 console 出現 `ensureSafety is not defined`，這是預期的，Task 11 完成後即消失。若要在此階段避免報錯，可先在 `ensureActGeo` 之後插入暫時的空實作 `async function ensureSafety(){}`，並在 Task 11 用完整版本取代。

- [ ] **Step 3: 在 listener 與 goTab 內觸發渲染**

在 `iceland-trip.html` 的 `_fbListen()` 內找到（Task 7 Step 2 加入的那一行）：

```js
    if(navigator.onLine)ensureActGeo(sched);
```

在它之後插入：

```js
    renderOfflineStat();
```

- [ ] **Step 4: 手動驗證**

1. 重新整理 app → 切到「設定」分頁
2. 預期看到：

```
離線資料
  地點定位　9 / 12 已完成
  安全資訊　0 / 20 天已就緒
  查不到座標：⟨兩到三個地點名稱⟩
  快照更新於 2026/8/5 下午7:35:00
```

（安全資訊此時為 0，Task 11 完成後才會有數字）

- [ ] **Step 5: Commit**

```bash
git add iceland-trip.html
git commit -m "feat(iceland): 設定頁加入離線資料狀態面板"
```

---

## Task 9: Day 導覽列

**Files:**
- Modify: `iceland-trip.html`（CSS，`:194` 附近）
- Modify: `iceland-trip.html:283`（`#schedBox` 之前加入容器）
- Modify: `iceland-trip.html`（`renderSched` 之後加入 `renderDayStrip`）

- [ ] **Step 1: 加入 CSS**

在 `iceland-trip.html:194` 找到這一行：

```css
.day-meta{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-top:4px;}
```

在它之前插入：

```css
.day-strip{position:sticky;top:0;z-index:50;background:var(--bg);display:flex;gap:8px;overflow-x:auto;padding:10px 16px;margin:0 -16px 10px;scrollbar-width:none;}
.day-strip::-webkit-scrollbar{display:none;}
.ds-chip{flex:0 0 auto;background:var(--card);border:1.5px solid var(--border);border-radius:12px;padding:8px 14px;text-align:center;cursor:pointer;min-width:74px;transition:all .12s;}
.ds-chip.on{background:var(--blue);border-color:var(--blue);}
.ds-chip .ds-n{display:block;font-size:15px;color:var(--muted);font-weight:600;}
.ds-chip .ds-d{display:block;font-size:18px;font-weight:800;color:var(--text);margin-top:1px;}
.ds-chip.on .ds-n,.ds-chip.on .ds-d{color:#fff;}
```

- [ ] **Step 2: 加入容器**

在 `iceland-trip.html:283` 找到：

```html
      <div class="bx" id="schedBox">
```

改成：

```html
      <div class="bx">
        <div class="day-strip" id="dayStrip"></div>
        <div id="overviewBox"></div>
      </div>
      <div class="bx" id="schedBox">
```

- [ ] **Step 3: 實作 `renderDayStrip` 與捲動定位**

在 `iceland-trip.html` 的 `function toggleDay(did){...}`（約 `:1179`）之前插入：

```js
// ─── Day 導覽列 ─────────────────────────────────────
function renderDayStrip(sched){
  const el=document.getElementById('dayStrip');
  if(!el)return;
  const days=Object.entries(sched||{}).sort((a,b)=>(parseInt(a[0].replace(/\D/g,''))||0)-(parseInt(b[0].replace(/\D/g,''))||0));
  const md=d=>{if(!d)return'';const[y,m,dd]=d.split('-');return `${parseInt(m)}/${parseInt(dd)}`;};
  const wd=d=>{if(!d)return'';return new Date(d+'T12:00:00').toLocaleDateString('zh-TW',{weekday:'short'});};
  el.innerHTML=
    `<div class="ds-chip" id="ds-overview" onclick="jumpOverview()"><span class="ds-n">總覽</span><span class="ds-d">${days.length}天</span></div>`+
    days.map(([did,day])=>
      `<div class="ds-chip" id="ds-${did}" onclick="jumpDay('${did}')"><span class="ds-n">D${did.replace(/\D/g,'')} ${wd(day.date)}</span><span class="ds-d">${md(day.date)}</span></div>`
    ).join('');
  initDaySpy();
}
function jumpOverview(){
  window.scrollTo({top:0,behavior:'smooth'});
  setDayChip('overview');
}
function jumpDay(did){
  const card=document.getElementById('dc-'+did);
  if(!card)return;
  card.classList.add('open');
  mountDayMap(did);
  const strip=document.getElementById('dayStrip');
  const offset=(strip?strip.getBoundingClientRect().height:0)+8;
  const y=card.getBoundingClientRect().top+window.scrollY-offset;
  window.scrollTo({top:y,behavior:'smooth'});
  setDayChip(did);
}
function setDayChip(key){
  document.querySelectorAll('.ds-chip').forEach(c=>c.classList.remove('on'));
  const chip=document.getElementById('ds-'+key);
  if(!chip)return;
  chip.classList.add('on');
  chip.scrollIntoView({behavior:'smooth',block:'nearest',inline:'center'});
}
let _daySpy=null;
// 捲到哪天就 highlight 哪個 chip。rootMargin 上緣留出 sticky 導覽列的高度，
// 讓「目前這天」的判定跟視覺上看到的一致。
function initDaySpy(){
  if(_daySpy)_daySpy.disconnect();
  _daySpy=new IntersectionObserver(entries=>{
    const vis=entries.filter(e=>e.isIntersecting)
      .sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top)[0];
    if(vis)setDayChip(vis.target.id.replace('dc-',''));
  },{rootMargin:'-80px 0px -70% 0px',threshold:0});
  document.querySelectorAll('.day-card').forEach(c=>_daySpy.observe(c));
}
```

- [ ] **Step 4: 在 `renderSched` 結尾呼叫**

在 `iceland-trip.html` 找到 `renderSched()` 的結尾（約 `:1176`）：

```js
  openDays.forEach(did=>{const el=document.getElementById('dc-'+did);if(el)el.classList.add('open');});
}
```

改成：

```js
  openDays.forEach(did=>{const el=document.getElementById('dc-'+did);if(el)el.classList.add('open');});
  renderDayStrip(sched);
  renderOverview(sched);
}
```

`renderOverview` 在 Task 10 實作。本任務完成後 console 會出現 `renderOverview is not defined` 且行程頁會停在載入中，**Task 9 與 Task 10 必須連續完成才能驗證**。若要分開驗證，先在 `renderDayStrip` 之後插入暫時的空實作 `function renderOverview(){}`，Task 10 再取代。

`mountDayMap` 在 Task 12 實作，同樣先補空實作 `function mountDayMap(){}`。

- [ ] **Step 5: Commit**

```bash
git add iceland-trip.html
git commit -m "feat(iceland): 加入 Day 導覽列與捲動定位"
```

---

## Task 10: 總覽區塊（住宿總整理）

**Files:**
- Modify: `iceland-trip.html`（CSS）
- Modify: `iceland-trip.html`（`renderDayStrip` 之後）

- [ ] **Step 1: 加入 CSS**

在 Task 9 Step 1 插入的 `.ds-chip.on .ds-n,...` 那一行之後插入：

```css
.ov-card{background:var(--card);border-radius:12px;padding:14px 16px;margin-bottom:10px;box-shadow:0 1px 4px rgba(0,0,0,.06);}
.ov-h{font-size:19px;font-weight:800;margin-bottom:10px;display:flex;align-items:center;gap:7px;}
.ov-row{display:flex;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);align-items:flex-start;}
.ov-row:last-child{border-bottom:none;}
.ov-date{flex:0 0 auto;font-size:17px;font-weight:800;color:var(--blue2);min-width:52px;}
.ov-name{font-size:18px;font-weight:700;line-height:1.4;}
.ov-loc{font-size:16px;color:var(--muted);margin-top:2px;white-space:pre-wrap;word-break:break-word;}
.ov-nav{flex:0 0 auto;background:#E8EFF3;color:var(--blue2);border:none;border-radius:9px;padding:7px 11px;font-size:15px;font-weight:700;cursor:pointer;text-decoration:none;}
```

- [ ] **Step 2: 實作 `renderOverview`**

在 `iceland-trip.html` 的 `renderDayStrip()` 函式之前插入：

```js
// ─── 總覽：住宿總整理 ───────────────────────────────
function navUrl(lat,lng,label){
  if(typeof lat==='number'&&typeof lng==='number')
    return `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(label||'')}`;
}
function renderOverview(sched){
  const el=document.getElementById('overviewBox');
  if(!el)return;
  const days=Object.entries(sched||{}).sort((a,b)=>(parseInt(a[0].replace(/\D/g,''))||0)-(parseInt(b[0].replace(/\D/g,''))||0));
  const rows=[];
  days.forEach(([did,day])=>{
    Object.values(day.acts||{}).filter(a=>a.cat==='hotel').forEach(a=>{
      rows.push({date:day.date,name:a.name||'住宿',loc:a.loc||'',geo:a.geo});
    });
  });
  if(!rows.length){el.innerHTML='';return;}
  const md=d=>{if(!d)return'';const[y,m,dd]=d.split('-');return `${parseInt(m)}/${parseInt(dd)}`;};
  el.innerHTML=`<div class="ov-card">
    <div class="ov-h">🛏️ 住宿總整理</div>
    ${rows.map(r=>`<div class="ov-row">
      <div class="ov-date">${md(r.date)}</div>
      <div style="flex:1;min-width:0">
        <div class="ov-name">${esc(r.name)}</div>
        ${r.loc?`<div class="ov-loc">${esc(r.loc)}</div>`:''}
      </div>
      ${(r.geo||r.loc)?`<a class="ov-nav" href="${navUrl(r.geo?.lat,r.geo?.lng,r.loc||r.name)}" target="_blank">導航</a>`:''}
    </div>`).join('')}
  </div>`;
}
```

- [ ] **Step 3: 移除 Task 9 的暫時空實作**

若 Task 9 Step 4 有插入 `function renderOverview(){}`，現在刪除該行。

- [ ] **Step 4: 手動驗證**

1. 重新整理 app
2. 預期頁面最上方出現「🛏️ 住宿總整理」卡片，列出 3 筆住宿（日期 + 名稱 + 地點 + 導航按鈕）
3. 上方出現橫向捲動的 Day 導覽列，第一個是「總覽 20天」
4. 點 D3 → 頁面平滑捲到 Day 3 並展開該日卡，D3 chip 變成藍底白字
5. 手動往下捲動 → chip 的 highlight 跟著改變
6. 點「總覽」→ 捲回頂端

- [ ] **Step 5: Commit**

```bash
git add iceland-trip.html
git commit -m "feat(iceland): 總覽區塊加入住宿總整理"
```

---

## Task 11: 安全資訊資料層

**Files:**
- Modify: `iceland-trip.html`（`ensureActGeo` 之後）

- [ ] **Step 1: 實作定位基準（純函式，先寫測試）**

在 `_selftest()` 內，`// ---- sanityCheck ----` 區塊之後插入：

```js
  // ---- dayBaseLatLng ----
  {
    const hotelDay={acts:{a:{cat:'hotel',geo:{lat:64.13,lng:-21.93}},b:{cat:'sight',geo:{lat:63.61,lng:-19.98}}}};
    const noHotel  ={acts:{a:{cat:'sight',geo:{lat:64.00,lng:-16.00}},b:{cat:'sight',geo:{lat:64.20,lng:-16.40}}}};
    const empty    ={acts:{}};
    const h=dayBaseLatLng(hotelDay,null);
    ok('住宿優先', h&&h.from==='hotel'&&near(h.lat,64.13,0.001));
    const c=dayBaseLatLng(noHotel,null);
    ok('無住宿退回當日中心', c&&c.from==='center'&&near(c.lat,64.10,0.001)&&near(c.lng,-16.20,0.001));
    const p=dayBaseLatLng(empty,{lat:64.25,lng:-15.20});
    ok('無座標退回前一日住宿', p&&p.from==='prevHotel'&&near(p.lat,64.25,0.001));
    ok('全無則回 null', dayBaseLatLng(empty,null)===null);
  }
```

- [ ] **Step 2: 執行 `_selftest()`，確認失敗**

Run: DevTools console → `_selftest()`

Expected: `ReferenceError: dayBaseLatLng is not defined`

- [ ] **Step 3: 實作安全資訊資料層**

在 `iceland-trip.html` 的 `ensureActGeo()` 函式之後插入：

```js
// ─── 安全資訊：定位基準與查詢 ───────────────────────
// 依序：當日住宿 → 當日所有座標的中心 → 前一日住宿。三者皆無則該日不顯示安全資訊。
function dayBaseLatLng(day,prevHotel){
  const acts=Object.values(day?.acts||{});
  const hotel=acts.find(a=>a.cat==='hotel'&&a.geo&&typeof a.geo.lat==='number');
  if(hotel)return {lat:hotel.geo.lat,lng:hotel.geo.lng,from:'hotel',label:hotel.name||hotel.loc||'住宿'};
  const pts=acts.filter(a=>a.geo&&typeof a.geo.lat==='number').map(a=>a.geo);
  if(pts.length){
    return {lat:pts.reduce((s,p)=>s+p.lat,0)/pts.length,
            lng:pts.reduce((s,p)=>s+p.lng,0)/pts.length,
            from:'center',label:'當日行程'};
  }
  if(prevHotel)return {lat:prevHotel.lat,lng:prevHotel.lng,from:'prevHotel',label:prevHotel.label||'前一日住宿'};
  return null;
}

const OVERPASS_URL='https://overpass-api.de/api/interpreter';
const OSRM_URL='https://router.project-osrm.org/route/v1/driving/';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

// 冰島鄉下資料很稀疏（實測某東南部城鎮半徑 50km 內只有 2 筆），所以半徑要漸進放大。
// clinic 不能省：鄉下常常只有 heilsugæsla 診所而沒有 hospital。
async function overpassAround(lat,lng,radius){
  const q=`[out:json][timeout:25];(
node[amenity=police](around:${radius},${lat},${lng});
node[amenity=hospital](around:${radius},${lat},${lng});
node[amenity=clinic](around:${radius},${lat},${lng});
way[amenity=police](around:${radius},${lat},${lng});
way[amenity=hospital](around:${radius},${lat},${lng});
);out center tags;`;
  const r=await fetch(OVERPASS_URL,{method:'POST',body:q});
  if(!r.ok)throw new Error('overpass '+r.status);
  const d=await r.json();
  return (d.elements||[]).map(e=>{
    const lat2=e.lat??e.center?.lat, lng2=e.lon??e.center?.lon;
    if(lat2==null)return null;
    const t=e.tags||{};
    return {amenity:t.amenity,name:t.name||'',emergency:t.emergency||'',
            lat:lat2,lng:lng2,km:haversine(lat,lng,lat2,lng2)};
  }).filter(Boolean);
}
// 車程。直線距離在冰島會嚴重低估（實測 1.15-1.24x），而且「62 公里」不會讓人知道那是一小時的路。
async function osrmDrive(fromLat,fromLng,toLat,toLng){
  try{
    const r=await fetch(`${OSRM_URL}${fromLng},${fromLat};${toLng},${toLat}?overview=false`);
    if(!r.ok)return null;
    const d=await r.json();
    if(d.code!=='Ok'||!d.routes?.length)return null;
    return {km:+(d.routes[0].distance/1000).toFixed(1),min:Math.round(d.routes[0].duration/60)};
  }catch(e){return null;}
}
async function fetchSafety(base){
  let els=[];
  for(const radius of [10000,30000,100000]){
    try{els=await overpassAround(base.lat,base.lng,radius);}
    catch(e){await sleep(2000);try{els=await overpassAround(base.lat,base.lng,radius);}catch(e2){throw e2;}}
    if(els.length)break;
    await sleep(2000);
  }
  const pick=pred=>els.filter(pred).sort((a,b)=>a.km-b.km).slice(0,3);
  const police=pick(e=>e.amenity==='police');
  const hosp  =pick(e=>e.amenity==='hospital'||e.amenity==='clinic');
  for(const e of [...police,...hosp]){
    e.km=+e.km.toFixed(1);
    const d=await osrmDrive(base.lat,base.lng,e.lat,e.lng);
    if(d)e.drive=d;
    await sleep(1000);
  }
  return {base,police,hospital:hosp,at:new Date().toISOString()};
}

let _safetyScanning=false;
// base 位移超過 1km 才重抓：from:'center' 的中心點會隨每次新增/刪除活動漂移，
// 沒有門檻的話每編輯一次行程就重打一輪 Overpass + OSRM，而幾百公尺不會改變最近的警局是哪間。
const SAFETY_MOVE_KM=1;
async function ensureSafety(sched,force=false){
  if(_safetyScanning||!navigator.onLine)return;
  _safetyScanning=true;
  try{
    const days=Object.entries(sched||{}).sort((a,b)=>(parseInt(a[0].replace(/\D/g,''))||0)-(parseInt(b[0].replace(/\D/g,''))||0));
    let prevHotel=null;
    for(const [did,day] of days){
      const base=dayBaseLatLng(day,prevHotel);
      if(base&&base.from==='hotel')prevHotel={lat:base.lat,lng:base.lng,label:base.label};
      if(!base)continue;
      const old=lastSafety?.[did];
      if(!force&&old?.base&&haversine(base.lat,base.lng,old.base.lat,old.base.lng)<=SAFETY_MOVE_KM)continue;
      try{
        const res=await fetchSafety(base);
        await DB.ref('/safety/'+did).set(res);
      }catch(e){
        // 查不到就保留舊快取不覆蓋——舊資料比沒資料有用
        console.warn('safety '+did+' 失敗：',e.message);
      }
      await sleep(2000);
    }
  }finally{_safetyScanning=false;}
}
```

- [ ] **Step 4: 移除 Task 8 的暫時空實作**

若 Task 8 Step 2 有插入 `async function ensureSafety(){}`，現在刪除該行。

- [ ] **Step 5: 在 listener 內觸發**

在 `iceland-trip.html` 的 `_fbListen()` 內找到（Task 7 Step 2 加入的那一行）：

```js
    if(navigator.onLine)ensureActGeo(sched);
```

改成：

```js
    if(navigator.onLine)ensureActGeo(sched).then(()=>ensureSafety(lastSched));
```

- [ ] **Step 6: 執行 `_selftest()`，確認 `dayBaseLatLng` 的 4 條斷言通過**

Run: DevTools console → `_selftest()`

Expected: 總計 `通過 28 / 失敗 0`

- [ ] **Step 7: 手動驗證資料抓取**

1. 重新整理 app，等待座標解析完成後會接著抓安全資訊（Network 面板會出現 `overpass-api.de` 與 `router.project-osrm.org` 請求）
2. 在 console 執行：

```js
Object.entries(lastSafety).map(([did,s])=>[did,s.base.from,s.police[0]?.name||'(無名)',s.police[0]?.drive?.min+'分',s.hospital[0]?.name,s.hospital[0]?.drive?.min+'分'])
```

預期：4 筆（day1、day2、day3、day5），每筆有警局與醫院的名稱與車程分鐘數。部分 `name` 可能為空字串，這是 OSM 的已知情況。

- [ ] **Step 8: Commit**

```bash
git add iceland-trip.html
git commit -m "feat(iceland): 加入每日安全資訊資料層（Overpass + OSRM）"
```

---

## Task 12: 每日地圖

**Files:**
- Modify: `iceland-trip.html:223` 之前（Leaflet CSS 延遲載入的樣式容器）
- Modify: `iceland-trip.html`（CSS）
- Modify: `iceland-trip.html`（`renderSched` 內插入容器、新增 mount 邏輯）

- [ ] **Step 1: 加入 CSS**

在 Task 10 Step 1 插入的 `.ov-nav{...}` 那一行之後插入：

```css
.day-map{height:220px;margin:0;background:#DCE6EA;position:relative;}
.day-map-ph{padding:14px 16px;background:var(--card);}
.dm-row{display:flex;gap:10px;align-items:flex-start;padding:7px 0;border-bottom:1px solid var(--border);}
.dm-row:last-child{border-bottom:none;}
.dm-n{flex:0 0 auto;width:24px;height:24px;border-radius:50%;background:var(--blue);color:#fff;font-size:14px;font-weight:800;display:flex;align-items:center;justify-content:center;}
.dm-name{font-size:17px;font-weight:700;}
.dm-co{font-size:15px;color:var(--muted);}
.leaflet-marker-num{background:var(--blue);color:#fff;border-radius:50%;width:26px;height:26px;line-height:26px;text-align:center;font-weight:800;font-size:14px;box-shadow:0 1px 4px rgba(0,0,0,.4);}
```

- [ ] **Step 2: 實作 Leaflet 延遲載入與地圖掛載**

在 `iceland-trip.html` 的 `renderOverview()` 函式之前插入：

```js
// ─── 每日地圖 ───────────────────────────────────────
let _leafletLoading=null;
function loadLeaflet(){
  if(window.L)return Promise.resolve(true);
  if(_leafletLoading)return _leafletLoading;
  _leafletLoading=new Promise(res=>{
    const css=document.createElement('link');
    css.rel='stylesheet';css.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(css);
    const s=document.createElement('script');
    s.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    s.onload=()=>res(true);
    s.onerror=()=>res(false);   // CDN 掛掉就走降級路徑，不讓整頁卡住
    document.head.appendChild(s);
  });
  return _leafletLoading;
}
// 當天有座標的活動，依 order 排序
function dayGeoActs(day){
  return Object.entries(day?.acts||{})
    .filter(([aid,a])=>a.geo&&typeof a.geo.lat==='number')
    .sort((a,b)=>{
      const oa=a[1].order!=null?a[1].order:999999, ob=b[1].order!=null?b[1].order:999999;
      if(oa!==ob)return oa-ob;
      return (a[1].time||'').localeCompare(b[1].time||'');
    })
    .map(([aid,a])=>({aid,name:a.name||'',lat:a.geo.lat,lng:a.geo.lng}));
}
const dayMaps=new Map();      // did → L.map 實例
const dayMapEls=new Map();    // did → 地圖容器 DOM（renderSched 重畫時暫存）

// 離線或 CDN 失敗時的降級：地點清單 + 座標 + 導航連結。
function dayMapFallbackHtml(pts){
  return `<div class="day-map-ph">${pts.map((p,i)=>`<div class="dm-row">
    <div class="dm-n">${i+1}</div>
    <div style="flex:1;min-width:0">
      <div class="dm-name">${esc(p.name)}</div>
      <div class="dm-co">${p.lat.toFixed(4)}, ${p.lng.toFixed(4)}</div>
    </div>
    <a class="ov-nav" href="${navUrl(p.lat,p.lng,p.name)}" target="_blank">導航</a>
  </div>`).join('')}</div>`;
}
async function mountDayMap(did){
  const host=document.getElementById('dmap-'+did);
  if(!host||host.dataset.mounted==='1')return;
  const day=lastSched[did];
  const pts=dayGeoActs(day);
  if(!pts.length)return;
  host.dataset.mounted='1';
  if(!navigator.onLine||!(await loadLeaflet())){
    host.innerHTML=dayMapFallbackHtml(pts);
    return;
  }
  host.classList.add('day-map');
  const map=L.map(host,{zoomControl:false,attributionControl:true});
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap'}).addTo(map);
  pts.forEach((p,i)=>{
    L.marker([p.lat,p.lng],{icon:L.divIcon({className:'',html:`<div class="leaflet-marker-num">${i+1}</div>`,iconSize:[26,26],iconAnchor:[13,13]})})
      .addTo(map).bindPopup(esc(p.name));
  });
  if(pts.length>1){
    L.polyline(pts.map(p=>[p.lat,p.lng]),{color:'#0077B6',weight:2,dashArray:'6,6',opacity:.8}).addTo(map);
    map.fitBounds(pts.map(p=>[p.lat,p.lng]),{padding:[28,28]});
  }else{
    map.setView([pts[0].lat,pts[0].lng],13);
  }
  dayMaps.set(did,map);
  setTimeout(()=>map.invalidateSize(),60);
}
function unmountDayMap(did){
  const m=dayMaps.get(did);
  if(m){m.remove();dayMaps.delete(did);}
  dayMapEls.delete(did);
}
```

- [ ] **Step 3: 在日卡內插入地圖容器**

在 `iceland-trip.html` 的 `renderSched()` 內找到這一行（約 `:1146`）：

```js
      <div class="day-body">
```

改成：

```js
      <div class="day-body">
        ${dayGeoActs(day).length?`<div id="dmap-${did}"></div>`:''}
```

- [ ] **Step 4: 重畫時保住 Leaflet 實例**

`renderSched()` 每次都 `box.innerHTML=...` 整頁重畫，而 listener 監聽根路徑，記一筆帳就會觸發。地圖節點被砍掉會讓 Leaflet 實例變殭屍並閃爍。解法是重畫前把節點摘下、重畫後放回去。

在 `iceland-trip.html` 的 `renderSched()` 開頭找到（約 `:1116`）：

```js
  const openDays=new Set([...document.querySelectorAll('.day-card.open')].map(el=>el.id.replace('dc-','')));
```

在它之後插入：

```js
  // 把已掛載的地圖節點摘下暫存，重畫後再放回原位。Leaflet 實例在 detach 期間仍然有效，
  // 直接讓 innerHTML 沖掉會留下殭屍實例，而且每記一筆帳畫面就閃一次。
  dayMapEls.clear();
  dayMaps.forEach((m,did)=>{
    const el=document.getElementById('dmap-'+did);
    if(el&&el.parentNode){el.parentNode.removeChild(el);dayMapEls.set(did,el);}
  });
```

在 `renderSched()` 結尾（Task 9 Step 4 改過的那段）找到：

```js
  openDays.forEach(did=>{const el=document.getElementById('dc-'+did);if(el)el.classList.add('open');});
  renderDayStrip(sched);
  renderOverview(sched);
}
```

改成：

```js
  openDays.forEach(did=>{const el=document.getElementById('dc-'+did);if(el)el.classList.add('open');});
  // 把暫存的地圖節點放回去；已經不存在的日子（活動被刪光）就順手銷毀實例
  dayMapEls.forEach((el,did)=>{
    const ph=document.getElementById('dmap-'+did);
    if(ph&&ph.parentNode){ph.parentNode.replaceChild(el,ph);const m=dayMaps.get(did);if(m)setTimeout(()=>m.invalidateSize(),60);}
    else unmountDayMap(did);
  });
  dayMapEls.clear();
  openDays.forEach(did=>mountDayMap(did));
  renderDayStrip(sched);
  renderOverview(sched);
}
```

- [ ] **Step 5: 展開日卡時掛載地圖**

在 `iceland-trip.html` 找到（約 `:1179`）：

```js
function toggleDay(did){document.getElementById('dc-'+did).classList.toggle('open');}
```

改成：

```js
function toggleDay(did){
  const card=document.getElementById('dc-'+did);
  card.classList.toggle('open');
  if(card.classList.contains('open'))mountDayMap(did);
}
```

- [ ] **Step 6: 移除 Task 9 的暫時空實作**

若 Task 9 Step 4 有插入 `function mountDayMap(){}`，現在刪除該行。

- [ ] **Step 7: 手動驗證**

1. 重新整理 app → 展開 Day 2（有三個景點座標）
2. 預期：日卡最上方出現地圖，三個編號 marker 依序 1、2、3，虛線相連，視野自動框住三點
3. **關鍵迴歸測試**：地圖開著時，切到記帳分頁新增一筆支出 → 回行程分頁
4. 預期：地圖**沒有閃爍、沒有消失**，仍停在原本的視野
5. 展開 Day 4（無活動）→ 預期不出現地圖區塊，也不留空框
6. DevTools → Network → Offline → 重新整理 → 展開 Day 2
7. 預期：出現地點清單（編號 + 名稱 + 座標 + 導航按鈕），不是空白地圖

- [ ] **Step 8: Commit**

```bash
git add iceland-trip.html
git commit -m "feat(iceland): 每日地圖，離線降級為地點清單"
```

---

## Task 13: 安全資訊卡片

**Files:**
- Modify: `iceland-trip.html`（CSS）
- Modify: `iceland-trip.html`（`renderSched` 內插入）

- [ ] **Step 1: 加入 CSS**

在 Task 12 Step 1 插入的 `.leaflet-marker-num{...}` 之後插入：

```css
.sf-card{margin:0;padding:14px 16px;border-top:1px solid var(--border);background:#FBF7F3;}
.sf-h{font-size:17px;font-weight:800;display:flex;align-items:center;gap:6px;margin-bottom:10px;}
.sf-row{display:flex;gap:11px;align-items:flex-start;padding:9px 0;border-bottom:1px dashed var(--border);}
.sf-row:last-of-type{border-bottom:none;}
.sf-ico{flex:0 0 auto;width:34px;height:34px;border-radius:9px;background:#E8EFF3;display:flex;align-items:center;justify-content:center;font-size:17px;}
.sf-lbl{font-size:14px;color:var(--muted);font-weight:600;}
.sf-name{font-size:17px;font-weight:700;line-height:1.35;}
.sf-dist{font-size:15px;color:var(--muted);margin-top:2px;}
.sf-tag{display:inline-block;background:#D9534F;color:#fff;border-radius:6px;padding:1px 7px;font-size:13px;font-weight:700;margin-left:6px;}
.sf-note{font-size:14px;color:var(--muted);margin-top:10px;line-height:1.6;}
```

- [ ] **Step 2: 實作卡片渲染**

在 `iceland-trip.html` 的 `mountDayMap()` 函式之後插入：

```js
// ─── 安全資訊卡片 ───────────────────────────────────
function sfDist(e){
  if(e.drive)return `車程 ${e.drive.km} 公里 · 約 ${e.drive.min} 分`;
  return `直線 ${e.km} 公里`;   // OSRM 不通時的 fallback，明確標示以免誤導
}
function sfRow(icon,label,e){
  if(!e)return '';
  const name=e.name||(label.includes('警')?'警察局（未命名）':'醫療機構（未命名）');
  const tag=e.emergency==='yes'?'<span class="sf-tag">有急診</span>':'';
  return `<div class="sf-row">
    <div class="sf-ico">${icon}</div>
    <div style="flex:1;min-width:0">
      <div class="sf-lbl">${label}</div>
      <div class="sf-name">${esc(name)}${tag}</div>
      <div class="sf-dist">${sfDist(e)}</div>
    </div>
    <a class="ov-nav" href="${navUrl(e.lat,e.lng,e.name)}" target="_blank">導航</a>
  </div>`;
}
function safetyHtml(did){
  const s=lastSafety?.[did];
  if(!s||!s.base)return '';
  const p=s.police?.[0],h=s.hospital?.[0];
  if(!p&&!h)return '';
  const from=s.base.from==='hotel'?`依住宿「${esc(s.base.label)}」查詢`
            :s.base.from==='center'?'依當日行程位置查詢'
            :`依前一日住宿「${esc(s.base.label)}」查詢`;
  return `<div class="sf-card">
    <div class="sf-h">🛡️ 安全資訊（最近警局 / 急診）</div>
    ${sfRow('🚓','最近警察局',p)}
    ${sfRow('🏥','最近醫療機構',h)}
    <div class="sf-note">${from}・資料：OpenStreetMap<br>車程僅供參考，出發前請再確認路況</div>
  </div>`;
}
```

- [ ] **Step 3: 在日卡最下方插入**

在 `iceland-trip.html` 的 `renderSched()` 內找到（約 `:1172`）：

```js
        <div class="day-add" onclick="openActM('${did}')">＋ 新增活動</div>
      </div>
    </div>`;
```

改成：

```js
        <div class="day-add" onclick="openActM('${did}')">＋ 新增活動</div>
        ${safetyHtml(did)}
      </div>
    </div>`;
```

- [ ] **Step 4: 手動驗證**

1. 重新整理 app → 展開 Day 3
2. 預期日卡最下方出現「🛡️ 安全資訊（最近警局 / 急診）」卡片，含：
   - 最近警察局：名稱（可能是「警察局（未命名）」）+ 車程分鐘 + 導航按鈕
   - 最近醫療機構：名稱 + 車程 + 導航
   - 底部：「依當日行程位置查詢・資料：OpenStreetMap」與路況提醒
3. 展開 Day 5（有住宿座標）→ 底部應顯示「依住宿「⟨名稱⟩」查詢」
4. DevTools → Offline → 重新整理 → 展開 Day 3
5. 預期：安全資訊**照常顯示**（讀 localStorage 快照），車程數字仍在

- [ ] **Step 5: Commit**

```bash
git add iceland-trip.html
git commit -m "feat(iceland): 每日安全資訊卡片，離線可讀"
```

---

## Task 14: 版本號、整體迴歸驗證與同步部署資料夾

**Files:**
- Modify: `iceland-trip.html:277`（版本號）

- [ ] **Step 1: 更新版本號**

iOS PWA 的快取極頑固，改版後不更新版本號會分不清看到的是新版還是舊版。在 `iceland-trip.html:277` 找到：

```html
<span style="font-size:12px;opacity:.5">v0611</span>
```

改成：

```html
<span style="font-size:12px;opacity:.5">v0805</span>
```

- [ ] **Step 2: 執行完整自我測試**

Run: DevTools console → `_selftest()`

Expected: `通過 28 / 失敗 0`

- [ ] **Step 3: 迴歸驗證清單**

逐項確認，全部都是既有功能，不得被本次改動破壞：

1. **記帳後地圖不閃**：展開 Day 2 地圖 → 新增一筆支出 → 回行程頁 → 地圖仍在原視野，無閃爍
2. **跨日拖曳仍正常**：長按 Day 2 某活動的拖曳把手 ⠿ → 拖到 Day 3 → 放開 → 活動移到 Day 3，且其座標跟著搬過去（展開 Day 3 地圖應出現該點）
3. **iOS 拖曳四項修法未被破壞**：在 iPhone 上實測拖曳排序（`touch-action:none`、不等 Firebase 回應即啟動、就近判定、`touchcancel` 處理）
4. **日期補正不互踢**：兩台裝置同時開著 app，靜置 30 秒，確認行程日期沒有來回變動
5. **離線完整流程**：DevTools Offline → 重新整理 → 行程、住宿總整理、安全資訊、記帳全部可見；地圖降級為地點清單
6. **記事本換行仍正常**：記事本內容的多行文字仍保留換行（`white-space:pre-wrap`）

- [ ] **Step 4: Commit**

```bash
git add iceland-trip.html
git commit -m "chore(iceland): 版本號更新為 v0805"
```

- [ ] **Step 5: 詢問使用者是否要同步到部署資料夾**

本專案的 Netlify **不是** git-connected 自動部署，`git push` 不會反映到線上。冰島版有自己的一份 Netlify 部署，且使用者偏好自己執行最後的部署動作。

向使用者確認：是否要將 `iceland-trip.html` 複製到部署資料夾（若存在），或由使用者自行手動拖拉部署。**不要自行執行 `netlify deploy`。**

同時提醒使用者：先前累積的 `290460e`、`dff66ef` 兩個 commit 是否已部署尚未確認，若尚未部署，這次一併上線時要確保是 `dff66ef` 之後的版本（單獨部署 `290460e` 會讓手動記帳的日期永久對不回去）。

---

## 完成標準

- [ ] `_selftest()` 通過 28 / 失敗 0
- [ ] 設定頁狀態面板顯示「地點定位 9 / 12」與「安全資訊 4 / 20 天」
- [ ] Day 導覽列可捲動定位，scrollspy 正常
- [ ] 總覽住宿總整理列出 3 筆住宿
- [ ] Day 1/2/3 展開後有地圖，Day 4 無地圖也無空框
- [ ] Day 1/2/3/5 有安全資訊卡片，含車程分鐘數
- [ ] 離線重新整理後，上述內容除地圖底圖外全部可見
- [ ] 迴歸清單 6 項全數通過
