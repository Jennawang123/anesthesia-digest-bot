# 讀書筆記彙整 App 設計文件

## 背景與目標

使用者用 HyRead 電子書閱讀器讀書並劃線，過去的讀書心得則整理在 Notion「閱讀清單」資料庫（每本書一頁，內文為分主題整理過的心得，而非逐句摘句）。目標是建立一個 app，把兩個來源的筆記彙整到同一個地方，可依書瀏覽、全文搜尋，並支援之後每讀完一本新書時匯入新的劃線。

Notion 之後不再作為筆記維護地點，僅做一次性歷史匯入；未來新內容全部進新 app。

## 架構

- **前端**：單一 HTML 檔案 PWA，沿用 `japan-trip.html` / `finance-app/index.html` 的模式，部署於 Netlify。
- **後端**：新 repo（暫名 `reading-notes-server`），FastAPI + SQLite，結構沿用 `finance-server`（`main.py` 掛載路由與靜態檔、`xxx_api.py` 放路由邏輯、`xxx_db.py` 放資料庫存取），部署於 Railway。
- 前端透過 REST API 讀寫後端資料，資料集中存於 SQLite，達成跨裝置同步（手機/電腦看到同一份資料）。

## 資料模型

```
Book
  id
  title
  author            (可空)
  category          (多選；沿用 Notion「種類」選項：房地產/投資理財/心靈成長/能力培養，可擴充新分類)
  started_at        (可空)
  finished_at       (可空)
  source_tag        (hyread | notion | manual — 該書筆記的主要來源，供顯示用)

Note   (統一的「筆記卡片」格式，不分來源使用不同結構)
  id
  book_id           (外鍵 → Book)
  content           (文字內容，卡片主體；若 HyRead 該則劃線有附加個人註解，附加在劃線原文下方，同一欄位)
  source            (hyread | notion | manual)
  location          (章節/小節標題；僅 hyread 來源會有值，可空)
  highlighted_at    (劃線或建立時間，可空)
  created_at
  updated_at
```

**卡片粒度規則**：
- HyRead 劃線：一句/一段劃線 = 一張卡片。
- Notion 心得：原文以 Markdown 標題（`#`）分段，匯入時依標題切成多張卡片，而非整頁塞成一條，確保跟 HyRead 卡片有一致的瀏覽與搜尋顆粒度。
- 手動新增：使用者自行決定一張卡片的內容範圍。

## 匯入管線（一次性歷史匯入 + 之後每本新書手動觸發，不做成 app 內建 UI 功能）

1. **HyRead → HTML 匯出**：
   - HyRead 可直接將劃線內容匯出成 HTML（不需經過 Evernote）。
   - 匯出的 HTML 結構固定：
     - `.book-title`：書名
     - `.book-data`：作者/譯者/出版社（單一字串，格式如「作者．著;譯者．譯．出版社．」）
     - `.book-cover img[src]`：封面圖網址
     - 每則劃線是一個 `.note-container`，內含：
       - `.note-chapter`：章節/小節標題 → 對應 `Note.location`
       - `.note-time`：劃線時間，格式 `YYYY/M/D H:MM` → 對應 `Note.highlighted_at`
       - `.highlight-content-*`（`*` 為 red/yellow/green/gray，代表劃線顏色，本次不保留顏色資訊）：劃線原文 → 對應 `Note.content`
       - `.note-text`：使用者額外寫的個人註解，可能為空。若非空，附加在 `Note.content` 劃線原文下方（同一欄位，不拆兩張卡片）
   - 寫一支獨立 Python parser script（用 BeautifulSoup），解析 HTML，輸出 seed JSON，再寫入 SQLite。
   - 未來讀完一本新書後，重複同樣流程：從 HyRead 匯出新書的 HTML → 重跑 script → 匯入新書的卡片。這是手動觸發的批次流程，不需要 app 內建上傳介面。

2. **Notion 歷史筆記（一次性）**：
   - 透過 Notion MCP 工具讀取「閱讀清單」資料庫（`書名`、`種類`、`開始閱讀日`、`完成閱讀日`）與每本書頁面的內文。
   - 內文依 Markdown 標題切分為多張卡片（見上方粒度規則），`source` 標記為 `notion`。
   - 一次性轉成 seed JSON 並匯入 SQLite。完成後 Notion 端不再讀取或同步。

## MVP 功能範圍

- 書籍列表頁：可依分類（種類）篩選。
- 書籍詳細頁：列出該書所有筆記卡片，依來源顯示標籤（HyRead / Notion / 手動）。
- 全文搜尋：跨書、跨卡片內容搜尋。
- 手動新增 / 編輯 / 刪除筆記卡片。

## 不在 MVP 範圍（v2 待辦）

- 隨機回顧模式（隨機抽過去的劃線/心得重新溫習）。
- 間隔重複提醒（spaced repetition）。

這兩項待 MVP 上線並實際使用後，再視需求評估設計與排入下一輪開發。

## 待確認的實作細節（留給 writing-plans 階段處理）

- Notion 匯入 script 的具體執行方式（一次性腳本或由 Claude 直接呼叫 MCP 工具產生 seed JSON）。
