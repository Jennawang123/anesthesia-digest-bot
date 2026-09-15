# us-trip 離線唯讀 + Service Worker + 寫死連線資訊 Implementation Plan

> **For agentic workers:** 每個 Task 由一個 subagent 執行，完成後由主 session 檢查 diff 與測試再派下一個。Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把冰島版 `v0914a` 的三項功能（離線唯讀、Service Worker、寫死連線資訊）原樣移植到 `us-trip.html`。

**設計來源：** `docs/superpowers/specs/2026-09-14-iceland-offline-readonly-design.md`（使用者 2026-09-15 確認「三件都做，跟冰島版一樣」，設計不重新討論）。

**程式碼來源：** `docs/superpowers/plans/2026-09-14-iceland-offline-readonly.md`（以下稱「冰島計畫」）。us-trip 與冰島版同源，**冰島計畫 Task 2–7 的每一個 old_string／new_string 程式碼區塊都照抄**，只套用下方「替換表」與各 Task 列出的差異。已於 2026-09-15 以腳本核對：冰島計畫 59 個錨點在 `us-trip.html` 中套用替換表後皆唯一出現，唯一例外是 `TRIP_KEYS`（見 Task 6 差異）與 Task 2 自己新增的 `// ---- 離線唯讀 ----`。

---

## 現況（已查證）

- `us-trip.html` 在 repo 根目錄，3957 行，版本 `u0913b`，無未 commit 變動。
- 線上 `https://jj-sandiego-2026.netlify.app/`：`/` 與 `/index.html` 200、`/us-trip.html` 404、`/sw.js` 404；內容與 repo 相同（只差 Netlify 注入的註解與 hud script）。
- 憑證檔 `~/us-trip-firebase.txt`，格式與冰島相同（`url=`／`apikey=`）。**注意專案 id 拼字是 `jj-sandeigo-2026`（ei），Netlify 網址是 `jj-sandiego-2026`（ie），兩者不同是既有事實，不要「修正」。**
- 寫入函式 26 個，比冰島多 `renameMembers`（只由 `saveCfg` 呼叫，擋 `saveCfg` 即涵蓋）。
- us-trip **沒有 `--fs` 字級乘數**。

## 替換表（套用於冰島計畫所有程式碼區塊與指令）

| 冰島計畫中的字串 | us-trip 用 |
|---|---|
| `iceland-trip.html`（原始檔路徑） | `us-trip.html`（repo 根目錄） |
| `iceland/iceland-sw.js`、`iceland-sw.js` | `us-trip-sw.js`（repo 根目錄） |
| `iceland_trip`（localStorage key） | `us_trip` |
| `iceland_trip_snap` | `us_trip_snap` |
| `v0908a` | `u0913b` |
| `v0914a` | `u0915a` |
| `lib-v0914a`（測試裡的快取名） | `lib-u0915a` |
| `~/iceland-firebase.txt` | `~/us-trip-firebase.txt` |
| `iceland-2026-f13e6`（檢查網址用） | `jj-sandeigo-2026` |
| `wang-iceland-2026.netlify.app` | `jj-sandiego-2026.netlify.app` |
| `scripts/test_iceland_offline.py` | `scripts/test_us_offline.py` |
| `netlify-iceland/` | `netlify-us-trip/` |
| commit 訊息的 `(iceland)` | `(us)` |
| 測試 SNAP 標題 `測試旅程`、行程 `藍湖溫泉` | 不變（假資料） |
| `PORT = 8765` | `PORT = 8766`（避免與冰島測試同時跑時撞埠） |

## 動手前必讀

照冰島計畫「動手前必讀」全部規則（字串錨點、不連真實 DB、只 add 本計畫檔案、commit 結尾兩行、`python3`）。另加：
- 動手前 `git status --short us-trip.html`，有未 commit 變動就停。
- **不可把 Firebase 網址或 apiKey 的值印出來**（Task 6 起檔案內含真實值）。

---

### Task 1: 測試腳手架

**Files:** Create `scripts/test_us_offline.py`

- [ ] **Step 1:** 以目前的 `scripts/test_iceland_offline.py` 為來源，**只取到 `test_selftest` 為止的腳手架**（docstring、import、常數、`check`、`Quiet`、`build_site`、`serve`、`new_page`、`test_selftest`、`TESTS={'selftest':...}`、`main`），不要帶後面的 ro_state 等測試（它們在各 Task 才加）。套用替換表，並把 `build_site` 改成：

```python
def build_site():
    d = Path(tempfile.mkdtemp(prefix='us-site-'))
    shutil.copy(ROOT / 'us-trip.html', d / 'index.html')
    if (ROOT / 'us-trip-sw.js').exists():
        shutil.copy(ROOT / 'us-trip-sw.js', d / 'sw.js')
    return d
```

`new_page()` 要保留冰島版後來加的 `identitytoolkit`/`securetoken` route 阻擋（Task 6 寫死真 key 後，其他測試才不會拿真 key 去匿名登入）。

- [ ] **Step 2:** `python3 scripts/test_us_offline.py selftest` → `通過 1 / 失敗 0`。若既有 `_selftest()` 失敗，記下失敗項名稱回報，不改 `us-trip.html`。
- [ ] **Step 3:** commit `test(us): 離線唯讀端對端測試腳手架`，只 add `scripts/test_us_offline.py`，push。

### Task 2: 唯讀狀態核心

照冰島計畫 Task 2 Step 1–9，套替換表。**差異：**
- Step 3 CSS 的 `#ro-banner` 字級用固定值：`font-size:15px;`（取代 `font-size:calc(15px*var(--fs));`）。
- 測試 `ro_state` 照抄。
- Step 8：`python3 scripts/test_us_offline.py selftest ro_state` 全過。
- commit `feat(us): 離線唯讀狀態、淡化編輯鈕與離線橫幅`。

### Task 3: 使用者寫入入口加守門

照冰島計畫 Task 3 Step 1–7，套替換表，21 個宣告行、Step 4 特例、Step 5 拖曳 7 處全部照抄。**差異：**
- 測試 `blocks_writes`：us-trip 成員固定兩位，`saveCfg()` 在唯讀下應被擋在第一行，不需額外處理；若「連上後 saveExp 正常寫入」失敗，Read us-trip 的 `saveExp` 看是否需要 `split` 等欄位，只修測試。
- 完成後新增守門行數應為 33（`git show HEAD -- us-trip.html | grep -c "^+.*roBlock"`），回報實際數字。
- commit `feat(us): 所有使用者寫入入口在離線時擋下並提示`。

### Task 4: 背景寫入守門、連線偵測、認證離線處理

照冰島計畫 Task 4 Step 1–8，套替換表，無其他差異。commit `feat(us): 以 .info/connected 判斷連線、背景寫入離線靜默跳過、離線登入不跳錯`。

### Task 5: Service Worker

照冰島計畫 Task 5 Step 1–7，套替換表。**差異：**
- 新檔 `us-trip-sw.js` 內容與目前的 `iceland/iceland-sw.js` 相同，只把 `const VERSION='v0914a';` 改成 `const VERSION='u0915a';`，註解「冰島版 Service Worker」改「us-trip Service Worker」。建議直接 `cp iceland/iceland-sw.js us-trip-sw.js` 再用 Edit 改這兩處，確保 diff 只有兩行（`diff iceland/iceland-sw.js us-trip-sw.js` 回報）。
- 測試 `sw_offline`、`auth_offline` 照抄（快取名 `lib-u0915a`）。
- commit `feat(us): Service Worker 讓 app 完全離線打得開、看過的地圖圖磚留存`，add `us-trip-sw.js us-trip.html scripts/test_us_offline.py`。

### Task 6: 寫死連線資訊

照冰島計畫 Task 6 Step 1–8，套替換表。**差異：**
- Step 3 的錨點改為 us-trip 的實際內容：

old_string：
```
const TRIP_KEYS=['title','members','start','days','photo','city','cityQuery','lat','lng','tz','cc'];
```
new_string：
```
const TRIP_KEYS=['title','members','start','days','photo','city','cityQuery','lat','lng','tz','cc'];
// 寫死的連線資訊：iOS 清掉網站資料後，有網路就能自動恢復，不必重新輸入。
// Firebase Web API Key 本來就會出現在前端，保護靠 Security Rules（2026-09-10 已鎖 auth != null）。
const DEF_FB_URL='__DEF_FB_URL__', DEF_FB_KEY='__DEF_FB_KEY__';
// 本機有值優先用本機（維持既有裝置行為），沒有才用寫死的
function deviceCfg(dev){dev=dev||{};return {...dev,url:dev.url||DEF_FB_URL,apiKey:dev.apiKey||DEF_FB_KEY};}
```
- Step 4 腳本讀 `~/us-trip-firebase.txt`，assert 改成 `'jj-sandeigo-2026' in url`，寫入 `us-trip.html`。
- 測試 `default_cfg` 的檢查改為 `'jj-sandeigo-2026' in (r['url'] or '')`，保留 `service_workers='block'` 與 gstatic route 阻擋，失敗訊息不印 r。
- 同一個 Task 順便改過時註解（冰島是在 Task 7 才改，這裡提前）：

old_string：
```
// API Key 跟資料庫網址一樣存在本機 localStorage，每台裝置各自貼一次，
// 刻意不寫死在檔案裡（這個 repo 是 public，寫死等於把金鑰放進 Git 歷史）。
```
new_string：
```
// 網址與 API Key 以本機 localStorage 為優先，沒有時用檔案裡寫死的 DEF_FB_URL/DEF_FB_KEY（見 deviceCfg）。
// 2026-09-15 起寫死：規則已鎖 auth != null，Web API Key 本來就公開在前端，保護靠 Security Rules
// 與 Google Cloud 的 HTTP 參照網址限制。
```
- Step 8 檢查改用計數：`git diff us-trip.html | grep -c "firebasedatabase.app\|AIza"`，預期 2（DEF_FB 那行 + selftest 的假網址），不印內容。
- commit `feat(us): 寫死 Firebase 網址與 apiKey，本機資料被清掉時自動恢復連線`。

### Task 7: 版本號、部署資料夾

照冰島計畫 Task 7 Step 1–5，套替換表（`u0913b`→`u0915a`、`netlify-us-trip/`）。註解已在 Task 6 改過，這裡不再改。
- Step 3：`mkdir -p netlify-us-trip && cp us-trip.html netlify-us-trip/index.html && cp us-trip-sw.js netlify-us-trip/sw.js`，兩個 cmp 相同。
- Step 4：`.gitignore` 只 stage `netlify-us-trip/` 一行（`git show HEAD:.gitignore` + 追加 + `git update-index --cacheinfo`），staged diff 只有那一行。工作區 `.gitignore` 也要追加該行。
- commit `chore(us): u0915a，部署資料夾 netlify-us-trip 加入 gitignore`。
- Step 6（memory）與 Step 7（交付說明）由主 session 處理，subagent 不做。

## 部署後（主 session）

1. 使用者拖 `netlify-us-trip/` 整個資料夾到 jj-sandiego-2026。
2. 主 session `curl` 確認 `/sw.js` 200、`/` 含 `u0915a`。
3. 使用者到 `https://console.cloud.google.com/apis/credentials?project=jj-sandeigo-2026`，Browser key 的「應用程式限制」選「網站」，加 `https://jj-sandiego-2026.netlify.app/*` 與 `https://jj-sandeigo-2026.firebaseapp.com/*`，API 限制不動。
4. 主 session 用 `identitytoolkit accounts:lookup` 帶無效 idToken 驗證：允許 Referer → 400 INVALID_ID_TOKEN、其他／空 → 403。
5. 手機各一次：有網路開 app 確認 `u0915a` → 滑掉重開 → 飛航模式滑掉重開看得到離線唯讀資料。
