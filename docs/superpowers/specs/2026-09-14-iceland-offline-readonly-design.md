# 冰島版離線唯讀 + 離線可開啟 + 寫死連線資訊 — 設計

- 日期：2026-09-14（旅程出發當天，使用者已在國外、有網路、身邊有這台 Mac）
- 範圍：只改 `iceland-trip.html`，新增 `iceland-sw.js`；family / couple / us 不動
- 基準版本：`v0908a`（commit `c3e803f`），線上 `wang-iceland-2026.netlify.app` 已 curl 比對與 repo 相同（僅差 Netlify 自動插入的註解）

## 目標

1. **完全沒網路時 app 打得開**，看得到行程、記帳、記事、安全資訊（文字）與看過的地圖區域。
2. **沒有真正連上資料庫時一律唯讀**，任何修改都擋下並提示，避免寫入只排在記憶體佇列、關 app 後遺失。
3. **iOS 清掉網站資料後，有網路即可自動恢復**，不必重新輸入 Firebase 網址與 API Key。

非目標：照片離線可看（快照刻意排除 images，要改 IndexedDB，這次不做）、地圖圖磚預先下載整條路線、手動唯讀開關。

## 現況（查證過）

- 離線快照 `iceland_trip_snap`（localStorage，排除 images）已存在，`bootApp()` 先用它畫畫面。
- 沒有 Service Worker：網頁本身、Firebase SDK（gstatic）、Leaflet（unpkg）、字型全靠瀏覽器快取，離線重開沒有保障。SDK 載不進來時 `fb-retry-banner` 會蓋在畫面最上方。
- 修改完全沒擋：37 處 `DB.ref().set/update/remove` 分布在 25 個函式。
- `navigator.onLine` 只反映有沒有網路介面，訊號一格但傳不出去時仍回 true。
- `window.onload`：localStorage 沒有 `iceland_trip` 就停在 Setup 畫面；程式內沒有寫死網址或 apiKey。Firebase 規則 2026-09-10 已鎖 `auth != null`，沒有 apiKey 就讀不到。
- `ensureAuth()` 是 `currentUser ? resolve : signInAnonymously()`；SDK 剛初始化時 `currentUser` 還沒從 IndexedDB 還原，離線時會走到 `signInAnonymously()` 失敗 → `authFail()` 顯示錯誤橫幅。
- Netlify 目前是單一 HTML 拖拉部署，線上存成 `/index.html`（`/` 200、`/iceland-trip.html` 404），捷徑網址是根目錄。

## 設計

### 一、唯讀鎖定

**連線狀態**
- 全域 `_fbOnline=false`（開 app 即唯讀）。
- `_fbListen()` 掛上後監聽 `DB.ref('.info/connected')`，值變化時：更新 `_fbOnline` → `document.body.classList.toggle('ro',!_fbOnline)` → 更新橫幅 → `sync()`。
- `sync()` 的離線判斷改看 `_fbOnline`，不再單看 `navigator.onLine`，標題列小字與橫幅說法一致。

**`roBlock()` helper**：`_fbOnline` 為 true 回傳 false；否則 `toast('📴 離線唯讀中，連上網路才能修改')` 並回傳 true。

**寫入入口**

| 類別 | 函式 | 處理 |
|---|---|---|
| 使用者開啟編輯 | `fabTap`、`openActM`、`openDayM`、`openExpM`、`openNoteM`、`openTodoM`、活動複製 ⧉ 開窗、`initDnD`／`initActDnD`／`initNoteDnD` 的拖曳起點 | 開頭 `if(roBlock())return;` |
| 使用者儲存／刪除 | `saveAct`、`delAct`、`saveDayM`、`saveExp`、`delExp`、`saveNote`、`saveTodo`、`delNote`、`toggleTodoItem`、`doCopyAct`、`saveCfg`、`clearAll`、`moveAct` | 同樣加 `roBlock()`。**表單保持開啟、內容不清**，連上後可再按一次 |
| 背景自動寫入 | `ensureActGeo`、`ensureFacilities`、`ensureSafety`、`ensureLegs`、`pruneDayOutliers`、`fixDates`、`_fbListen` 內的 `/config` 遷移與 `createFullSchedule` | `!_fbOnline` 時**靜默跳過**，不提示；下次連上 listener 觸發時會重跑 |
| 不擋 | `openMemberDetail`、記事展開、匯率換算機、字級、地圖、lightbox | 不寫資料庫 |
| **刻意不擋** | `saveApiKey`、`changeFB` | 只寫本機 localStorage。**key 或網址錯了正是連不上的原因**，唯讀時擋掉會變成永遠修不回來 |

`doSetup`／`doConnect`（首次建立行程）本來就需要連線，維持現狀。

拖曳：`roBlock()` 放在 touchstart／dragstart 判定為把手之後、真正進入拖曳狀態之前，避免一般捲動也跳提示。

**畫面**
- `body.ro` 下，編輯類控制項 `opacity:.4`（＋ FAB、✏️、🗑、⧉、⠿、待辦勾選框、表單儲存鈕），仍可點擊以觸發提示。實作時以既有 class 列選擇器，不改 HTML 結構。
- 新增頂端橫幅 `#ro-banner`：「📴 離線唯讀 · {快照時間} 的資料」，時間取 `snapLoad().at`，無快照時只顯示「📴 離線唯讀」。字級走 `calc(Npx*var(--fs))`。
- **開 app 後 4 秒內仍未連上才顯示橫幅**（按鈕從一開始就是淡的）；之後中途斷線立即顯示，連上立即隱藏。
- `fb-retry-banner`（SDK 載入失敗）在**有快照時不顯示**，改由唯讀橫幅表達；沒有快照時照舊顯示（那時才真的需要重試）。

**認證離線行為**
- `ensureAuth()` 改為先等 SDK 還原登入狀態（`onAuthStateChanged` 第一次回呼），有使用者直接用，沒有才 `signInAnonymously()`。
- 認證失敗時若 `navigator.onLine===false` 或錯誤碼為 `auth/network-request-failed`：不顯示 `fb-err-banner`，維持唯讀，等 `online` 事件再重試 `connectFB()`。其他錯誤照舊 `authFail()`。

### 二、Service Worker（`iceland-sw.js`，部署時名為 `sw.js`）

**註冊**：主頁在 `window.onload` 開頭 `if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{})`，失敗不影響 app。

**快取區**（名稱帶 `VERSION` 常數，activate 時刪除不是本版的快取區；`skipWaiting()` + `clients.claim()`）

| 快取 | 內容 | 策略 |
|---|---|---|
| `shell-{VERSION}` | 導覽請求（`request.mode==='navigate'`），一律以 `/` 為快取鍵 | Network-first，**3 秒逾時**改用快取；網路成功就寫回快取。無快取又無網路時回一頁純文字「請先在有網路時開啟一次」 |
| `lib-{VERSION}` | `firebase-app-compat.js`、`firebase-database-compat.js`、`firebase-auth-compat.js`（9.23.0）、`leaflet.js`／`leaflet.css`（1.9.4）、Google Fonts CSS 與其 `fonts.gstatic.com` 字型檔 | install 時預抓 Firebase 與 Leaflet（任一失敗則安裝失敗，下次重試）；字型為執行期 cache-first，失敗不影響 |
| `tiles` | `tile.openstreetmap.org` | Cache-first，未命中才抓並存；上限 3000 張，超過刪最舊（依寫入順序）。不帶版本號，SW 更新不清空 |

**不攔截**（直接交給瀏覽器）：Firebase RTDB 網域、`identitytoolkit`／`securetoken` 認證、Nominatim、OSRM、Overpass、Open-Meteo、`open.er-api.com`，以及其他所有未列出的請求。

**OSM 圖磚政策**：只快取使用者實際瀏覽過的圖磚，不做批次預抓（OSM tile usage policy 禁止大量預下載）。

**更新**：HTML 走 network-first，改主頁部署後手機下次有網路開 app 即為新版；只有改到 lib 清單或 SW 邏輯時才需要調 `VERSION`。

### 三、寫死連線資訊

- 程式內加 `const DEF_FB_URL='…'`、`const DEF_FB_KEY='…'`，值取自 `~/iceland-firebase.txt`（實作時讀檔填入，不經對話傳遞）。
- `window.onload`：`CFG.url=dev.url||DEF_FB_URL`、`CFG.apiKey=dev.apiKey||DEF_FB_KEY`；localStorage 完全沒有 `iceland_trip` 時也用預設值直接 `bootApp()`，不再停在 Setup 畫面。**localStorage 有值時優先用本機值**（維持現有四台手機行為不變）。
- 設定頁的網址／API Key 欄位保留，可覆寫。
- `changeFB()`（清掉 localStorage 後重載）在有預設值之後的效果變成「回到預設連線」，不再回 Setup 畫面；這支是單一旅程專用 app，可接受。
- 前提（已成立）：Firebase 規則 2026-09-10 已鎖 `auth != null`，所以網址與 key 進 public repo 不再等於開放讀寫。
- 使用者另外手動做（不在程式內）：Google Cloud Console 為這把 API Key 加「HTTP 參照網址」限制，只允許 `https://wang-iceland-2026.netlify.app/*`。

### 四、部署

- 原始檔：`iceland-trip.html`、`iceland-sw.js`，皆 commit。
- 部署資料夾：`netlify-iceland/index.html`（複製自 `iceland-trip.html`）+ `netlify-iceland/sw.js`（複製自 `iceland-sw.js`），每次修改後由 Claude 同步複製；資料夾加入 `.gitignore`。
- 使用者把整個 `netlify-iceland` 資料夾拖到 wang-iceland-2026 的 Deploys。網址不變，不需重新加入主畫面。
- 版本號 `v0914a`。

## 驗證

**本機（playwright + `python3 -m http.server`，不連真實資料庫）**
- 以 route 攔截擋掉所有 Firebase 網域，並預先注入假快照與假 `iceland_trip` 設定，確保不觸發真實讀寫。
- 首次載入（線上）→ 確認 SW 安裝、`lib` 快取含 5 支檔案。
- `context.setOffline(true)` → 重新載入 → 頁面打得開、行程由快照渲染、`body.ro` 存在、4 秒後 `#ro-banner` 出現、`fb-err-banner`／`fb-retry-banner` 不出現。
- 唯讀下呼叫 `fabTap()`、`saveExp()`、`toggleTodoItem()` → 出現提示、stub DB 沒有收到寫入。
- stub `.info/connected` 切 true → `body.ro` 移除、橫幅消失；再切 false → 立即恢復唯讀。
- localStorage 清空後載入 → 直接 `bootApp()`，`CFG.url`/`apiKey` 為預設值。
- 開過地圖後離線重載 → 圖磚由快取提供。
- 既有 `_selftest()` 全數通過。

**部署後（四台手機各一次）**
1. 有網路開 app，確認標題列版本號 `v0914a`。
2. 關掉 app 重開一次（讓 SW 安裝完成並接管）。
3. 開飛航模式、從背景滑掉 app 後重開 → 看得到行程、出現離線唯讀橫幅、按 ＋ 會跳提示。
4. 關飛航模式 → 橫幅消失、可正常編輯。

## 資料安全說明

- 這次不改 `/schedule`、`/expenses`、`/notes` 任何既有資料，也不做資料遷移。
- 唯讀鎖只會「擋下寫入」，不會刪除或覆蓋任何內容。
- localStorage 的快照、連線資訊沿用既有 key，升級後不會被清除。
