# 雪梨旅遊 App 優化設計文件

**日期：** 2026-04-21（最後更新：2026-04-22）
**目標檔案：** `sydney-trip.html`（單一 HTML 檔案 PWA）

---

## 1. 視覺：Header 改版

### 目標
將原本的純色 header 替換為質感照片 + 品牌標題。

### 實作方式
- `<img>` 標籤載入歌劇院照片，`object-fit: cover`，`object-position: center 35%`
- Header 高度維持 168px，`overflow: hidden`
- 疊加漸層遮罩（`linear-gradient`，底部偏暗），確保地標不被遮蓋
- 標題「雪梨之旅」定位於左上角（`top: 16px; left: 18px`），落在天空區域

### 字體
透過 Google Fonts 引入：
- 標題、Day 數字：`Noto Serif TC`（有質感的中文襯線體）
- 內文、chips：`Noto Sans TC`

### 照片來源
`https://www.pelago.com/img/collections/sydney-opera-house/0527-0635_sydney-opera-house.jpg`

---

## 2. 功能：天氣整合

### API
Open-Meteo（免費，無需 API key）
Endpoint：`https://api.open-meteo.com/v1/forecast?latitude=-33.87&longitude=151.21&hourly=temperature_2m,weathercode&timezone=Australia/Sydney&forecast_days=16`

### 實作
新增 `async function fetchWeather()`：
1. fetch Open-Meteo API，取得 `hourly.time` 與 `hourly.temperature_2m`、`hourly.weathercode`
2. 取每天 **12:00** 的資料（index 過濾）
3. 將 `weathercode` 對應至繁體中文描述（晴、多雲、陣雨等）
4. 回傳 `Map<dateStr, { temp, desc }>`，存為模組層級變數 `weatherByDate`

`renderSched()` 呼叫前先 `await fetchWeather()`；若 API 失敗，`weatherByDate` 保持空 Map，day card 不顯示 `wchip`（靜默降級）。

### weathercode 對應表（精簡）
| code | 描述 |
|------|------|
| 0 | ☀️ 晴 |
| 1–3 | ⛅ 多雲 |
| 45,48 | 🌫️ 霧 |
| 51–67 | 🌧️ 有雨 |
| 80–82 | 🌦️ 陣雨 |
| 95–99 | ⛈️ 雷雨 |
| 其他 | ☁️ 陰（fallback） |

---

## 3. 功能：每日總花費

### 實作
新增 `function calcDaySpend(exps, dateStr)`（`dateStr` 格式與 Firebase 儲存一致，為 `"YYYY-MM-DD"`）：
1. 過濾 `exps` 陣列，保留 `date === dateStr` 的記錄
2. 依幣別分組（`AUD`、`TWD`）分別加總
3. 回傳 `Map<currency, total>`，只包含 total > 0 的幣別

### 顯示規則
- 每個有花費的幣別顯示一個 `schip`
- 格式：AUD → `💵 $148 AUD`；TWD → `💴 NT$2,400 TWD`
- 當天無花費記錄 → 不顯示任何 `schip`

### 呼叫時機
在 `renderSched()` 內，渲染每張 day card 時呼叫 `calcDaySpend(exps, day.date)`，結果插入 `.day-meta`。

---

## 4. Day Card 格式

```
Day 1  [4月20日（日）]    ← Noto Serif TC, 日期為藍色小 badge
抵達雪梨                  ← 行程標題（自訂標籤，預設 "Day N" 時不顯示）
[⛅ 21°C 多雲] [💵 $148 AUD]  ← weather chip + spend chip
```

- 移除原有左側數字方塊（`.day-n` HTML 不再渲染，對應 CSS class 可清除）
- 移除「· N 個活動」文字
- `day-num` 以 `Noto Serif TC` 行內顯示「Day 1」
- 行程標題（`.day-dt`）僅在 label 不符合 `/^Day\s*\d+$/i` 時才顯示，避免與 Day N 重複

---

## 5. 功能：圓餅圖分類連動

### 問題
行程頁面儲存活動花費至 `/expenses` 時，category 固定寫死為 `'activity'`，導致住宿、餐飲等在記帳圓餅圖顯示為「活動」。

### 實作
新增 `function mapActCat(actCat)`，將行程活動類型對應至記帳分類：

| 行程類型 | 記帳分類 |
|---------|---------|
| `food` | `food`（餐飲） |
| `transport` | `transport`（交通） |
| `hotel` | `hotel`（住宿） |
| `shopping` | `shopping`（購物） |
| `sight` | `ticket`（門票） |
| `fun` / `beach` / `other` | `activity`（活動） |

`saveAct()` 與 `moveAct()` 寫入 `/expenses` 時，`cat` 欄位改為 `mapActCat(curAC)` / `mapActCat(act.cat)`。

---

## 6. 功能：Day Card 展開狀態保留

### 問題
每次 Firebase 同步或儲存活動後觸發 `renderSched()`，DOM 完全重建，已展開的 day card 會自動收合。

### 實作
`renderSched()` 開頭讀取當前所有 `.day-card.open` 的 `id`，存為 `Set<did>`；`innerHTML` 重建後，再對 Set 內的 did 恢復 `.open` class。

---

## 7. 視覺：PWA Icon

### 來源
使用 Vexels 手繪歌劇院插圖（無文字版本）：
`https://images.vexels.com/media/users/3/181823/isolated/preview/e0da54bc315043a7c7a634bf9b4049e7-the-sydney-opera-house-hand-drawn.png`

### 實作
以 JS 於 canvas 繪製淺藍漸層底（`#D6EEF8` → `#EEF7FC`，圓角 96px）後疊加上述圖片（padding 4%），轉為 `data:image/png` 設為 `<link rel="icon">` 與 `<link rel="apple-touch-icon">`。CORS 失敗時降級為直接使用圖片 URL。

---

## 8. 架構決策

- **單一 HTML 檔案**，不拆分模組
- 新增獨立 function：`fetchWeather()`、`calcDaySpend()`、`mapActCat()`
- 天氣資料在 app 初始化時一次性 fetch，不在每次渲染重複呼叫
- 現有 Firebase 同步、拖拉排序、圓餅圖邏輯不動
