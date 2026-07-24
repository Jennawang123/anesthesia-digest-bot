# Nasr 第二版圖表抽取並插入小兒心臟學筆記 — 設計

日期：2026-07-24
狀態：設計完成，待實作

## 目標

把 Nasr《The Pediatric Cardiac Anesthesia Handbook》第二版（2024, Wiley Blackwell）的 140 張 Figure 抽成圖檔，上傳到 Notion，插入「小兒心臟學讀書會（Park's + Pediatric Congenital Cardiology）」系列既有筆記。

來源 PDF：`~/Desktop/pediatric cardiac handbook TEE.pdf`（360 頁，37 章，Part I Basics 1–11 + Part II Specific Lesions 12–37）

前一輪 Miller 圖表回填的設計見 `2026-07-21-notion-figure-extraction-design.md`，該文件結尾寫明「不處理 Park's 小兒心臟系列，抽圖腳本與書本無關，日後可直接對其 PDF 重跑」。實測結果推翻了「直接重跑」這個假設，理由見下節。

## 與 Miller 的結構差異（實測）

| 項目 | Miller | Nasr ed2 |
|---|---|---|
| 版面 | 612×783，左右雙欄 | 480.5×720，左右雙欄 |
| 向量繪圖物件 | 每頁數千（Ch28 全章零內嵌圖） | **全書 0 個** |
| 圖的形式 | 純向量線稿／上千碎塊 raster | **全部為完整內嵌 raster** |
| caption 編號 | `Fig. 28.3`（點號） | `Figure 8.1` |
| caption 位置 | 圖下方 | **圖下方**或**旁欄同高** |
| Notion 對應依據 | sub-page 標頭的書本頁碼區間 | **章號→病灶頁對照表** |

三點結論：

1. **Miller 的 `figure_rect()`（從 caption 往上找內文邊界）不適用。** 旁欄 caption 的正上方是內文，往上裁會裁出內文或空白。
2. **可以改用 raster 圖框直接裁切。** 全書向量物件為 0，`get_image_rects()` 取得的框就是圖本身的邊界，比任何幾何啟發式都準確，也不需要 Miller 那套「內文字體門檻」判斷。
3. **頁碼區間比對不適用。** Park's 系列是 lesion-based 頁面，標頭來源行混列 Park's / Nasr / da Cruz / Miller 四本書，沒有單一可比對的頁碼區間。

### caption 與 raster 的配對實測（全書 140 張）

| 情形 | 頁數 |
|---|---|
| 1 caption ↔ 1 raster | 48 |
| 1 caption ↔ 多 raster（multi-panel，需聯集） | 34 |
| 2–3 caption 同頁（需分派） | 22 |
| caption 所在頁**無** raster（圖在鄰頁） | 6 |

無 raster 的 6 張：Fig 7.2、8.1、11.1、11.2、11.4、11.5、11.9。

## 範圍決策

- **只做 Nasr 第二版**。Park's Handbook 的圖不在本輪，日後想補再單獨跑一輪。
- **只抽 `Figure`**。Table 維持現行做法重建成 Notion table block（可搜尋、可編輯），Box 為純文字不圖片化。與 Miller 一致。
- **既有內容全部保留**，只做插入。這點對本系列比 Miller 更關鍵：使用者自行貼在頁面上的圖是 S3 presigned URL，任何整頁重寫都會使其失效。
- **不跳過使用者已自行貼圖的頁面**。腳本照插，重複的由使用者在 Notion 自行刪除。理由是無法判斷既有 image block 是否為同一張圖，跳過會讓真正該補的圖被漏掉；漏插比多插難發現。
- **圖插在「一、內文筆記」對應小標末尾**，歸屬不明確的落回「二、圖表」。與 Miller 一致。
- 圖片以 Notion File Upload API 上傳，存在 Notion 內部，不用外部 URL。

## 架構

```
Nasr ed2 PDF ──▶ ① extract_figures_raster.py ──▶ figures/nasr/*.png
   （無網路、無 token）                          ├─ manifest.json
                                                └─ contact_sheet.html  ← 使用者驗收
manifest.json ──▶ ② map_nasr_figures.py ──▶ manifest.json（補 target_page_id）
   （讀對照表，不連網）
manifest.json ──▶ ③ upload_figures.py ──▶ Notion（上傳 + 插入 image block）
   （沿用 Miller 現成腳本，不修改）
```

**新開 `extract_figures_raster.py`，不改寫 `extract_figures.py`。** Miller 那套的 caption-往上裁邏輯還要服務 miller_queue 的 Tier 3 章節，兩本書的版面前提相反（向量為主 vs raster 為主），共用一份會互相汙染。

### ① extract_figures_raster.py

- 掃描每頁 text block，以 `^Figure\s*(\d+)\.(\d+)` 取得 caption 及其 rect。
- 取每頁 raster 圖框（`get_image_rects()`），濾除：
  - 寬 >440 且高 >640 的整頁背景層（每頁固定兩張）
  - 寬或高 <20pt 的碎塊
- caption↔raster 配對，兩種幾何各判一次：
  - **圖下方**：raster 在 caption 上方，水平重疊 >30% caption 寬，取垂直距離最近者
  - **旁欄同高**：raster 與 caption 垂直重疊 >30%，水平不重疊且位於相鄰欄
- 同一 caption 配到多個 rect 取聯集（multi-panel 圖）。聯集後寬或高超過版心 1.2 倍標 `oversized_union`。
- caption 所在頁無 raster 時，往前一頁與後一頁各找一次；仍無則標 `no_raster`，不產圖，僅列入 contact sheet。
- `page.get_pixmap(clip=rect, dpi=200)` 輸出 PNG，四周留 PAD 6pt。
- Contact sheet 為單一 HTML，縮圖牆排列全部圖，標註 fig_id、PDF 頁碼、書本頁碼、caption、suspect 旗標。

### ② map_nasr_figures.py

讀 `nasr_ed2_figure_map.json`（章號→Notion page id），依 manifest 每張圖的 `nasr_chapter` 填入 `target_page_id`。純本地查表，不連 Notion。

兩章需逐圖分派，對照表中標為 `split`，由人工（Claude 讀圖說）指定：

- **Ch27 Transposition of the Great Arteries**（7 張）→ D-TGA 頁／L-TGA 頁
- **Ch35 ALCAPA and AAOCA**（5 張）→ ALCAPA 頁／AAOCA 頁

`target_section`（頁內小節）同樣由 Claude 讀圖說與該頁小節大綱填入，等同 Miller 流程中 `set_sections.py` 的角色。

### ③ upload_figures.py

沿用不修改。既有行為：

- Notion File Upload API 兩步（建立 upload → 上傳檔案）。
- 依 `target_section` 找到小節，於小節最後一個 block 之後插入 image block，caption 帶原文圖說 + 書本頁碼。找不到小節退回「二、圖表」heading，該 heading 不存在則建立。
- 插入後重新列出頁面、以圖說比對取得 block id 寫回 `uploaded_block_id`。不可直接用 PATCH 回傳（實測回傳筆數與實際插入數不符）。
- 小節偵測同時認 `heading_3` 與整行粗體 paragraph。

### manifest.json 欄位

沿用 Miller 那份，新增 `nasr_chapter`：

```json
{
  "fig_id": "8.3",
  "nasr_chapter": 8,
  "pdf_page": 100,
  "book_page": 87,
  "caption": "Figure 8.3 Midesophageal four-chamber view…",
  "png": "fig-8-03_p100.png",
  "bbox": [54, 73, 445, 320],
  "panels": 3,
  "suspect": [],
  "include": true,
  "target_page_id": "3a4e77f4-b1f0-8137-8413-d0fcd88b23f6",
  "target_section": null,
  "uploaded_block_id": null
}
```

## 章號→Notion 頁對照表

35 個有圖的章，合計 140 張。Ch3（術前評估）與 Ch34（Heart-Lung/Lung Transplantation）在書中無 Figure。

### Part I Basics（掛 Ch0 母頁下，57 張）

| Nasr ed2 章 | 圖 | Notion 頁 | page id |
|---|---|---|---|
| 1 Cardiovascular Development | 1 | 正常心臟解剖 | 3a1e77f4-b1f0-81d1-bcab-c92324b4098a |
| 2 Important Concepts in CHD | 6 | 4 types of lesion ⚠️ | 3a1e77f4-b1f0-813d-9432-dc883d83a125 |
| 4 Intraoperative Management | 1 | 術中管理 | 3a2e77f4-b1f0-810b-aa94-f7ed16a667c9 |
| 5 Developmental Hemostasis & PBM | 3 | Developmental Hemostasis 與 PBM | 3a4e77f4-b1f0-81e6-952c-f3e263f5dfb2 |
| 6 Cardiac Catheterization Data | 5 | 心導管數據判讀 | 3a2e77f4-b1f0-8120-9461-f9fba4666931 |
| 7 Cardiopulmonary Bypass | 9 | 體外循環 | 3a2e77f4-b1f0-81bc-a7ce-f41fdec3abcf |
| 8 Echocardiography | 12 | Echocardiography（TEE 完整切面） | 3a4e77f4-b1f0-8137-8413-d0fcd88b23f6 |
| 9 Risk Scoring Systems | 1 | Risk Scoring Systems | 3a4e77f4-b1f0-8172-be57-f184937d24d3 |
| 10 Mechanical Circulatory Support | 10 | 機械輔助裝置（ECMO/VAD） | 3a2e77f4-b1f0-81ab-ad38-dac1a21a9d8d |
| 11 Postoperative CICU Care | 9 | Postoperative CICU Care | 3a4e77f4-b1f0-81e1-b6cd-ce08ac9c7721 |

### Part II Specific Lesions（83 張）

| Nasr ed2 章 | 圖 | Notion 頁 | page id |
|---|---|---|---|
| 12 Patent Ductus Arteriosus | 1 | PDA | 3a1e77f4-b1f0-817a-9aea-e8105c704aab |
| 13 Aortopulmonary Window | 1 | Ch12 AP Window | 3a2e77f4-b1f0-81e0-be2d-e0a5a040fd3c |
| 14 Coarctation of the Aorta | 4 | CoA | 3a1e77f4-b1f0-818f-b6d1-eef636346de0 |
| 15 Atrial Septal Defect | 4 | ASD | 3a1e77f4-b1f0-81a6-bded-f7e00e25be07 |
| 16 Ventricular Septal Defect | 2 | VSD | 3a1e77f4-b1f0-8123-9ff5-f3933527d0a4 |
| 17 Atrioventricular Canal Defects | 4 | AVSD | 3a1e77f4-b1f0-813a-be7d-deeb67c9da57 |
| 18 Double Outlet Right Ventricle | 4 | Ch10 DORV ⚠️ | 3a2e77f4-b1f0-8180-99d4-c4c97d7174e8 |
| 19 Truncus Arteriosus | 3 | Ch9 Truncus Arteriosus | 3a1e77f4-b1f0-814e-9174-d7b5c83e3f4d |
| 20 TAPVR | 2 | Ch5 TAPVR（實質內容在子頁） | 3a1e77f4-b1f0-8106-9bf9-fb4c53591116 |
| 21 LVOTO | 2 | AS | 3a1e77f4-b1f0-819a-94b1-e24d5843ac59 |
| 22 Mitral Valve | 2 | Ch13 Mitral Valve Disease | 3a2e77f4-b1f0-81b4-908a-c28b8446c577 |
| 23 PA-IVS | 2 | PA-IVS | 3a1e77f4-b1f0-81ae-b9ca-f4a556ce9acc |
| 24 Tetralogy of Fallot | 4 | TOF（典型） | 3a1e77f4-b1f0-813b-9c0d-d47118f84f2a |
| 25 TOF with Pulmonary Atresia | 1 | TOF+PA | 3a1e77f4-b1f0-8182-95f6-cd7f157d9121 |
| 26 TOF with Absent Pulmonary Valve | 1 | TOF+AbsentPV | 3a1e77f4-b1f0-81f0-8c78-f4344af60ede |
| 27 Transposition of the Great Arteries | 7 | **split** D-TGA / L-TGA | 3a1e77f4-b1f0-8199-8de5-ceaab9cbdcb6 / 3a1e77f4-b1f0-8119-83b1-d050c09cd9d4 |
| 28 Single-ventricle Lesions | 9 | Ch18 單心室統整框架 | 3a2e77f4-b1f0-81db-9617-da0fa9331937 |
| 29 Hypoplastic Left Heart Syndrome | 2 | HLHS 解剖生理手術路徑 ⚠️ | 3a1e77f4-b1f0-8183-a5e0-c7b24a4598b0 |
| 30 Interrupted Aortic Arch | 5 | IAA | 3a1e77f4-b1f0-81fe-bd7c-de2ed0e8752f |
| 31 Vascular Rings | 6 | Ch14 Vascular Rings | 3a2e77f4-b1f0-8168-a60b-cf115b99d028 |
| 32 Tricuspid Atresia | 3 | Tricuspid Atresia | 3a1e77f4-b1f0-819a-b927-cca2b6e179d9 |
| 33 Heart Transplantation | 3 | Ch16 Heart Transplantation | 3a2e77f4-b1f0-8120-8561-ee025c67e349 |
| 35 ALCAPA and AAOCA | 5 | **split** ALCAPA / AAOCA | 3a2e77f4-b1f0-81dd-a717-fe812b1b51b5 / 3a4e77f4-b1f0-8178-8929-f86b05412845 |
| 36 Heterotaxy | 3 | Ch15 Heterotaxy | 3a2e77f4-b1f0-8119-9ca8-f6ae27030695 |
| 37 Ebstein Anomaly | 3 | Ebstein Anomaly 詳細筆記 | 3a1e77f4-b1f0-8148-afc4-c64ef74032d9 |

⚠️ 標記為記憶檔中已知使用者自行加過圖片／表格的頁面。依範圍決策照插不跳過。

**Notion 有頁但 Nasr 無對應章**（本輪不會有圖進入）：PS、Coronary Artery Fistula、Ch17 Heart-Lung and Lung Transplantation、各章母頁、Ch0 母頁、總論、術前評估。

## 認證

沿用 Miller 的 Notion internal integration，capabilities 含 Read / Update / Insert content，token 存於 `Jenna_agent/.env` 的 `NOTION_TOKEN`（`.env` 已在 `.gitignore`）。

前置作業：需將「小兒心臟學讀書會」母頁分享給該 integration，子頁繼承。**2026-07-24 已由使用者完成並實測驗證**（母頁、TEE 頁、TOF 典型、Ch18 單心室、ALCAPA 五個抽樣頁皆可讀取）。此前該 integration 只被分享過 Miller 的頁，對本系列一律回 404 object_not_found。

## 錯誤處理與可逆性

- **只做插入，不刪除或改寫既有內容。** 本系列頁面含使用者自行上傳的 S3 presigned URL 圖片，整頁重寫會使其失效。全程只用 append，不碰 `replace_content`。最壞情況是多出一張裁切錯誤的圖，刪除該 block 即回復原狀。
- 裁切錯誤在 contact sheet 階段攔下，不會進到 Notion。
- `no_raster`（6 張）不產圖，列在 contact sheet 供人工決定是否手動補。
- `oversized_union` 在縮圖牆以紅字標示。
- `uploaded_block_id` 防止分批執行時重複插圖。

## 驗收方式

先只做 **Ch8 Echocardiography** 一章 12 張。選它的理由：TEE 切面圖多為 multi-panel，是聯集邏輯最容易出錯的一章；且 Fig 8.1 正好是 `no_raster` 案例，兩種失敗模式一次驗證。

驗收由使用者對成果判斷，不對架構判斷：

1. Contact sheet 縮圖牆 — 裁切是否完整、哪幾張不需要。
2. Notion 頁面實際插入位置。

Ch8 品質確認後，才推展其餘 34 章；屆時再決定一次跑完或分批。

## 明確排除

- 不抽 Table 與 Box。
- 不處理 Park's Handbook 的圖。
- 不修改 `extract_figures.py`（Miller 專用）與 `upload_figures.py`。
- 不處理 Notion 有頁但 Nasr 無對應章的頁面。
- 不建向量檢索層。與 Miller 那輪的決策一致。
