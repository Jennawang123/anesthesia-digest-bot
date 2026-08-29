# 住宿自動出發／入住卡片 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 iceland-trip.html／couple-trip-template.html／us-trip.html 三支旅遊 app 的行程列表，在跨夜住宿的日子自動插入「從住宿出發」（早上）與「今晚住宿」（晚上）兩張唯讀卡片，並用既有的 OSRM／直線距離機制算出對應車程。

**Architecture:** 新增一個純函式 `morningHotel(sched,did)`，與既有 `coveringHotel(sched,did)` 互補（語意差一個 `<=`：退房日早上也算，入住日當天不算）。`dayGeoActs()` 比照既有「補今晚落腳處」的做法，在陣列最前面也補上「今早出發點」。`renderSched()` 把當天要顯示的項目改成 `[出發卡?, ...真實活動, 入住卡?]` 這樣一個統一陣列來畫，相鄰項目一律用既有 `legHtml()` 算距離——不管兩端是卡片還是活動都同一套邏輯，OSRM 快取、直線 fallback、约略標示全部照舊生效。純渲染層改動，不寫回 Firebase，`coveringHotel()`／安全資訊／地圖定位基準完全不動。

**Tech Stack:** 純前端 HTML/JS（無框架、無建置流程），Firebase Realtime Database，Leaflet 地圖，OSRM 路徑 API。測試用檔案內建的 `_selftest()` 搭配 `python3 -m http.server` + Playwright 瀏覽器執行（此專案沒有 Node/pytest 測試跑者）。

---

## 背景說明（給執行者）

這是一支純 HTML 檔案（沒有 build step、沒有 npm、沒有模組系統），三支檔案（iceland-trip.html／couple-trip-template.html／us-trip.html）內容幾乎相同（都是從 iceland-trip.html fork 出去的），本次要改的所有函式在三支裡逐字相同（唯一例外：iceland 版有「顯示字級」功能，`font-size` 寫成 `calc(16px*var(--fs))`；couple/us 版沒有這個功能，寫成純數字 `16px`；還有 iceland/couple 用寫死的 `'JPY'`、us 版用 `DEF_CUR` 常數——這些差異只出現在「尚無活動」提示與金額顯示，不影響本次邏輯，plan 裡會照各檔案原樣保留）。

**測試方式**：這個專案沒有自動化測試框架，所有邏輯測試都寫在檔案內的 `_selftest()` 函式裡（用 `ok(name, condition)` 這個小 helper），要跑測試得：
1. 在專案根目錄起一個本機伺服器：`python3 -m http.server 8765`
2. 用 Playwright 開 `http://localhost:8765/<檔名>`（注意：Playwright 擋 `file://` 協定，一定要走 http server）
3. 在頁面 console 執行 `_selftest()`，讀輸出的 `通過 X / 失敗 Y`

**不需要連 Firebase**：`_selftest()` 用自己建的假資料（`sched` 物件字面量）測試，跟真實 Firebase 連線無關，可以直接測不用先設定帳密。視覺驗證那幾步也一樣——直接在 console 把 `lastSched`／`curDay` 兩個全域變數改成假資料再呼叫 `renderSched(lastSched)`，全程不會寫入任何 Firebase 資料庫。

**檔案路徑**：全部檔案都在專案根目錄 `/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/`（以下路徑均相對於此目錄）。

**部署**：這三支都是 Netlify **手動拖拉部署**，不是 git-connected，commit/push 不會自動上線。本 plan 只負責把程式碼改對、commit 進 git；部署交給使用者自己手動拖。

---

## File Structure

只修改既有檔案，不新增檔案：

- Modify: `iceland-trip.html` — 新增 `morningHotel()`、擴充 `dayGeoActs()`、改寫 `renderSched()` 的活動陣列渲染區塊、刪除 `lastLegToStay()`、新增 `.stay-card` CSS、`_selftest()` 補測試
- Modify: `couple-trip-template.html` — 同上（差異：`font-size` 用純數字、金額用 `DEF_CUR`）
- Modify: `us-trip.html` — 同上（差異同 couple 版）

---

## Task 1: iceland-trip.html — 新增 morningHotel()

**Files:**
- Modify: `iceland-trip.html:967-982`

- [ ] **Step 1: 在 `coveringHotel()` 後面插入 `morningHotel()`**

用 Edit 工具，把：

```js
function coveringHotel(sched,did){
  const n=dayNum(did);
  for(const [hdid,day] of Object.entries(sched||{})){
    if(dayNum(hdid)>=n)continue;
    for(const a of Object.values(day.acts||{})){
      if(a.cat!=='hotel'||!a.stay?.out)continue;
      if(n<dayNum(a.stay.out))return a;
    }
  }
  return null;
}
```

改成：

```js
function coveringHotel(sched,did){
  const n=dayNum(did);
  for(const [hdid,day] of Object.entries(sched||{})){
    if(dayNum(hdid)>=n)continue;
    for(const a of Object.values(day.acts||{})){
      if(a.cat!=='hotel'||!a.stay?.out)continue;
      if(n<dayNum(a.stay.out))return a;
    }
  }
  return null;
}
// 今天早上從哪間住宿出發。跟 coveringHotel 的差別只有一個 <=：退房日早上人還是
// 從這裡出發的，要算進去；入住日當天本身不算（那天早上是「前一個住宿」的事，
// 不是這一間——這一間今天才剛要住進去）。
function morningHotel(sched,did){
  const n=dayNum(did);
  for(const [hdid,day] of Object.entries(sched||{})){
    if(dayNum(hdid)>=n)continue;
    for(const a of Object.values(day.acts||{})){
      if(a.cat!=='hotel'||!a.stay?.out)continue;
      if(n<=dayNum(a.stay.out))return a;
    }
  }
  return null;
}
```

- [ ] **Step 2: 確認沒有語法錯誤**

執行：`python3 -m http.server 8765 --directory "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"`（背景執行）

用 Playwright 開 `http://localhost:8765/iceland-trip.html`，讀 console，確認沒有紅字 JS 錯誤（此時頁面會停在 Setup 畫面，因為還沒填 Firebase 網址，這是預期行為，不用管）。

---

## Task 2: iceland-trip.html — 擴充 dayGeoActs()，加入 selftest

**Files:**
- Modify: `iceland-trip.html:2196-2212`（函式本體）
- Modify: `iceland-trip.html`（`_selftest()` 裡的「跨夜住宿」區塊）

- [ ] **Step 1: 改寫 dayGeoActs()**

把：

```js
function dayGeoActs(day,did){
  const list=Object.entries(day?.acts||{})
    .filter(([aid,a])=>a.geo&&typeof a.geo.lat==='number')
    .sort((a,b)=>{
      const oa=a[1].order!=null?a[1].order:999999, ob=b[1].order!=null?b[1].order:999999;
      if(oa!==ob)return oa-ob;
      return (a[1].time||'').localeCompare(b[1].time||'');
    })
    .map(([aid,a])=>({aid,name:a.name||'',lat:a.geo.lat,lng:a.geo.lng}));
  // 連住數晚時，中間幾天的活動清單裡沒有住宿，但那天最後還是要開回同一間。
  // 補在最後一個點，地圖才畫得出「今晚回哪裡」這一段。
  const cov=did?coveringHotel(lastSched,did):null;
  if(cov?.geo&&typeof cov.geo.lat==='number')
    list.push({aid:'stay',name:(cov.name||cov.loc||'住宿')+'（今晚住）',lat:cov.geo.lat,lng:cov.geo.lng});
  return list;
}
```

改成：

```js
function dayGeoActs(day,did){
  const list=Object.entries(day?.acts||{})
    .filter(([aid,a])=>a.geo&&typeof a.geo.lat==='number')
    .sort((a,b)=>{
      const oa=a[1].order!=null?a[1].order:999999, ob=b[1].order!=null?b[1].order:999999;
      if(oa!==ob)return oa-ob;
      return (a[1].time||'').localeCompare(b[1].time||'');
    })
    .map(([aid,a])=>({aid,name:a.name||'',lat:a.geo.lat,lng:a.geo.lng}));
  // 連住數晚時，早上是從昨晚住的地方出發、晚上又要開回今晚落腳處，但這兩者都不在
  // 當天的活動清單裡（住宿只記在入住日那一筆）。分別補在陣列最前/最後，地圖才畫得出
  // 完整路線；兩者是同一間且當天沒有其他活動時，只保留「今晚住」這一端——活動全無的
  // 純過夜日，講「今晚住哪」比「從哪出發」更貼近實況（沒有下一站可以出發去）。
  const morn=did?morningHotel(lastSched,did):null;
  const cov=did?coveringHotel(lastSched,did):null;
  const noRealActs=list.length===0;
  const sameHotel=morn&&cov&&morn===cov;
  if(morn?.geo&&typeof morn.geo.lat==='number'&&!(noRealActs&&sameHotel))
    list.unshift({aid:'stay-in',name:(morn.name||morn.loc||'住宿')+'（今早出發）',lat:morn.geo.lat,lng:morn.geo.lng});
  if(cov?.geo&&typeof cov.geo.lat==='number')
    list.push({aid:'stay-out',name:(cov.name||cov.loc||'住宿')+'（今晚住）',lat:cov.geo.lat,lng:cov.geo.lng});
  return list;
}
```

> **2026-08-30 訂正**：Task 3 執行後才發現，這裡的 guard 原本寫反了（放在 `cov`／今晚住那個 push 上，保留的其實是 `stay-in`）——跟 Task 3 Step 5 視覺驗證說明裡「day4 預期只有『今晚住』卡」互相矛盾。上面已經是訂正後的版本（guard 移到 `morn`／stay-in 那個 push 上，`noRealActs&&sameHotel` 時保留 `stay-out`）。iceland-trip.html 已在 commit `af2b058` 修正，couple/us 兩支請直接照這個訂正版實作，不要照最初版本。

- [ ] **Step 2: 在 `_selftest()` 的「跨夜住宿」區塊補測試**

找到這一段（在 `// ---- 跨夜住宿 ----` 區塊內）：

```js
    ok('入住日當天不算 covering（本來就有住宿活動）', coveringHotel(sched,'day2')===null);
    ok('中間日抓得到跨夜住宿', coveringHotel(sched,'day3')?.name==='東部旅館');
    ok('中間日第二天也抓得到', coveringHotel(sched,'day4')?.name==='東部旅館');
    ok('退房日當天不算住這裡', coveringHotel(sched,'day5')===null);
    ok('入住日之前不算', coveringHotel(sched,'day1')===null);
    ok('沒有 stay.out 就不跨夜', coveringHotel({day1:{acts:{h:{cat:'hotel',geo:{lat:64,lng:-19}}}}},'day2')===null);
```

在這 6 行後面（`// 中間日雖然只有一個景點...` 那行註解之前）插入：

```js
    ok('入住日當天不算 morning（那天早上不是從這間出發）', morningHotel(sched,'day2')===null);
    ok('中間日算 morning', morningHotel(sched,'day3')?.name==='東部旅館');
    ok('中間日第二天也算 morning', morningHotel(sched,'day4')?.name==='東部旅館');
    ok('退房日也算 morning（跟 coveringHotel 的差異點）', morningHotel(sched,'day5')?.name==='東部旅館');
    ok('入住日之前不算 morning', morningHotel(sched,'day1')===null);
    ok('沒有 stay.out 就不跨夜（morning）', morningHotel({day1:{acts:{h:{cat:'hotel',geo:{lat:64,lng:-19}}}}},'day2')===null);
    {
      const savedSched=lastSched;
      lastSched=sched;
      const d2=dayGeoActs(sched.day2,'day2');
      ok('入住日地圖不補住宿虛擬點（本來就有真實住宿活動）', !d2.some(p=>p.aid==='stay-in'||p.aid==='stay-out'));
      const d3=dayGeoActs(sched.day3,'day3');
      ok('中間日地圖首尾都補住宿點', d3.length===3&&d3[0].aid==='stay-in'&&d3[d3.length-1].aid==='stay-out');
      const d4=dayGeoActs(sched.day4,'day4');
      ok('中間日無活動且同一間住宿只保留今晚住宿點，不畫原地折返', d4.length===1&&d4[0].aid==='stay-out');
      const d5=dayGeoActs(sched.day5,'day5');
      ok('退房日地圖只補早上出發點，沒有今晚住宿點', d5.length===1&&d5[0].aid==='stay-in');
      lastSched=savedSched;
    }
```

- [ ] **Step 3: 執行 selftest 驗證新測試全過**

用 Playwright 開 `http://localhost:8765/iceland-trip.html`（如果 Task 1 的 server 還在跑，重用同一個），在 console 執行：

```js
_selftest()
```

預期：console 輸出結尾是 `通過 N / 失敗 0`（N 應該比改動前多 12 項：6 項 morningHotel 邊界測試 + 4 項 dayGeoActs 行為測試，這裡數的是新增的 `ok(...)` 呼叫數）。如果有 `❌` 開頭的行，讀訊息定位錯誤再修。

- [ ] **Step 4: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add iceland-trip.html
git commit -m "$(cat <<'EOF'
feat(iceland): 新增 morningHotel()，dayGeoActs 補上早上出發點

coveringHotel() 只回答「今晚住哪」，地圖與安全資訊夠用，但行程列表
要顯示「從住宿出發」還缺一個「早上從哪來」的推算，且退房日早上也要
算進去（跟 coveringHotel 刻意排除退房日不同）。dayGeoActs() 比照既有
「補今晚落腳處」的做法，在陣列最前面補上早上出發點；同一間住宿又當
天沒有其他活動時只補一個點，避免地圖上畫出原地折返的路線。

純資料層改動，renderSched 的卡片渲染留給下一個 commit。
EOF
)"
```

---

## Task 3: iceland-trip.html — renderSched 插入住宿卡片，刪除 lastLegToStay

**Files:**
- Modify: `iceland-trip.html:110`（CSS）
- Modify: `iceland-trip.html:2124-2156`（renderSched 活動陣列渲染區塊）
- Modify: `iceland-trip.html:2239-2247`（刪除 lastLegToStay）

- [ ] **Step 1: 新增 `.stay-card` CSS**

把：

```css
.act-row{display:flex;align-items:flex-start;padding:11px 16px;border-bottom:1px solid var(--border);gap:10px;cursor:grab;transition:opacity .2s;}
```

改成：

```css
.act-row{display:flex;align-items:flex-start;padding:11px 16px;border-bottom:1px solid var(--border);gap:10px;cursor:grab;transition:opacity .2s;}
.stay-card{cursor:default;}
.stay-card .act-name{color:var(--muted);font-style:italic;}
```

- [ ] **Step 2: 改寫 renderSched() 的活動陣列渲染區塊**

把：

```js
        ${!acts.length?'<div style="padding:14px 16px;color:var(--muted);font-size:calc(16px*var(--fs));text-align:center">尚無活動</div>':
          acts.map(([aid,act],idx)=>{
            const ac=ACTM[act.cat]||ACTM.other;
            const actIco=act.cat==='custom'?(act.customIco||'✏️'):ac.ico;
            const mapUrl='https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(act.loc||'');
            const sym=curSym(act.cost?.cur||'JPY');
            const dp=0;
            const closedTxt=closedLabel(act.closed);
            const isClosed=Array.isArray(act.closed)&&act.closed.includes(dowOf(day.date));
            const stayTxt=act.cat==='hotel'?stayLabel(act,day.date):'';
            // 兩端都要有座標才畫距離列。少一端就不畫，不用直線硬湊一個看似精確的數字。
            const nxt=acts[idx+1]?.[1];
            const legRow=(act.geo&&nxt?.geo)?legHtml(act.geo,nxt.geo):'';
            return `<div class="act-row" draggable="true" data-did="${did}" data-aid="${aid}">
              <div class="act-handle" data-did="${did}" data-aid="${aid}">⠿</div>
              <div class="act-ico" style="background:${ac.bg}">${actIco}</div>
              <div class="act-body">
                ${act.time?`<div class="act-time">⏰ ${act.time}</div>`:''}
                <div class="act-name">${esc(act.name||'')}${isClosed?'<span class="closed-tag">⚠️ 公休日</span>':''}</div>
                ${act.loc?`<div class="act-loc"><a href="${mapUrl}" target="_blank">📍 ${esc(act.loc)}</a></div>`:''}
                ${closedTxt?`<div class="closed-note">${closedTxt}</div>`:''}
                ${stayTxt?`<div class="ov-stay">${stayTxt}</div>`:''}
                ${act.note?`<div class="act-note-t">💬 ${autolink(act.note)}</div>`:''}
                ${act.images?.length?`<div class="act-imgs">${act.images.map(b=>`<img class="act-img-thumb" src="${b}" onclick="openLightbox('${b}')">`).join('')}</div>`:''}
                ${act.cost?.amt>0?`<div class="act-cost">💰 ${sym}${parseFloat(act.cost.amt).toFixed(dp)} ${act.cost.cur||'JPY'}</div>`:''}
              </div>
              <div class="act-btns">
                <button class="ib" onclick="openActEdit('${did}','${aid}')">✎</button>
                <button class="ib" onclick="delAct('${did}','${aid}')">✕</button>
              </div>
            </div>${legRow}`;
          }).join('')+lastLegToStay(did,acts)
        }
```

改成：

```js
        ${(()=>{
          const morn=morningHotel(lastSched,did);
          const cov=coveringHotel(lastSched,did);
          const sameHotel=morn&&cov&&morn===cov;
          const noRealActs=!acts.length;
          const items=[];
          if(morn?.geo&&typeof morn.geo.lat==='number'&&!(noRealActs&&sameHotel))
            items.push({stay:'in',geo:morn.geo,name:morn.name||morn.loc||'住宿'});
          acts.forEach(([aid,act])=>items.push({aid,act}));
          if(cov?.geo&&typeof cov.geo.lat==='number')
            items.push({stay:'out',geo:cov.geo,name:cov.name||cov.loc||'住宿'});
          if(!items.length)return '<div style="padding:14px 16px;color:var(--muted);font-size:calc(16px*var(--fs));text-align:center">尚無活動</div>';
          return items.map((item,idx)=>{
            const nxt=items[idx+1];
            const geo=item.stay?item.geo:item.act.geo;
            const nxtGeo=nxt?(nxt.stay?nxt.geo:nxt.act.geo):null;
            const legRow=(geo&&nxtGeo)?legHtml(geo,nxtGeo):'';
            if(item.stay){
              const txt=item.stay==='in'?`從 ${esc(item.name)} 出發`:`今晚住 ${esc(item.name)}`;
              return `<div class="act-row stay-card">
              <div class="act-ico" style="background:${ACTM.hotel.bg}">🛏️</div>
              <div class="act-body"><div class="act-name">${txt}</div></div>
            </div>${legRow}`;
            }
            const {aid,act}=item;
            const ac=ACTM[act.cat]||ACTM.other;
            const actIco=act.cat==='custom'?(act.customIco||'✏️'):ac.ico;
            const mapUrl='https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(act.loc||'');
            const sym=curSym(act.cost?.cur||'JPY');
            const dp=0;
            const closedTxt=closedLabel(act.closed);
            const isClosed=Array.isArray(act.closed)&&act.closed.includes(dowOf(day.date));
            const stayTxt=act.cat==='hotel'?stayLabel(act,day.date):'';
            return `<div class="act-row" draggable="true" data-did="${did}" data-aid="${aid}">
              <div class="act-handle" data-did="${did}" data-aid="${aid}">⠿</div>
              <div class="act-ico" style="background:${ac.bg}">${actIco}</div>
              <div class="act-body">
                ${act.time?`<div class="act-time">⏰ ${act.time}</div>`:''}
                <div class="act-name">${esc(act.name||'')}${isClosed?'<span class="closed-tag">⚠️ 公休日</span>':''}</div>
                ${act.loc?`<div class="act-loc"><a href="${mapUrl}" target="_blank">📍 ${esc(act.loc)}</a></div>`:''}
                ${closedTxt?`<div class="closed-note">${closedTxt}</div>`:''}
                ${stayTxt?`<div class="ov-stay">${stayTxt}</div>`:''}
                ${act.note?`<div class="act-note-t">💬 ${autolink(act.note)}</div>`:''}
                ${act.images?.length?`<div class="act-imgs">${act.images.map(b=>`<img class="act-img-thumb" src="${b}" onclick="openLightbox('${b}')">`).join('')}</div>`:''}
                ${act.cost?.amt>0?`<div class="act-cost">💰 ${sym}${parseFloat(act.cost.amt).toFixed(dp)} ${act.cost.cur||'JPY'}</div>`:''}
              </div>
              <div class="act-btns">
                <button class="ib" onclick="openActEdit('${did}','${aid}')">✎</button>
                <button class="ib" onclick="delAct('${did}','${aid}')">✕</button>
              </div>
            </div>${legRow}`;
          }).join('');
        })()}
```

注意：這一步之後 `lastLegToStay` 已經沒有任何呼叫端了，下一步刪掉它。

- [ ] **Step 3: 刪除 lastLegToStay()**

把：

```js
// 連住數晚時，「當天最後一站 → 今晚住哪」也是要開的一段路，但住宿活動記在入住日、
// 不在這天的清單裡，上面的相鄰配對配不到它，得另外補這一列。
function lastLegToStay(did,acts){
  const cov=coveringHotel(lastSched,did);
  if(!cov?.geo||typeof cov.geo.lat!=='number')return '';
  const last=[...acts].reverse().find(([,a])=>a.geo&&typeof a.geo.lat==='number');
  if(!last)return '';
  return legHtml(last[1].geo,cov.geo,`到今晚住宿「${esc(cov.name||cov.loc||'住宿')}」`);
}
```

改成空字串（整段刪除，不留殘骸註解）。

- [ ] **Step 4: 確認整檔沒有殘留的 lastLegToStay 呼叫**

```bash
grep -n "lastLegToStay" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/iceland-trip.html"
```

預期：無輸出（完全沒有殘留）。

- [ ] **Step 5: 視覺驗證（不連 Firebase，純 console 灌假資料）**

確認 Task 1 起的 http server 還在跑（`http://localhost:8765`）。用 Playwright 開 `http://localhost:8765/iceland-trip.html`，在 console 依序執行：

```js
lastSched = {
  day1:{date:'2026-09-14',acts:{}},
  day2:{date:'2026-09-15',acts:{h:{cat:'hotel',name:'東部旅館',geo:{lat:65.27,lng:-14.40},stay:{out:'day5'}}}},
  day3:{date:'2026-09-16',acts:{s:{cat:'sight',name:'黑沙灘',geo:{lat:65.00,lng:-14.90},order:0}}},
  day4:{date:'2026-09-17',acts:{}},
  day5:{date:'2026-09-18',acts:{}},
};
lastExps={};lastLegs={};
curDay='day3';
renderSched(lastSched);
```

預期看到（用 Playwright 截圖 `#schedBox` 確認）：
- 第一張卡：斜體「從 東部旅館 出發」
- 一條距離線（`約 XX 公里`，因為 `lastLegs` 是空的會退回直線 fallback）
- 「⏰ 黑沙灘」活動卡
- 另一條距離線
- 最後一張卡：斜體「今晚住 東部旅館」

再測 `curDay='day4'`（中間日、當天無活動、住宿相同）：

```js
curDay='day4';renderSched(lastSched);
```

預期只有**一張**卡「今晚住 東部旅館」（不是兩張、中間也沒有距離線）。

再測 `curDay='day5'`（退房日、當天無活動）：

```js
curDay='day5';renderSched(lastSched);
```

預期只有**一張**卡「從 東部旅館 出發」，沒有「今晚住」卡。

檢查瀏覽器 console 全程沒有紅字 JS 錯誤。

- [ ] **Step 6: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add iceland-trip.html
git commit -m "$(cat <<'EOF'
feat(iceland): 行程列表自動插入「從住宿出發」「今晚住宿」卡片

跨夜住宿只記在入住日，中間夜晚跟退房日早上原本行程列表完全看不到
住宿、也算不出從飯店到第一個景點要多久。renderSched() 把當天項目
組成 [出發卡?, ...真實活動, 入住卡?] 統一陣列渲染，相鄰項目一律用
既有 legHtml() 算距離，OSRM 快取與直線 fallback 原封不動複用。

這兩張卡是唯讀（無把手/無編輯刪除按鈕），不寫回 Firebase，純渲染層
推算。舊的 lastLegToStay() 被這套統一渲染取代，直接刪除。
EOF
)"
```

---

## Task 4: couple-trip-template.html — 同 Task 1（新增 morningHotel）

**Files:**
- Modify: `couple-trip-template.html:967-982`

- [ ] **Step 1: 插入 morningHotel()**

跟 Task 1 Step 1 完全相同的 old/new 內容（這段程式碼在 couple-trip-template.html 逐字相同，位置也是緊接在 `coveringHotel()` 後面）。

- [ ] **Step 2: 確認沒有語法錯誤**

用 Playwright 開 `http://localhost:8765/couple-trip-template.html`，確認 console 無錯誤。

---

## Task 5: couple-trip-template.html — 同 Task 2（擴充 dayGeoActs + selftest）

**Files:**
- Modify: `couple-trip-template.html:2320-2335`（dayGeoActs 函式本體）
- Modify: `couple-trip-template.html`（`_selftest()` 的「跨夜住宿」區塊）

- [ ] **Step 1: 改寫 dayGeoActs()**

跟 Task 2 Step 1 完全相同的 old/new 內容（couple-trip-template.html 這段函式逐字相同於 iceland 版）。

- [ ] **Step 2: 補 selftest**

跟 Task 2 Step 2 完全相同的插入內容——couple-trip-template.html 的「跨夜住宿」測試區塊（含 `sched` fixture）跟 iceland 版逐字相同，插入點一樣是 `ok('沒有 stay.out 就不跨夜', ...)` 那行後面、`// 中間日雖然只有一個景點...` 那行註解前面。

- [ ] **Step 3: 執行 selftest 驗證**

用 Playwright 開 `http://localhost:8765/couple-trip-template.html`，console 執行 `_selftest()`，確認 `失敗 0`。

- [ ] **Step 4: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add couple-trip-template.html
git commit -m "$(cat <<'EOF'
feat(couple): 新增 morningHotel()，dayGeoActs 補上早上出發點

同 iceland-trip.html 的 092e1db（見該次 commit 說明），這段跨夜住宿
子系統是從 iceland 版 fork 過來的同一套邏輯，兩邊同步修改。
EOF
)"
```

---

## Task 6: couple-trip-template.html — 同 Task 3（renderSched 插入卡片，刪除 lastLegToStay）

**Files:**
- Modify: `couple-trip-template.html:100`（CSS）
- Modify: `couple-trip-template.html:2247-2278`（renderSched 活動陣列渲染區塊）
- Modify: `couple-trip-template.html:2364-2372`（刪除 lastLegToStay）

- [ ] **Step 1: 新增 `.stay-card` CSS**

跟 Task 3 Step 1 完全相同的 old/new 內容（`.act-row{...}` 這行在 couple-trip-template.html 逐字相同）。

- [ ] **Step 2: 改寫 renderSched() 的活動陣列渲染區塊**

**注意跟 iceland 版的兩處差異**：`font-size:16px`（不是 `calc(16px*var(--fs))`，couple 版沒有字級縮放功能）、`curSym(act.cost?.cur||DEF_CUR)` 與 `act.cost.cur||DEF_CUR`（不是寫死 `'JPY'`，couple 版用可設定的 `DEF_CUR` 常數）。

把：

```js
        ${!acts.length?'<div style="padding:14px 16px;color:var(--muted);font-size:16px;text-align:center">尚無活動</div>':
          acts.map(([aid,act],idx)=>{
            const ac=ACTM[act.cat]||ACTM.other;
            const actIco=act.cat==='custom'?(act.customIco||'✏️'):ac.ico;
            const mapUrl='https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(act.loc||'');
            const sym=curSym(act.cost?.cur||DEF_CUR);
            const dp=0;
            const closedTxt=closedLabel(act.closed);
            const isClosed=Array.isArray(act.closed)&&act.closed.includes(dowOf(day.date));
            const stayTxt=act.cat==='hotel'?stayLabel(act,day.date):'';
            // 兩端都要有座標才畫距離列。少一端就不畫，不用直線硬湊一個看似精確的數字。
            const nxt=acts[idx+1]?.[1];
            const legRow=(act.geo&&nxt?.geo)?legHtml(act.geo,nxt.geo):'';
            return `<div class="act-row" draggable="true" data-did="${did}" data-aid="${aid}">
              <div class="act-handle" data-did="${did}" data-aid="${aid}">⠿</div>
              <div class="act-ico" style="background:${ac.bg}">${actIco}</div>
              <div class="act-body">
                ${act.time?`<div class="act-time">⏰ ${act.time}</div>`:''}
                <div class="act-name">${esc(act.name||'')}${isClosed?'<span class="closed-tag">⚠️ 公休日</span>':''}</div>
                ${act.loc?`<div class="act-loc"><a href="${mapUrl}" target="_blank">📍 ${esc(act.loc)}</a></div>`:''}
                ${closedTxt?`<div class="closed-note">${closedTxt}</div>`:''}
                ${stayTxt?`<div class="ov-stay">${stayTxt}</div>`:''}
                ${act.note?`<div class="act-note-t">💬 ${autolink(act.note)}</div>`:''}
                ${act.images?.length?`<div class="act-imgs">${act.images.map(b=>`<img class="act-img-thumb" src="${b}" onclick="openLightbox('${b}')">`).join('')}</div>`:''}
                ${act.cost?.amt>0?`<div class="act-cost">💰 ${sym}${parseFloat(act.cost.amt).toFixed(dp)} ${act.cost.cur||DEF_CUR}</div>`:''}
              </div>
              <div class="act-btns">
                <button class="ib" onclick="openActEdit('${did}','${aid}')">✎</button>
                <button class="ib" onclick="delAct('${did}','${aid}')">✕</button>
              </div>
            </div>${legRow}`;
          }).join('')+lastLegToStay(did,acts)
        }
```

改成：

```js
        ${(()=>{
          const morn=morningHotel(lastSched,did);
          const cov=coveringHotel(lastSched,did);
          const sameHotel=morn&&cov&&morn===cov;
          const noRealActs=!acts.length;
          const items=[];
          if(morn?.geo&&typeof morn.geo.lat==='number'&&!(noRealActs&&sameHotel))
            items.push({stay:'in',geo:morn.geo,name:morn.name||morn.loc||'住宿'});
          acts.forEach(([aid,act])=>items.push({aid,act}));
          if(cov?.geo&&typeof cov.geo.lat==='number')
            items.push({stay:'out',geo:cov.geo,name:cov.name||cov.loc||'住宿'});
          if(!items.length)return '<div style="padding:14px 16px;color:var(--muted);font-size:16px;text-align:center">尚無活動</div>';
          return items.map((item,idx)=>{
            const nxt=items[idx+1];
            const geo=item.stay?item.geo:item.act.geo;
            const nxtGeo=nxt?(nxt.stay?nxt.geo:nxt.act.geo):null;
            const legRow=(geo&&nxtGeo)?legHtml(geo,nxtGeo):'';
            if(item.stay){
              const txt=item.stay==='in'?`從 ${esc(item.name)} 出發`:`今晚住 ${esc(item.name)}`;
              return `<div class="act-row stay-card">
              <div class="act-ico" style="background:${ACTM.hotel.bg}">🛏️</div>
              <div class="act-body"><div class="act-name">${txt}</div></div>
            </div>${legRow}`;
            }
            const {aid,act}=item;
            const ac=ACTM[act.cat]||ACTM.other;
            const actIco=act.cat==='custom'?(act.customIco||'✏️'):ac.ico;
            const mapUrl='https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(act.loc||'');
            const sym=curSym(act.cost?.cur||DEF_CUR);
            const dp=0;
            const closedTxt=closedLabel(act.closed);
            const isClosed=Array.isArray(act.closed)&&act.closed.includes(dowOf(day.date));
            const stayTxt=act.cat==='hotel'?stayLabel(act,day.date):'';
            return `<div class="act-row" draggable="true" data-did="${did}" data-aid="${aid}">
              <div class="act-handle" data-did="${did}" data-aid="${aid}">⠿</div>
              <div class="act-ico" style="background:${ac.bg}">${actIco}</div>
              <div class="act-body">
                ${act.time?`<div class="act-time">⏰ ${act.time}</div>`:''}
                <div class="act-name">${esc(act.name||'')}${isClosed?'<span class="closed-tag">⚠️ 公休日</span>':''}</div>
                ${act.loc?`<div class="act-loc"><a href="${mapUrl}" target="_blank">📍 ${esc(act.loc)}</a></div>`:''}
                ${closedTxt?`<div class="closed-note">${closedTxt}</div>`:''}
                ${stayTxt?`<div class="ov-stay">${stayTxt}</div>`:''}
                ${act.note?`<div class="act-note-t">💬 ${autolink(act.note)}</div>`:''}
                ${act.images?.length?`<div class="act-imgs">${act.images.map(b=>`<img class="act-img-thumb" src="${b}" onclick="openLightbox('${b}')">`).join('')}</div>`:''}
                ${act.cost?.amt>0?`<div class="act-cost">💰 ${sym}${parseFloat(act.cost.amt).toFixed(dp)} ${act.cost.cur||DEF_CUR}</div>`:''}
              </div>
              <div class="act-btns">
                <button class="ib" onclick="openActEdit('${did}','${aid}')">✎</button>
                <button class="ib" onclick="delAct('${did}','${aid}')">✕</button>
              </div>
            </div>${legRow}`;
          }).join('');
        })()}
```

- [ ] **Step 3: 刪除 lastLegToStay()**

跟 Task 3 Step 3 完全相同的內容（此函式在 couple-trip-template.html 逐字相同）。

- [ ] **Step 4: 確認沒有殘留呼叫**

```bash
grep -n "lastLegToStay" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/couple-trip-template.html"
```

預期：無輸出。

- [ ] **Step 5: 視覺驗證**

跟 Task 3 Step 5 相同流程，改開 `http://localhost:8765/couple-trip-template.html`。這支有內建「試用模式」（Setup 畫面「🧪 先試用看看」按鈕會呼叫全域函式 `startDemo()`），如果想連著真實 UI 流程走也可以在 console 直接呼叫 `startDemo()` 代替手動塞 `lastSched`，但塞假資料這條路更容易精準控制成 Task 3 描述的三種情境（中間日同一間住宿無活動／退房日），建議還是用相同的 `lastSched`/`curDay` 手動注入方式。

- [ ] **Step 6: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add couple-trip-template.html
git commit -m "$(cat <<'EOF'
feat(couple): 行程列表自動插入「從住宿出發」「今晚住宿」卡片

同 iceland-trip.html 的實作（見該次 commit 說明），renderSched()
改成統一陣列渲染，舊的 lastLegToStay() 刪除。
EOF
)"
```

---

## Task 7: us-trip.html — 同 Task 1（新增 morningHotel）

**Files:**
- Modify: `us-trip.html:987-1002`

- [ ] **Step 1: 插入 morningHotel()**

跟 Task 1 Step 1 完全相同的 old/new 內容（us-trip.html 這段程式碼逐字相同，位置緊接在 `coveringHotel()` 後面）。

- [ ] **Step 2: 確認沒有語法錯誤**

用 Playwright 開 `http://localhost:8765/us-trip.html`，確認 console 無錯誤。

---

## Task 8: us-trip.html — 同 Task 2（擴充 dayGeoActs + selftest）

**Files:**
- Modify: `us-trip.html:2362-2377`（dayGeoActs 函式本體）
- Modify: `us-trip.html`（`_selftest()` 的「跨夜住宿」區塊）

- [ ] **Step 1: 改寫 dayGeoActs()**

跟 Task 2 Step 1 完全相同的 old/new 內容（us-trip.html 這段函式逐字相同於 iceland 版）。

- [ ] **Step 2: 補 selftest**

跟 Task 2 Step 2 完全相同的插入內容——us-trip.html 的「跨夜住宿」測試區塊（含 `sched` fixture）跟 iceland 版逐字相同。

- [ ] **Step 3: 執行 selftest 驗證**

用 Playwright 開 `http://localhost:8765/us-trip.html`，console 執行 `_selftest()`，確認 `失敗 0`。

- [ ] **Step 4: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add us-trip.html
git commit -m "$(cat <<'EOF'
feat(us): 新增 morningHotel()，dayGeoActs 補上早上出發點

同 iceland-trip.html 的 092e1db（見該次 commit 說明），這段跨夜住宿
子系統是從 iceland 版 fork 過來的同一套邏輯，三邊同步修改。
EOF
)"
```

---

## Task 9: us-trip.html — 同 Task 3（renderSched 插入卡片，刪除 lastLegToStay）

**Files:**
- Modify: `us-trip.html:100`（CSS）
- Modify: `us-trip.html:2289-2320`（renderSched 活動陣列渲染區塊）
- Modify: `us-trip.html:2406-2414`（刪除 lastLegToStay）

- [ ] **Step 1: 新增 `.stay-card` CSS**

跟 Task 3 Step 1 完全相同的 old/new 內容（`.act-row{...}` 這行在 us-trip.html 逐字相同）。

- [ ] **Step 2: 改寫 renderSched() 的活動陣列渲染區塊**

跟 couple-trip-template.html（Task 6 Step 2）**完全相同**的 old/new 內容——us-trip.html 這個區塊跟 couple 版逐字相同（`font-size:16px`、`DEF_CUR`，都沒有字級縮放功能）。

- [ ] **Step 3: 刪除 lastLegToStay()**

跟 Task 3 Step 3 完全相同的內容。

- [ ] **Step 4: 確認沒有殘留呼叫**

```bash
grep -n "lastLegToStay" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/us-trip.html"
```

預期：無輸出。

- [ ] **Step 5: 視覺驗證**

跟 Task 3 Step 5 相同流程，改開 `http://localhost:8765/us-trip.html`。這支也有 `startDemo()` 試用模式可用，但一樣建議用手動 `lastSched`/`curDay` 注入方式精準測三種情境。

- [ ] **Step 6: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add us-trip.html
git commit -m "$(cat <<'EOF'
feat(us): 行程列表自動插入「從住宿出發」「今晚住宿」卡片

同 iceland-trip.html 的實作（見該次 commit 說明），renderSched()
改成統一陣列渲染，舊的 lastLegToStay() 刪除。
EOF
)"
```

---

## Task 10: 收尾檢查

**Files:**
- 無新增/修改檔案，只做驗證

- [ ] **Step 1: 三支各自再跑一次完整 `_selftest()`**

依序對三個檔案執行（沿用同一個 http server）：

```js
_selftest()
```

三支都要是 `失敗 0`。

- [ ] **Step 2: 停掉本機測試伺服器**

```bash
# 找到 Task 1 起的 http.server process 並關閉
lsof -ti:8765 | xargs kill
```

- [ ] **Step 3: 確認 git log 三個 feature commit 都在**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git log --oneline -8
```

預期看到本次 6 個 commit（每支各 2 個：morningHotel/dayGeoActs 一個、renderSched/CSS 一個），加上先前的 2 個 spec commit。

- [ ] **Step 4: 提醒使用者手動部署**

不要自己執行部署——三支都是 Netlify **手動拖拉部署**，commit 不等於上線。跟使用者說完成了、需要她自己手動把三支拖去各自的 Netlify（冰島版有版本號可以之後核對是否真的上線；couple/us 版目前沒有版本號機制）。
