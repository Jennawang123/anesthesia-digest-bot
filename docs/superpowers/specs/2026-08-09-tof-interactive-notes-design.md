# Ch3 Tetralogy of Fallot 互動式學習頁 設計文件

日期：2026-08-09

## 目的

把 Notion「小兒心臟學讀書會」Ch3 Tetralogy of Fallot（+PA variants）三個子頁的既有筆記內容，轉成一個自包含的互動式 HTML/JS 學習頁，供深度理解病理生理心智模型（用途 B）與麻醉決策情境模擬（用途 C）之用。不是重新研究或補充新內容，是既有 Notion 內容的轉譯與互動化。

## 範圍

三個病灶頁，同一套完整互動框架，內容忠實對應已 fetch 到的 Notion 現有內容（不新增未經查證的醫學內容）：

1. TOF（典型）
2. TOF with Pulmonary Atresia
3. TOF with Absent Pulmonary Valve

## 內容來源（已 fetch，見對話記錄）

- Notion 母頁：https://app.notion.com/p/3a1e77f4b1f081a3b7e6d47279d4ca30 （Ch3 索引，含中文 Key Points）
- 三子頁各自的「一、內文筆記／二、圖表／三、臨床重點／四、易考點／五、常見陷阱」五段結構
- 圖片 7 張，已下載到本機 scratchpad：
  `/private/tmp/claude-501/-Users-wangyingyu-Library-Mobile-Documents-com-apple-CloudDocs-Jenna-agent/c6e37b1e-d920-4525-9776-e1baab649709/scratchpad/tof_images/`
  - fig24-1-anatomy.png（TOF 解剖總覽，典型TOF頁）
  - fig24-2-parasternal.png（Parasternal long-axis echo，典型TOF頁）
  - fig24-3-infundibular.png（Infundibular stenosis 光譜圖，典型TOF頁）
  - fig24-4-shunts.png（姑息性 shunt 手術選項，典型TOF頁）
  - fig25-1-tofpa.png（TOF/PA 解剖分組圖，TOF+PA頁）
  - img3904-staged.jpg（分階段手術流程手寫圖，TOF+PA頁，2.3MB 需壓縮）
  - fig26-1-apv.png（TOF+APV 動脈瘤式擴張圖，TOF+APV頁）

## 架構

單一自包含 HTML 檔（inline CSS + vanilla JS，無外部 CDN、無後端）。理由：個人學習工具不需跨裝置同步；Notion 圖片為 presigned URL 會過期，須轉存為固定資源；單檔可直接發布成 Claude Artifact，也可存成本機檔案雙用（不依賴網路）。

產出：
- 本機檔案：`Jenna_agent/tof-interactive-notes.html`（供離線開啟）
- 同步發布為 Claude Artifact（方便手機/平板隨時開啟複習）

## 頁面結構

### 1. 頂層分頁（Tab）
三個病灶各一個 tab：典型TOF／TOF+PA／TOF+APV。Tab 切換用純 JS 顯示/隱藏，不做路由。

### 2. 各分頁內的可折疊區塊（Accordion）
對應 Notion 原本五段，展開/收合用 JS toggle：
- 解剖與生理（含內文筆記中的 Prevalence/解剖/生理/臨床表現子項）
- 手術治療
- 麻醉考量（誘導/維持/Post-CPB/併發症，典型TOF頁另含 JET 專節）
- 臨床重點（⚡ 條列，常駐顯示不折疊，因為是複習時最先要看的）
- 易考點與常見陷阱 → 併入下方測驗卡機制（見 4），不用靜態條列重複呈現

### 3. 互動式病理生理機轉圖解（典型TOF頁）
一個 SVG/Canvas 簡圖，呈現心臟四腔室＋VSD＋RVOT＋主動脈。提供一個滑桿或左右按鈕控制「RVOT obstruction 嚴重度」，即時：
- 用箭頭動畫呈現血流方向與相對量（L→R 或 R→L，經 VSD）
- 顯示對應的臨床標籤（輕度 PS → acyanotic/pink tet；重度 PS → cyanotic TOF）
- 顯示對應的心音提示文字（obstruction 越嚴重、murmur 越微弱）

這是簡化教學圖解，非精確血流動力學模擬，圖解下方需加註「示意圖，非等比例模擬」避免誤讀。

### 4. Tet Spell 處置流程互動卡（典型TOF頁）
逐步展開式流程卡，對應筆記中「治療順序」：
1. knee-chest position / 壓迫股動脈-腹主動脈
2. IV bolus 15-30ml/kg 晶體液
3. 加深麻醉 + morphine 0.05-0.1mg/kg
4. phenylephrine 5-10mcg/kg bolus 或 infusion
5. propranolol/esmolol（若仍無效）

每步點擊展開「為什麼這樣做」的生理學解釋（取自既有筆記文字，不新編）。額外設一個互動陷阱點：使用者若點選「給 beta-agonist 拉高血壓」的誘餌選項，跳出警示說明為何絕對禁忌（infundibular spasm 惡化）。

### 5. 測驗卡（三頁皆有）
把三頁各自的「四、易考點」（❓/答案）與「五、常見陷阱」（⚠️）轉成可翻面卡片：正面問題/陷阱敘述，點擊翻面看答案/正解。卡片右上角可標記「已熟悉」，狀態存 localStorage（key 依卡片內容 hash，避免之後編輯文字打亂進度）。

### 6. 圖片
7 張圖片先用本機工具壓縮/縮放（尤其 img3904-staged.jpg 從 3716x2787 縮到合理顯示尺寸，如長邊 ≤1400px），轉成 base64 內嵌於 HTML（不依賴外部連結，避免 Notion presigned URL 過期問題）。點擊圖片可 lightbox 放大檢視；圖說保留原英文 caption，並在圖片下方附中文重點標註（依既有筆記內容摘錄，不新編醫學判讀）。

## 資料結構

內容以 JS 物件（非外部 JSON 檔，單檔原則）分病灶儲存：

```js
const LESIONS = {
  classic: { title, anatomy, physiology, surgery, anesthesia, keyPoints, quizCards, images },
  pa:      { ... 同結構 ... },
  apv:     { ... 同結構 ... },
};
```

## 不做的事（範圍外）

- 不接資料庫/後端、不做跨裝置同步（單機 localStorage 即可）
- 不新增 Notion 頁面沒有的醫學內容或延伸判讀
- 不做精確血流動力學數值模擬，機轉圖解只是教學示意
- 不處理 Ch3 以外的其他章節

## 驗證方式

本機瀏覽器開啟 HTML 檔，逐一測試：三個 tab 切換、accordion 展開收合、機轉圖解滑桿互動、tet spell 流程卡逐步展開與陷阱警示、測驗卡翻面與已熟悉標記持久化（reload 後仍保留）、圖片 lightbox 放大、手機版面（viewport 縮放）不跑版。
