# Nasr 第二版圖表抽取並插入小兒心臟學筆記 — 設計

日期：2026-07-24
狀態：✅ 2026-07-24 完成，139 張已上傳至 37 個 Notion 頁

## 目標

把 Nasr《The Pediatric Cardiac Anesthesia Handbook》第二版（2024, Wiley Blackwell）的 145 張 Figure 抽成圖檔，上傳到 Notion，插入「小兒心臟學讀書會（Park's + Pediatric Congenital Cardiology）」系列既有筆記。

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

### caption 的辨識

以 `^Figure\s*(\d+)\.(\d+)` 比對 text block 開頭，並沿用 Miller 的 `is_body` 字體過濾——內文交叉引用用的是內文字體（TimesNewRomanPSMT 10pt），真正的圖說不是。實測全書 140 個字面命中中，1 個為內文交叉引用（idx98 的「Figure 8.1. Figures 8.2-8.9 summarize the images obtained during a comprehensive TTE exam.」，真正的 Fig 8.1 圖說在 idx99），過濾後得 **139 張，零誤判**（各章編號連續、無重複）。

### 範圍圖說（一個圖說涵蓋連號多張）

Ch8 的 28-view comprehensive TEE exam 圖譜用的是複數形範圍圖說「Figures 8.12–8.17 The 28 views included in a comprehensive TEE exam」，橫跨 idx105–110 共 6 頁，每頁是表格的一段（Imaging plane / 3D model / 2D TEE image / Acquisition protocol / Structures imaged），**該圖說在每一頁底部都重複印一次**。

`CAPTION_RE` 不會命中複數形，所以這 6 個圖號原本整組漏掉——這正是使用者最重視的 TEE 內容，且 Notion 頁上早有對應小節「Comprehensive TEE Exam：28 views（Fig 8.12–8.17，ASE 2019 Puchalski）」。2026-07-24 使用者決定納入，做法為**一頁一張**（6 頁對 6 個圖號，保留每列「圖↔探頭角度↔結構」的對照關係）。

處理方式：`RANGE_CAPTION_RE` 另外比對，全書蒐集後依 (章, 起, 迄) 分組，把出現過的頁面排序後依序給連號圖號。**必須先分組再展開**，否則 6 頁各自展開一整組會得到 36 筆。裁切用 `atlas_crop()`：取「非內文字體的 text block」與 raster 的聯集，藉此排除頁眉、圖說本身、與混在頁尾的章節內文（idx107 表格下方就接著內文）。標記 `atlas_page`。

因此全書總數為 **145 張**（139 單張 + 6 圖譜頁），預設納入 139（6 張 `geometric_fallback` 除外）。

**已知缺口：Ch6 的 Fig 6.2 與 6.3 在文字層沒有 caption block**（內文有「Figure 6.2」引用，但圖說本身抓不到，推測已烙進圖檔）。這兩張無法自動抽取，列為人工處理項目，不影響其餘 139 張。

### 書本頁碼

頁眉有兩種寫法：偶數頁「10 The Pediatric Cardiac Anesthesia Handbook」（頁碼在前）、奇數頁「Cardiovascular Development 5」（頁碼在後）。取首個 text block（限 y < 60）的頭尾 token，1–3 位數字即書本頁碼。340 頁中 327 頁適用，其餘為整頁圖或章首頁。

14 張圖所在頁取不到頁碼，以**章內位移**回填：實測每章的 `pdf_page − book_page` 唯一且恆定（Ch1 +16 遞減至 Ch37 −3，因 Part 分隔頁而逐章漂移），故不可全書套單一公式，必須逐章計算。

### caption 與 raster 的配對實測（全書 139 張）

配對規則以整份 PDF 實跑驗證，最終為：

- **下方型**：raster 在 caption 上方，水平重疊 > 兩者**較窄**一方寬度的 30%，且垂直間隙 < 0.6 × 頁高。
- **旁欄型**：raster 與 caption 垂直重疊 > 較矮一方高度的 30%，且水平不重疊。
- 每個 raster 只歸給距離最近的 caption（同頁有 2–3 個圖說的有 22 頁）。

重疊門檻必須相對於「較窄一方」，這點踩過兩次：改成相對 caption 寬度時，Fig 15.1 的 6 個 panel（各寬 59–73pt）全數落空；改成要求 raster 落在 caption 跨距內時，換成寬圖配窄圖說的 Fig 9.1、12.1、27.7、31.6 落空。

| 結果 | 張數 |
|---|---|
| raster 配對成功 | 133 |
| 該頁無可用 raster，需幾何 fallback | 6 |
| 配對失敗 | 0 |

多 panel 分布：1 panel 93 張、2 panel 20 張、3–8 panel 20 張（最多 8 panel）。聯集後無任何一張超過頁高 75%，`oversized_union` 實測未觸發。

### 幾何 fallback（推翻先前的排除決定）

Fig 7.2、7.3、11.2、11.4、11.5、11.9 這 6 張所在頁沒有任何可用 raster——它們被烙進整頁尺寸的背景掃描層，無法用圖框隔離。

原先的決定是「不做幾何 fallback，6 張手動處理更快」。實測推翻了前半段但也推翻了後半段的樂觀：重用 `extract_figures.figure_rect()` + `detect_columns()` 只要十餘行就能對這 6 張產出裁切，**但品質不可信**——實測 Fig 11.4 裁出的是整張 State Behavioral Scale 表格加上頁眉，右側還被切掉（Nasr 的欄位偵測在 480pt 窄版面本來就不準）。

結論是兩者都不取，改採第三種：**產出裁切，但標記 `geometric_fallback` 且 `include: false`**。這 6 張會出現在 contact sheet 上供檢視，預設不會進 Notion，使用者認可哪張才把 `include` 改為 `true`。安靜地成功並送出垃圾，比失敗更糟。

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
- 圖說在聯集正下方時，裁切寬度再取 raster 聯集與圖說跨距的聯集。圖上的標示文字是疊在圖上的 text block、不屬於任何 raster，只看圖框會被切掉（實測 Fig 8.10 右側四個標示框全被切掉）；這本書的圖說按圖塊寬度排版，可作為圖塊真實寬度的代理。圖說在旁欄時不適用，會把整欄內文裁進來。
- caption 所在頁無可用 raster 時，退回幾何裁切（重用 `extract_figures.figure_rect()` 與 `detect_columns()`），標記 `geometric_fallback` 並設 `include: false`。實測 6 張，品質不可信，需逐張目視認可。
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

35 個有圖的章，合計 139 張。Ch3（術前評估）與 Ch34（Heart-Lung/Lung Transplantation）在書中無 Figure。

### Part I Basics（掛 Ch0 母頁下，56 張）

| Nasr ed2 章 | 圖 | Notion 頁 | page id |
|---|---|---|---|
| 1 Cardiovascular Development | 1 | 正常心臟解剖 | 3a1e77f4-b1f0-81d1-bcab-c92324b4098a |
| 2 Important Concepts in CHD | 6 | 4 types of lesion ⚠️ | 3a1e77f4-b1f0-813d-9432-dc883d83a125 |
| 4 Intraoperative Management | 1 | 術中管理 | 3a2e77f4-b1f0-810b-aa94-f7ed16a667c9 |
| 5 Developmental Hemostasis & PBM | 3 | Developmental Hemostasis 與 PBM | 3a4e77f4-b1f0-81e6-952c-f3e263f5dfb2 |
| 6 Cardiac Catheterization Data | 5 | 心導管數據判讀 | 3a2e77f4-b1f0-8120-9461-f9fba4666931 |
| 7 Cardiopulmonary Bypass | 9 | 體外循環 | 3a2e77f4-b1f0-81bc-a7ce-f41fdec3abcf |
| 8 Echocardiography | 11 | Echocardiography（TEE 完整切面） | 3a4e77f4-b1f0-8137-8413-d0fcd88b23f6 |
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
- `geometric_fallback`（6 張）預設 `include: false`，不會進 Notion，需在 contact sheet 上逐張認可。
- Ch6 的 Fig 6.2、6.3 文字層無 caption，抽不到，列為人工處理項目。
- `oversized_union` 在縮圖牆以紅字標示。
- `uploaded_block_id` 防止分批執行時重複插圖。

## 驗收方式

先只做 **Ch8 Echocardiography** 一章 11 張。選它的理由：TEE 切面圖多為 multi-panel，是聯集邏輯最容易出錯的一章；且 Ch8 同時含內文交叉引用誤判（Fig 8.1）與跨頁 caption，字體過濾與配對邏輯一次驗證。

驗收由使用者對成果判斷，不對架構判斷：

1. Contact sheet 縮圖牆 — 裁切是否完整、哪幾張不需要。
2. Notion 頁面實際插入位置。

Ch8 品質確認後，才推展其餘 34 章共 128 張；屆時再決定一次跑完或分批。

## 明確排除

- 不抽 Table 與 Box。
- 不處理 Park's Handbook 的圖。
- 不修改 `extract_figures.py`（Miller 專用）與 `upload_figures.py`。
- 不處理 Notion 有頁但 Nasr 無對應章的頁面。
- 不建向量檢索層。與 Miller 那輪的決策一致。
- 不為幾何 fallback 改良欄位偵測。只有 6 張，改良的投入報酬不成比例，改用「預設不納入 + 人工認可」處理。

## 執行結果（2026-07-24）

**139 張上傳完成，分佈 37 個 Notion 頁。** 全書抽出 145 張（139 單張 + 6 圖譜頁），預設納入 139。

落回「二、圖表」的 6 張：Fig 1.1（胎兒循環，「正常心臟解剖」頁的小節都是解剖構造，無對應）、Fig 7.5–7.9（TEG/ROTEM 判讀與輸血演算法，「體外循環」頁沒有凝血監測小節）。依設計不硬指派。

未上傳的 6 張：Fig 7.2、7.3、11.2、11.4、11.5、11.9，全部是 `geometric_fallback`。

### 執行中發現、設計階段未預見的四件事

1. **Ch4 的 Fig 4.1 取不到書本頁碼。** 該章只有一張圖且落在無頁眉的頁面，章內拿不出位移基準。改為借用章號最接近那一章的位移（位移隨章號單調漂移），得書 p.37，與前後頁頁眉 36/38 一致。
2. **重疊門檻必須相對「較窄一方」。** 相對 caption 寬度會讓 Fig 15.1 的 8 個窄 panel 全數落空；要求 raster 落在 caption 跨距內則換成寬圖配窄圖說的 9.1、12.1、27.7、31.6 落空。
3. **圖上的標示文字不屬於任何 raster。** Fig 8.10 右側四個標示框被切掉。改為圖說在圖正下方時用圖說跨距補足寬度（旁欄型不適用）。
4. **Ch8 的 28-view TEE 圖譜整組漏掉。** 見「範圍圖說」一節。

前三項都是在 Ch8 驗收關卡攔下的，佐證了「先做一章再推展」的設計決定：11 張裡就踩到兩個，139 張直接全跑會有相當數量的缺角圖進到 Notion。

