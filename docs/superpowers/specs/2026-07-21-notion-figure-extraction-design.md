# 教科書圖表抽取並插入 Notion 筆記 — 設計

日期：2026-07-21
狀態：已核准，Ch28 試作中

## 目標

把 Miller's Anesthesia PDF 各章的 figure 抽成圖檔，上傳到 Notion，插入既有章節筆記的「二、圖表」區塊。首要範圍是回填**已完成的 13 章**；佇列中 7 章 pending 暫停，不在本次範圍。

## 背景與關鍵限制

發想來源是 GitHub repo `drpwchen/textbook-to-note`。評估結論：不導入該 repo，只取「圖表抽取」這個點子。理由是它的第一階段依賴 `page.get_text()`，與現行 Miller 筆記流程明文規定的視覺法（PyMuPDF 渲染 PNG → Read 讀圖，禁用 `get_text()`）衝突；其向量檢索層的價值要等跨書查詢需求出現才成立。

實測三章 PDF 的內部結構：

| 章 | 頁數 | 內嵌 raster 圖 | 向量繪圖物件 |
|---|---|---|---|
| Ch28 術前評估 | 78 | 0 | 1272 |
| Ch41 脊椎麻醉 | 48 | 22 | 5572 |
| Ch13 心臟生理 | 22 | 1740 | 9247 |

**因此不可用 `page.get_images()` 逐張抽取內嵌圖片。** Ch28 的圖全是向量線稿（零內嵌圖片），Ch13 則是一張圖被切成上千個碎塊。唯一對三種情況都成立的做法是**依 caption 定位圖的範圍，整塊區域高解析度渲染**。

Caption 偵測已實測可行（Ch41 樣本）：

```
p1  rect=(315,439,551,466)  Fig. 41.1  Spinal cord anatomy. Notice the termination…
p17 rect=(51,689,551,743)   Fig. 41.6  Vertebral anatomy of the midline and paramedian…
p19 rect=(315,57,480,69)    Box 41.1  Modified Bromage Scale
```

編號格式為 `Fig. 41.1`（點號），caption 為獨立 text block。頁面 612×783，左欄 x≈51–290、右欄 x≈315–563、跨欄圖 x≈51–551。Caption 文字含 soft hyphen（U+00AD），需清除。

## 範圍決策

- **只抽 `Fig.`**。Table 維持現行做法重建成 Notion table block（可搜尋、可編輯）；Box 為純文字清單，不圖片化。
- **回填已完成 13 章**；pending 7 章暫停。
- **既有文字摘要與表格全部保留**，圖插在其上方，不刪除任何既有內容。理由為風險不對稱：文字可被 Notion 搜尋、圖片不能，且刪除不可復原。
- 圖片以 Notion File Upload API 上傳，**存在 Notion 內部**，不用外部 URL，避免來源失效造成破圖。

## 架構

三個獨立腳本，每一步的產出可在進入下一步前檢查：

```
Miller PDF ──▶ ① extract_figures.py ──▶ figures/ch28/*.png
   （無網路、無 token）                 ├─ manifest.json
                                       └─ contact_sheet.html  ← 使用者驗收
manifest.json ──▶ ② map_figures.py ──▶ manifest.json（補 target_page_id）
   （讀 Notion，只讀不寫）              ← Claude 審閱，標記 include
manifest.json ──▶ ③ upload_figures.py ──▶ Notion（上傳 + 插入 image block）
```

### ① extract_figures.py

輸入章節 PDF，輸出 PNG、manifest、contact sheet。純本地確定性運算。

- 掃描每頁 text block，以 regex 比對 `^Fig\.\s*\d+[.-]\d+` 取得 caption block 及其 rect。
- 依 caption x 範圍判定欄位：跨欄（寬度 > 0.7 × 版心寬）或單欄（左／右）。
- 圖的範圍 = caption 正上方、同欄寬，往上延伸到最近的**內文** text block 底部。判定內文的門檻：字元數 ≥ 25 且寬度 ≥ 該欄寬的 30%；不符者視為圖內標籤（如 (A)、(B)、解剖標註），略過不作為邊界。
- 上界夾在頁面上緣頁邊距。
- `page.get_pixmap(clip=rect, dpi=200)` 渲染輸出 PNG。
- Contact sheet 為單一 HTML 檔，縮圖牆排列全章圖，每張標註 fig_id、PDF 頁碼、caption。

### ② map_figures.py

- 讀該章 Notion 章節頁的 sub-page 清單。
- 解析每篇 sub-page 標頭引言：`Miller's Anesthesia 10th ed. Ch 28 — Preoperative Evaluation, pp. 820–833（PDF pp. 12–20）`，取出 PDF 頁碼區間。
- 依圖的 PDF 頁碼指派 `target_page_id`。落在區間外或跨區間者留空，由 Claude 人工指派。
- 只讀不寫。

### ③ upload_figures.py

- 對 `include: true` 且 `uploaded_block_id` 為 null 的圖：Notion File Upload API 三步（建立 upload → 上傳檔案 → 取得 file_upload id）。
- 在目標 sub-page 找到「二、圖表」heading block，於其後插入 image block，caption 帶原文圖說 + 書本頁碼。該 heading 不存在時建立之。
- 寫回 `uploaded_block_id`，作為重跑防重複依據。

### manifest.json 欄位

```json
{
  "fig_id": "28.3",
  "pdf_page": 15,
  "book_page": 823,
  "caption": "Fig. 28.3  Revised Cardiac Risk Index…",
  "png": "figures/ch28/fig-28-03.png",
  "bbox": [51, 340, 551, 620],
  "column": "span",
  "include": true,
  "target_page_id": "381e77f4-b1f0-81a9-b466-e0c719d59676",
  "uploaded_block_id": null
}
```

## 認證

Notion internal integration，capabilities 需含 Read / Update / Insert content，並將 Miller 章節 parent page 分享給該 integration（子頁繼承）。Token 存於 `Jenna_agent/.env` 的 `NOTION_TOKEN`；`.env` 已加入 `.gitignore`。

## 錯誤處理與可逆性

- 只做插入，不刪除或改寫既有內容。最壞情況是多出一張裁切錯誤的圖，刪除該 block 即回復原狀。
- 抽圖失敗（裁切邊界錯誤）在 contact sheet 階段被攔下，不會進到 Notion。
- `uploaded_block_id` 防止分批執行時重複插圖。

## 驗收方式

先只做 **Ch28** 一章。Ch28 是最難案例（零內嵌圖片、全向量），失敗資訊量最大。

驗收由使用者對**成果**判斷，不對架構判斷：
1. Contact sheet 縮圖牆 — 裁切是否正確、哪幾張不需要。
2. Notion 頁面實際插入結果。

Ch28 品質確認後，才決定是否推展到其餘 12 章；屆時再為 rollout 寫實作計畫。

## 明確排除

- 不導入 `drpwchen/textbook-to-note`。
- 不建向量檢索層（LanceDB / bge-m3）。跨書語意檢索等實際查詢需求出現再議。
- 不處理 Park's 小兒心臟系列。抽圖腳本與書本無關，日後可直接對其 PDF 重跑。
- 不改動 pending 7 章的筆記流程。
