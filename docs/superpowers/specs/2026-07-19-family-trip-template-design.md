# 家庭旅遊 App 設計文件

**日期：** 2026-07-19
**目標檔案：** `family-trip-template.html`（單一 HTML 檔 PWA，通用模板，非單次行程專屬）
**基底：** `japan-trip.html`（fork 後移除 Japan 專屬設定與分帳邏輯，改為通用多人記帳）

---

## 1. 架構總覽

**技術棧：** 單一 HTML PWA，無後端，沿用 japan-trip.html 架構
- Firebase Realtime Database（資料同步，使用者自行輸入 databaseURL，不寫死）
- Gemini API（收據 OCR，按需呼叫，沿用現有 model 版本）
- Open-Meteo Forecast API（天氣，免費無 key）
- **新增：** Open-Meteo Geocoding API（`geocoding-api.open-meteo.com/v1/search`，城市名稱轉座標，免費無 key）

**與 japan-trip.html 的定位差異：** japan-trip.html 是「岡山行程」專屬檔案；family-trip-template.html 是通用模板，任何目的地、任何家庭旅行都直接複製這一份使用，不寫死城市或幣別。

**Setup 畫面**（首次啟動，存入 `localStorage`）：
- Firebase databaseURL
- Gemini API key
- 旅遊標題
- 城市名稱（自由輸入文字框，見第 6 節 geocoding 流程）
- 家庭成員 1-4（文字輸入，可留空，儲存時過濾空值）

**Tab 結構：**

| Tab | 功能 |
|-----|------|
| 📅 行程 | Day card + 日內活動拖曳排序（沿用 japan-trip.html） |
| 💰 記帳 | 手動新增 + 掃描收據，記錄付款人，不做分帳 |
| 📊 統計 | 分類圓餅圖 + 各成員花費卡片（無結算） |

---

## 2. Firebase 資料結構

沿用 japan-trip.html 結構，`paidBy` 改存成員名稱字串，**移除 `split` 欄位**：

```
/days/{did}
  date: "YYYY-MM-DD"
  label: string
  order: number

/acts/{aid}
  did: string
  cat: string
  name: string
  order: number
  cost: {amt: number, cur: string, paidBy: string} | null   # 無 split 欄位

/expenses/{eid}
  date: "YYYY-MM-DD"
  desc: string
  amt: number
  cur: "JPY" | "AUD" | "USD" | "TWD" | "EUR"
  cat: string
  paidBy: string        # 成員名稱，如 "媽媽"；不再是 p1/p2 enum
  ts: number
```

---

## 3. 收據掃描功能

沿用 japan-trip.html 的 `scanReceipt()` 流程與 Gemini prompt 結構不變（店名/金額/分類/日期），僅將 `currency` 判斷從固定 `"JPY"` 改為讓 Gemini 從收據上辨識幣別代碼（限定回傳 `PRESET_CURRENCIES` 五碼之一），無法辨識時預設 `TWD`；表單預填後仍需使用者確認/微調金額與幣別才送出儲存（沿用現有流程），OCR 失敗時一律靜默降級為空白手動表單，不阻斷記帳流程。

---

## 4. 多人記帳模型（取代分帳模型）

### 資料模型

`CFG.members`：字串陣列，最多 4 個元素，取代 `CFG.p1`/`CFG.p2`。Setup 儲存時過濾空字串，僅保留使用者實際填寫的成員（2-4 人皆可）。

### 付款人選擇器

現有 `pb1`/`pb2` 固定雙鈕、`sp-both`/`sp-p1`/`sp-p2` 分帳選項，改為：
- 依 `CFG.members` 陣列迴圈渲染付款人按鈕（flex-wrap，2-4 個），預設選中成員 1
- **完全移除** split 選擇 UI 與 `curSplit` 變數 — 每筆記錄只記「誰付的」，不記分攤方式
- 記帳表單、活動花費表單皆套用同一套付款人選擇器 component

### 統計頁顯示

**移除**現有 `calcBal()` 與其欠款方向 UI（`bc-settle` 等）。改為「各成員花費卡片」：

```
┌───────────┬───────────┬───────────┬───────────┐
│  爸爸     │  媽媽     │  小明     │  小美     │
│  ¥42,300  │  ¥38,700  │  ¥0       │  €120     │
└───────────┴───────────┴───────────┴───────────┘
```

- 卡片數 = `CFG.members.length`（2-4 張），用可換行 grid 排版，不是固定雙欄 flex
- 計算邏輯：直接依 `paidBy` 加總各幣別金額（`Object.values(exps).filter(e=>e.paidBy===member)`），比現有 `calcPersonSpend` 的均分/自付判斷更簡單，因為沒有 split 語意要處理

---

## 5. 幣別與匯率

固定 5 個 chip：**JPY / AUD / USD / TWD / EUR**，每筆記帳都可自由選擇，Setup 階段不需預選。

匯率抓取沿用現有 lazy 模式並擴展成多幣別版：
- 內部狀態從單一 `exchRate` 變數改為 `exchRates = {JPY: null, AUD: null, USD: null, EUR: null}`（TWD 為本位幣，不需匯率）
- 只在某幣別**實際被用在至少一筆記錄**時才呼叫 `open.er-api.com` 抓該幣別對 TWD 匯率，避免無謂 API 呼叫
- 統計頁圓餅圖的幣別分頁，從現有 `hasJPY/hasTWD` 二元判斷式改為迴圈檢查 `PRESET_CURRENCIES = ['JPY','AUD','USD','EUR','TWD']`，動態產生分頁

---

## 6. 城市與地理定位（新增功能）

Setup 畫面城市欄位改為自由輸入文字框，取代現有寫死的日本城市下拉選單。

**流程：**
1. 使用者輸入城市名稱（如「京都」「Rome」）
2. 存檔時呼叫 `https://geocoding-api.open-meteo.com/v1/search?name=<城市>&count=1&language=zh`
3. 成功：取第一筆結果的 `latitude`/`longitude`/`name`/`country`，存入 `CFG.lat`/`CFG.lng`，並在 Setup 畫面顯示確認文字，如「📍 已定位：岡山市, Japan (34.66, 133.93)」，讓使用者在儲存前確認地點無誤
4. 查無結果：顯示錯誤訊息，**擋下儲存**，要求使用者修改城市名稱重試（避免產生無效座標導致天氣功能整個失效）

天氣功能沿用 Open-Meteo Forecast API，讀取 `CFG.lat`/`CFG.lng`，邏輯不變。

---

## 7. 日內活動拖曳

沿用 japan-trip.html 既有的 `initActDnD()` 邏輯，不需改動（與人數/分帳無關）。

---

## 8. 視覺

- PWA icon：房子／家庭剪影圖案，與情侶版岡山的紅底鳥居區隔
- 主色調：暖橘色系（`--accent:#F97316`）取代岡山版紅色系，維持與雪梨藍、岡山紅不同的辨識度
- 字體沿用 Noto Serif TC（標題）+ Noto Sans TC（內文），與現有 app 一致

---

## 9. 架構決策

- 從 `japan-trip.html` 複製後修改，非從零開始，也非改造共用模組（沿用單一 HTML 檔、無 build step 的既有慣例，符合手機瀏覽器直接開啟 / Netlify 靜態部署的使用情境）
- **移除**：`CFG.p1`/`CFG.p2`、`curSplit`、split 相關 UI（`sp-both`/`sp-p1`/`sp-p2`/`asp-*`）、`calcBal()` 與其 UI、日本城市下拉選單寫死清單、單一幣別假設
- **新增**：`CFG.members[]`、geocoding 查詢與確認流程、多幣別 `exchRates` map、動態付款人選擇器 component、動態成員統計卡片 grid
- Setup localStorage key 改為 `family_trip`，避免與 `japan_trip`／雪梨版 key 衝突
- Firebase databaseURL 沿用「使用者自行輸入、不寫死」模式，同一份模板可反覆用於不同旅行（各自建立獨立 Firebase 專案或路徑）
