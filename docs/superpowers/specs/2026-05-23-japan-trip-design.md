# 日本旅遊 App 設計文件

**日期：** 2026-05-23
**目標檔案：** `japan-trip.html`（單一 HTML 檔 PWA）
**基底：** `trip-template.html`

---

## 1. 架構總覽

**技術棧：** 單一 HTML PWA，無後端
- Firebase Realtime Database（資料同步，同雪梨架構）
- Gemini 2.0 Flash API（收據 OCR，按需呼叫）
- Open-Meteo API（天氣，免費無 key）

**Setup 畫面**（首次啟動，存入 `localStorage`）：
- Firebase config（apiKey、databaseURL 等）
- Gemini API key
- 兩位旅伴名稱（`player1Name`、`player2Name`）
- 主要城市（選單，決定天氣座標）

**Tab 結構：**

| Tab | 功能 |
|-----|------|
| 📅 行程 | Day card + 日內活動拖曳排序 |
| 💴 記帳 | 手動新增 + 掃描收據 |
| 📊 統計 | 分類圓餅圖 + 兩人花費總額 |

---

## 2. Firebase 資料結構

沿用雪梨結構，新增 `payer` 欄位：

```
/days/{did}
  date: "YYYY-MM-DD"
  label: "Day 1"
  order: 0

/acts/{aid}
  did: string        # 所屬 day id
  cat: string        # 活動類型
  title: string
  cost: number
  currency: string
  order: number      # 日內排序用

/expenses/{eid}
  date: "YYYY-MM-DD"
  title: string
  amount: number
  currency: "JPY" | "TWD"
  cat: string
  payer: "p1" | "p2" | "shared"   # ← 新增
  ts: number
```

---

## 3. 收據掃描功能

### UI 流程

記帳頁 FAB 展開後顯示兩個選項：
- ✏️ 手動輸入（原有）
- 📷 掃描收據（新增）

點「掃描收據」後：
1. 觸發 `<input type="file" accept="image/*" capture="environment">`
2. 使用者拍照或選圖
3. 圖片轉 base64，呼叫 Gemini 2.0 Flash API
4. 解析回傳 JSON，預填記帳表單
5. 使用者確認／微調後送出儲存

### Gemini Prompt 設計

```
你是日本收據辨識助手。請分析這張收據圖片，回傳以下 JSON（只回傳 JSON，不加任何說明）：
{
  "store": "店名（若看不清則填空字串）",
  "amount": 金額數字（日圓整數，若有外税請加總後回傳含税總額）,
  "currency": "JPY",
  "category": "food|transport|hotel|shopping|ticket|activity",
  "date": "YYYY-MM-DD（若看不清則填今天日期）"
}
注意：日本收據常見外税(8%/10%)與内税，請確認取含税最終金額。
```

### Gemini API 呼叫

```javascript
async function scanReceipt(base64Image) {
  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${geminiKey}`,
    {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        contents: [{parts: [
          {text: RECEIPT_PROMPT},
          {inline_data: {mime_type: 'image/jpeg', data: base64Image}}
        ]}]
      })
    }
  );
  const json = await res.json();
  return JSON.parse(json.candidates[0].content.parts[0].text);
}
```

API 失敗或 JSON 解析失敗 → 靜默降級，開啟空白手動表單。

---

## 4. 兩人分帳模型

### payer 欄位語意

| 值 | 意義 | 統計計算 |
|----|------|---------|
| `"p1"` | 旅伴 1 付 | 全額計入 p1 |
| `"p2"` | 旅伴 2 付 | 全額計入 p2 |
| `"shared"` | 共同平分 | 各計入一半 |

### 統計頁顯示

圓餅圖（分類）維持不變，下方新增兩人花費卡片：

```
┌─────────────────┬─────────────────┐
│  Jenna          │  小明           │
│  ¥42,300        │  ¥38,700        │
│  NT$2,400       │  NT$0           │
└─────────────────┴─────────────────┘
```

計算邏輯：`calcPersonSpend(exps, 'p1')` / `calcPersonSpend(exps, 'p2')`
- 依幣別分組加總
- `shared` 記錄各取一半

---

## 5. 日內活動拖曳

雪梨 app 支援 day 層級拖曳（跨日調整順序）。新增 act 層級拖曳（同一天內調整活動順序）：

- 每個活動列左側加拖曳把手（`⠿`，touch-action: none）
- 事件：`dragstart` / `dragover` / `drop`（同雪梨 day 拖曳實作，層級降至 act）
- 放開後更新 Firebase `/acts/{id}/order`
- `renderSched()` 依 `order` 欄位排序活動（ASC）

---

## 6. 天氣整合

Open-Meteo 座標依 Setup 選擇的城市：

| 城市 | 緯度 | 經度 |
|------|------|------|
| 東京 | 35.68 | 139.69 |
| 大阪 | 34.69 | 135.50 |
| 京都 | 35.01 | 135.77 |
| 札幌 | 43.06 | 141.35 |
| 福岡 | 33.59 | 130.40 |

Timezone：`Asia/Tokyo`
取每天 12:00 資料，weathercode 對應表同雪梨。

---

## 7. 視覺

- Header 照片：日本風景（富士山或京都）
- 色調：沿用雪梨藍色系（`--blue:#0077B6`）
- 字體：Noto Serif TC（標題）+ Noto Sans TC（內文），同雪梨
- PWA icon：以 canvas 繪製日本主題（富士山或鳥居剪影）

---

## 8. 架構決策

- 單一 HTML 檔，不拆分模組
- 新增獨立 function：`scanReceipt()`、`calcPersonSpend()`
- Gemini 僅在使用者主動觸發掃描時呼叫，不影響其他功能效能
- Setup localStorage key 前綴改為 `japan_` 避免與雪梨 app 衝突
- 天氣資料 app 初始化時一次性 fetch，不在每次渲染重複呼叫
