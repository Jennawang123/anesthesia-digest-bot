# 雪梨旅遊 App 優化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `sydney-trip.html` 加入歌劇院照片 header、Noto Serif TC 字體、Open-Meteo 天氣、每日花費 chip，並更新 day card 格式（Day N + 日期 badge，移除活動數量）。

**Architecture:** 單一 HTML 檔案，新增 `fetchWeather()` 與 `calcDaySpend()` 兩個獨立函式，在 `bootApp()` 初始化順序中串接；`renderSched()` 讀取模組層級 `weatherByDate` 與 `lastExps` 組合 chip。

**Tech Stack:** Vanilla JS、Open-Meteo REST API、Google Fonts (Noto Serif TC / Noto Sans TC)、Firebase Realtime Database（現有）

---

## 檔案地圖

| 動作 | 路徑 | 說明 |
|------|------|------|
| 修改 | `sydney-trip.html:1-8` | `<head>` 加入 Google Fonts `<link>` |
| 修改 | `sydney-trip.html:44` | `.hdr` CSS 改為 relative+overflow:hidden |
| 修改 | `sydney-trip.html:44-46` | 新增 `.hdr-photo`、`.hdr-overlay`、`.hdr-title-block`、`.day-num`、`.day-date-badge`、`.day-meta`、`.wchip`、`.schip` CSS |
| 修改 | `sydney-trip.html:222-225` | header HTML 換成照片 + overlay + title-block |
| 修改 | `sydney-trip.html:392` | 新增 `let weatherByDate = new Map();` |
| 修改 | `sydney-trip.html:403` | 新增 `fmtDayBadge()` helper |
| 修改 | `sydney-trip.html:415-425` | 新增 `fetchWeather()` 函式 |
| 修改 | `sydney-trip.html:461` | `bootApp()` 改為先 fetchWeather 再 connectFB |
| 修改 | `sydney-trip.html:480-486` | `connectFB()` 內移動 `lastExps` 賦值到 `renderSched` 之前 |
| 修改 | `sydney-trip.html:612-654` | `renderSched()` 新增 weather/spend chip、day card 格式 |
| 修改 | `sydney-trip.html:736` | 新增 `calcDaySpend()` 函式 |

---

## Task 1：Google Fonts + CSS 更新

**Files:**
- Modify: `sydney-trip.html:1-199`

- [ ] **Step 1：在 `<head>` 第一行加入 Google Fonts**

在 `sydney-trip.html` 找到 `<head>` 下方、`<script>` 之前，插入：

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@600;700&family=Noto+Sans+TC:wght@400;500;600;700&display=swap" rel="stylesheet">
```

插入位置（原始碼 line 8，`<meta name="apple-mobile-web-app-title">` 之後，`<title>` 之前）：

```html
<meta name="apple-mobile-web-app-title" content="雪梨之旅">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@600;700&family=Noto+Sans+TC:wght@400;500;600;700&display=swap" rel="stylesheet">
<title>雪梨之旅</title>
```

- [ ] **Step 2：替換 `.hdr` CSS（原 line 44）**

找到：
```css
.hdr{background:var(--blue);color:#fff;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;box-shadow:0 2px 8px rgba(0,119,182,.25);}
.hdr-t{font-size:17px;font-weight:700;}
.hdr-s{font-size:12px;opacity:.85;display:flex;align-items:center;gap:5px;}
```

替換為：
```css
.hdr{position:relative;height:168px;flex-shrink:0;overflow:hidden;}
.hdr-photo{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center 35%;}
.hdr-overlay{position:absolute;inset:0;z-index:5;background:linear-gradient(to bottom,rgba(0,0,0,.08) 0%,transparent 35%,rgba(0,0,0,.18) 60%,rgba(0,0,0,.62) 100%);}
.hdr-title-block{position:absolute;top:16px;left:18px;z-index:20;}
.hdr-t{font-family:'Noto Serif TC',serif;font-size:26px;font-weight:700;color:#fff;text-shadow:0 1px 10px rgba(0,0,0,.55),0 2px 24px rgba(0,0,0,.28);line-height:1;}
.hdr-s{font-size:11px;color:rgba(255,255,255,.85);display:flex;align-items:center;gap:5px;margin-top:6px;}
```

- [ ] **Step 3：在 `</style>` 之前加入新 day card CSS**

在 `#drag-ghost{...}` 之後、`</style>` 之前插入：

```css
.day-num{font-family:'Noto Serif TC',serif;font-size:15px;font-weight:700;color:#1A3A78;letter-spacing:.2px;}
.day-date-badge{font-size:10px;font-weight:600;color:#6B8FC4;background:#EBF2FC;border-radius:5px;padding:2px 7px;margin-left:2px;}
.day-meta{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-top:4px;}
.wchip{display:inline-flex;align-items:center;gap:2px;background:#E8F3FC;border-radius:20px;padding:2px 8px;font-size:10px;font-weight:600;color:#1A5BA8;}
.schip{display:inline-flex;align-items:center;gap:2px;background:#EAF5EA;border-radius:20px;padding:2px 8px;font-size:10px;font-weight:600;color:#1E7D32;}
```

- [ ] **Step 4：開啟瀏覽器驗證 CSS 載入**

以 `http://localhost:7823/sydney-trip.html` 開啟（需先執行 `python3 -m http.server 7823`），打開 DevTools → Network 確認 Google Fonts 請求狀態 200，確認 header 高度變為 168px（暫時空白屬正常）。

---

## Task 2：Header HTML 更新

**Files:**
- Modify: `sydney-trip.html:222-225`

- [ ] **Step 1：替換 header HTML**

找到（原始碼 line 222-225）：
```html
<div id="app">
  <div class="hdr">
    <div class="hdr-t" id="appTitle">🎭 雪梨之旅</div>
    <div class="hdr-s"><span class="dot" id="syncDot"></span><span id="syncTxt">已同步</span></div>
  </div>
```

替換為：
```html
<div id="app">
  <div class="hdr">
    <img class="hdr-photo" src="https://www.pelago.com/img/collections/sydney-opera-house/0527-0635_sydney-opera-house.jpg" alt="Sydney Opera House">
    <div class="hdr-overlay"></div>
    <div class="hdr-title-block">
      <div class="hdr-t" id="appTitle">雪梨之旅</div>
      <div class="hdr-s"><span class="dot" id="syncDot"></span><span id="syncTxt">已同步</span></div>
    </div>
  </div>
```

- [ ] **Step 2：修改 setup 預設標題（移除 emoji）**

找到（原始碼 line 432）：
```js
CFG={url,title:document.getElementById('s_title').value.trim()||'🎭 雪梨之旅',
```

替換為：
```js
CFG={url,title:document.getElementById('s_title').value.trim()||'雪梨之旅',
```

- [ ] **Step 3：瀏覽器驗證**

重新整理 `http://localhost:7823/sydney-trip.html`，確認：
- 歌劇院照片滿版顯示於 header
- 「雪梨之旅」白色文字位於左上角天空區域
- 標題字體為 Noto Serif TC（有襯線感）
- 「已同步」綠點顯示於標題下方

---

## Task 3：新增 `weatherByDate` 變數 + `fmtDayBadge()` + `fetchWeather()`

**Files:**
- Modify: `sydney-trip.html:392-425`

- [ ] **Step 1：新增 `weatherByDate` 模組層級變數**

找到（原始碼 line 392）：
```js
let CFG={},DB=null,curTab='sched';
```

替換為：
```js
let CFG={},DB=null,curTab='sched';
let weatherByDate=new Map();
```

- [ ] **Step 2：在 `fmtDt` 之後新增 `fmtDayBadge` helper**

找到（原始碼 line 404）：
```js
const fmtDt=iso=>{const d=new Date(iso);return d.toLocaleDateString('zh-TW',{month:'short',day:'numeric'})+' '+d.toLocaleTimeString('zh-TW',{hour:'2-digit',minute:'2-digit'});};
```

在該行之後插入：
```js
const fmtDayBadge=d=>{if(!d)return'';const dt=new Date(d+'T12:00:00');const w=['日','一','二','三','四','五','六'][dt.getDay()];return`${dt.getMonth()+1}月${dt.getDate()}日（${w}）`;};
```

- [ ] **Step 3：在 `fetchRate()` 之後新增 `fetchWeather()`**

找到（原始碼 line 425）：
```js
  }catch(e){exchRate=null;}
}
```

（即 `fetchRate` 函式結尾）在其後插入：

```js
function weatherDesc(code){
  if(code===0)return{icon:'☀️',desc:'晴'};
  if(code<=3)return{icon:'⛅',desc:'多雲'};
  if(code===45||code===48)return{icon:'🌫️',desc:'霧'};
  if(code>=51&&code<=67)return{icon:'🌧️',desc:'有雨'};
  if(code>=80&&code<=82)return{icon:'🌦️',desc:'陣雨'};
  if(code>=95&&code<=99)return{icon:'⛈️',desc:'雷雨'};
  return{icon:'☁️',desc:'陰'};
}
async function fetchWeather(){
  try{
    const r=await fetch('https://api.open-meteo.com/v1/forecast?latitude=-33.87&longitude=151.21&hourly=temperature_2m,weathercode&timezone=Australia/Sydney&forecast_days=16');
    const d=await r.json();
    const times=d.hourly.time,temps=d.hourly.temperature_2m,codes=d.hourly.weathercode;
    weatherByDate=new Map();
    times.forEach((t,i)=>{
      if(t.endsWith('T12:00')){
        const ds=t.split('T')[0];
        const{icon,desc}=weatherDesc(codes[i]);
        weatherByDate.set(ds,{temp:Math.round(temps[i]),icon,desc});
      }
    });
  }catch(e){weatherByDate=new Map();}
}
```

- [ ] **Step 4：DevTools 手動驗證（可選）**

在瀏覽器 Console 執行：
```js
await fetchWeather(); console.log([...weatherByDate.entries()].slice(0,3));
```

預期輸出：3 筆形如 `["2026-04-21", {temp: 22, icon: "⛅", desc: "多雲"}]` 的陣列項目。若 API 失敗，`weatherByDate.size` 為 0，屬預期降級行為。

---

## Task 4：新增 `calcDaySpend()`

**Files:**
- Modify: `sydney-trip.html:736-743`

- [ ] **Step 1：在 `calcBal()` 之後新增 `calcDaySpend()`**

找到（原始碼 line 743 結尾）：
```js
  return{p1p,p2p,total:p1p+p2p,settle:p1p-p1s};
}
```

（即 `calcBal` 函式結尾）在其後插入：

```js
function calcDaySpend(exps,dateStr){
  const totals=new Map();
  Object.values(exps).forEach(e=>{
    if(e.date!==dateStr)return;
    const cur=e.cur||'AUD';
    totals.set(cur,(totals.get(cur)||0)+(e.amt||0));
  });
  totals.forEach((v,k)=>{if(v<=0)totals.delete(k);});
  return totals;
}
```

- [ ] **Step 2：瀏覽器 Console 驗證**

在 Console 執行（需先有 Firebase 資料）：
```js
console.log([...calcDaySpend(lastExps, '2026-04-20').entries()]);
```

若當天無支出回傳空 Map `[]`，有支出回傳如 `[["AUD", 262]]`。

---

## Task 5：修正 `lastExps` 賦值順序 + 更新 `renderSched()`

**Files:**
- Modify: `sydney-trip.html:478-486` （connectFB 內部）
- Modify: `sydney-trip.html:612-654` （renderSched 函式）

- [ ] **Step 1：修正 `connectFB()` 內 `lastExps` 賦值順序**

找到（原始碼 line 480-486）：
```js
      renderSched(sched);
      lastExps=d.expenses||{};
      renderExp(lastExps);
      renderNotes(d.notes||{});
      sync(false);
```

替換為：
```js
      lastExps=d.expenses||{};
      renderSched(sched);
      renderExp(lastExps);
      renderNotes(d.notes||{});
      sync(false);
```

（說明：`renderSched` 會呼叫 `calcDaySpend(lastExps, ...)` 因此 `lastExps` 必須先賦值）

- [ ] **Step 2：更新 `renderSched()` 的 day card 模板**

找到（原始碼 line 619-630）：
```js
    return `<div class="day-card" id="dc-${did}">
      <div class="day-hdr" onclick="toggleDay('${did}')">
        <div class="day-n">${dayN}</div>
        <div class="day-info">
          <div class="day-tit">${esc(day.label||did)}<button class="day-eb" onclick="event.stopPropagation();openDayM('${did}','${esc(day.label||'')}')">✎</button></div>
          <div class="day-dt">${fmtD(day.date)}${acts.length?' · '+acts.length+' 個活動':''}</div>
        </div>
        <div class="day-chev">›</div>
      </div>
```

替換為：
```js
    const wInfo=weatherByDate.get(day.date);
    const wChip=wInfo?`<span class="wchip">${wInfo.icon} ${wInfo.temp}°C ${wInfo.desc}</span>`:'';
    const spend=calcDaySpend(lastExps,day.date);
    const sChips=[...spend.entries()].map(([cur,tot])=>{
      const sym=cur==='AUD'?'$':'NT$';
      const ico=cur==='AUD'?'💵':'💴';
      return`<span class="schip">${ico} ${sym}${Math.round(tot).toLocaleString('zh-TW')} ${cur}</span>`;
    }).join('');
    const metaRow=(wChip||sChips)?`<div class="day-meta">${wChip}${sChips}</div>`:'';
    return `<div class="day-card" id="dc-${did}">
      <div class="day-hdr" onclick="toggleDay('${did}')">
        <div class="day-info">
          <div class="day-tit"><span class="day-num">Day ${dayN}</span><span class="day-date-badge">${fmtDayBadge(day.date)}</span><button class="day-eb" onclick="event.stopPropagation();openDayM('${did}','${esc(day.label||'')}')">✎</button></div>
          <div class="day-dt">${esc(day.label||did)}</div>
          ${metaRow}
        </div>
        <div class="day-chev">›</div>
      </div>
```

- [ ] **Step 3：瀏覽器驗證 day card 格式**

重新整理後展開行程頁，確認每張 day card：
- 顯示「Day 1 ＋ 藍色日期 badge（如 4月20日（日））」
- 標題為行程名稱（不含活動數量）
- 若有 Firebase 支出資料，顯示 `💵 $xxx AUD` chip
- 若天氣 API 成功，顯示天氣 chip（如 `⛅ 22°C 多雲`）

---

## Task 6：更新 `bootApp()` 初始化順序

**Files:**
- Modify: `sydney-trip.html:460-461`

- [ ] **Step 1：改為先 fetchWeather 再 connectFB**

找到（原始碼 line 460-461）：
```js
  renderCatGrid();renderACGrid();initDnD();
  connectFB();fetchRate();
```

替換為：
```js
  renderCatGrid();renderACGrid();initDnD();
  fetchWeather().finally(()=>connectFB());
  fetchRate();
```

（說明：`finally` 確保即使天氣 API 失敗，Firebase 仍會連線；天氣通常在 300ms 內回應，Firebase 初始化時間相近，實際使用不會有明顯延遲）

- [ ] **Step 2：完整端對端驗證**

重新整理 `http://localhost:7823/sydney-trip.html`，依序確認：

1. 開啟 DevTools Network 面板
2. 可見 `forecast?latitude=-33.87...` 請求，狀態 200
3. Firebase 在天氣請求之後建立連線（Network 時序）
4. 行程頁每張 day card 顯示天氣 chip（例如：`⛅ 22°C 多雲`）
5. 若已有支出記錄，顯示對應幣別的 spend chip
6. 無支出當天不顯示 schip
7. Console 無 JS 錯誤

- [ ] **Step 3：離線降級驗證**

在 DevTools Network 勾選「Offline」後重新整理，確認：
- App 正常顯示（Firebase 會失敗，屬預期）
- Day card 不顯示 wchip（不 crash）
- Console 無 Uncaught 錯誤

---

## 驗收清單

| 功能 | 驗收標準 |
|------|---------|
| 照片 header | 歌劇院+海港大橋照片滿版，「雪梨之旅」Noto Serif TC 位於左上天空區域 |
| Day card | 顯示「Day N ＋ 日期 badge」；無活動數量；label 為行程標題 |
| 天氣 chip | 有 API 資料時顯示 `icon °C 描述`；API 失敗時靜默不顯示 |
| 花費 chip | 有當日支出時顯示對應幣別；無支出時不顯示 |
| 多幣別 | AUD 和 TWD 各自顯示一個 chip（同天有兩種幣則兩個 chip） |
| 字體 | 標題、Day 數字使用 Noto Serif TC；內文使用 Noto Sans TC |
