# HyRead HTML 筆記匯入按鍵 設計文件

## 背景與目標

目前 HyRead 劃線匯入是手動流程：使用者從 HyRead 匯出 HTML → 本機跑 `parse_hyread_html.py` + `seed_import.py`（需設定 `DATABASE_URL` 連正式環境 Postgres）。目標是在前端加一個匯入按鍵，讓使用者直接上傳 HTML 檔案完成匯入，不用再手動跑 script。

附帶修正一個既有解析瑕疵：目前 `parse_hyread_html.py` 是「一則劃線 = 一張卡片」，導致同一章節標題（`location`）底下有多筆劃線時，會拆成多張內容很短的卡片（見使用者提供的畫面截圖，「時間財富的三大支柱」被拆成 3 張卡片）。改為同一 `location` 底下的多筆劃線合併成一張卡片。

## 範圍

- **合併同標題修正**：只套用在此功能上線後的新匯入，不回頭清理資料庫裡既有的舊資料（已匯入的重複卡片維持現狀）。
- **匯入按鍵**：新增於 `index.html` 書籍列表頁，跟「+ 新增書籍」按鍵並排。

## 架構決策

採用「後端新增匯入端點，重用既有 Python 解析邏輯」，理由：解析邏輯只維護一份（Python），前端只需檔案上傳 UI。

否決方案：
- 前端用 JS 重新實作 HTML 解析 → 解析邏輯要維護兩份（Python script 用於歷史匯入 + JS 用於前端匯入按鍵），容易出現行為不一致。
- 非同步任務佇列（上傳後背景 job + 前端輪詢）→ 檔案通常是單本書的筆記量，同步處理秒級完成，過度設計。

## 變更一：`parse_hyread_html.py` 同標題合併

- 解析時依 `.note-container` 原始順序遍歷，依 `.note-chapter`（`location`）分組；HyRead 匯出檔案中同一章節的 `.note-container` 本來就是連續出現，因此「相鄰即合併」等同「依 location 全域分組」，不需要額外排序或去重章節出現順序的邏輯。
- 同一組內多筆 highlight/note，`content` 依原始順序用空行（`\n\n`）串接。
- 合併後該筆記的 `highlighted_at` 採該組**第一筆**的時間。
- 只影響 `parse_hyread_html()` 的輸出結構，不動 `notes_db.py` 或既有資料。

## 變更二：匯入端點與按鍵

### 後端（`reading-notes-server`）

**新端點** `POST /notes/import/hyread`
- 輸入：`multipart/form-data` 檔案欄位（HTML 檔）+ `X-API-Key` header（沿用既有 `_auth`）
- 邏輯：
  1. 讀取上傳檔案內容為文字，呼叫（合併修正後的）`parse_hyread_html(html)`
  2. 呼叫 `import_hyread_book(parsed)`：
     - 同名書沿用既有書 id（大小寫、去除前後空白比對），非重複則新增書籍
     - 新增筆記前，先查詢該書現有筆記，若有 `content` 與 `highlighted_at` 完全相同者則跳過（新增 `notes_db.note_exists(book_id, content, highlighted_at)`）
  3. 匯入完成後，若該書 `cover_url` 為空，呼叫 `fetch_cover_url(title, author)` 補上封面。單次嘗試，不做 429 重試迴圈；失敗（例外或查無結果）就略過，不影響匯入成功的回應
  4. 回傳 JSON：
     ```json
     {
       "book_id": 12,
       "title": "時間財富",
       "is_new_book": false,
       "notes_imported": 12,
       "notes_skipped_duplicate": 2,
       "cover_fetched": true
     }
     ```
- 錯誤處理：HTML 解析不出 `.book-title`（非 HyRead 匯出格式）時回傳 `400` + 訊息「無法辨識此 HTML 格式，請確認是從 HyRead 匯出的劃線檔案」

### 前端（`reading-notes-app` / `index.html`）

- 在「+ 新增書籍」按鍵旁加「匯入 HyRead 筆記」按鍵，點擊觸發隱藏的 `<input type="file" accept=".html">`
- 選檔後用 `FormData` 上傳到 `${API}/notes/import/hyread`（帶 `X-API-Key`），期間按鍵顯示 loading 狀態（disable + 文字變「匯入中...」）
- 成功：用 alert 顯示摘要，格式類似「《時間財富》匯入完成，新增 12 則筆記，略過 2 則重複，已補上封面」，並重新呼叫 `loadBooks()` 刷新列表
- 失敗：alert 顯示後端回傳的錯誤訊息

## 測試範圍

- `test_parse_hyread_html.py`：新增同 `location` 多筆合併的案例（含合併後 `content` 排列順序、`highlighted_at` 取值）
- `test_notes_db.py`：新增 `note_exists` 的單元測試（完全相同跳過、內容或時間有差異則不跳過）
- `test_notes_api.py`：新增 `/notes/import/hyread` 端點案例——新書匯入、合併既有同名書、重複筆記跳過、非 HyRead 格式回傳 400、封面自動補齊

## 不在範圍內

- 不清理資料庫裡既有的、合併修正上線前就已匯入的重複卡片（截圖中的舊資料維持現狀）。
- 不支援 Notion 來源的前端上傳匯入（Notion 匯入已是一次性歷史匯入，不再維護）。
