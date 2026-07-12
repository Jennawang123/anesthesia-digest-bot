# 地球儀升級為真實衛星貼圖 3D 球體 — 設計文件

## 背景

使用者對地球儀外觀不滿意，兩輪向量繪圖精緻化（[國界/河流/DPR](2026-07-12-globe-detail-refinement-design.md)、[平滑邊緣/柔邊地形/立體陰影](2026-07-12-globe-visual-polish-design.md)）之後仍然反饋「不夠逼真」。釐清後確認使用者要的是「像真實衛星空拍地球」的質感，這跟目前手刻 Canvas 2D 向量地圖插畫（海岸線多邊形+漸層填色）是完全不同的技術路線，不是能靠繼續打磨向量畫法達到的。

## 範圍決策

- 球體改用 **three.js（WebGL）+ 真實地球日間貼圖**，取代現有 Canvas 2D 向量渲染管線。
- 保留：國界線疊加（衛星照片本身不會畫政治國界，疊加線仍有意義）、拖曳旋轉、滾輪縮放、點擊 pin 顯示行程 tooltip、tooltip 點擊進入行程詳情。
- 移除：`HIGHLANDS`/`MOUNTAINS` 地形色塊疊加、`RIVERS` 河流向量線——真實衛星貼圖已經自然呈現雪山、沙漠、大河的視覺特徵，向量疊加會跟貼圖色調打架、造成視覺雜訊。
- `CONTINENTS`（海岸線填色多邊形）不再需要——真實貼圖已經包含陸地/海洋輪廓與色彩，不需要另外畫陸地色塊。
- 不做：雲層貼圖、夜間燈光貼圖、法線/鏡面反射貼圖（範圍明確排除，之後有需要再另外提案）。

## 資料/資源

- **地球貼圖**：Solar System Scope 2K 日間地球貼圖，`https://www.solarsystemscope.com/textures/download/2k_earth_daymap.jpg`，CC BY 4.0 授權。實測下載為 2048×1024 JPEG，463KB。作為外部圖片檔案存放，不 base64 內嵌進 `travel-atlas.html`（維持 HTML 本體輕量，圖片可被瀏覽器/PWA 快取）。
- **three.js**：透過 CDN（`unpkg.com/three@0.165.0`）以 ES module + `importmap` 方式載入，不需要 npm/bundler，維持「無 build step」的架構慣例。`OrbitControls` 附加模組（`three@0.165.0/examples/jsm/controls/OrbitControls.js`）同樣走 CDN。
- **`BORDERS`**：沿用既有的經緯度資料（Natural Earth 110m land boundary lines，333 條線/1501 點），不需要重新處理。

## 架構

### 1. 場景建置

新增一個 three.js `Scene`：
- `PerspectiveCamera`，初始距離讓地球佔滿目前 `.map-wrap` 容器（跟現有 Canvas 版本的視覺大小接近）。
- `WebGLRenderer`，`canvas` 元素沿用目前 `#mapCanvas` 的位置與容器（`.map-wrap`），但 three.js 需要自己接管這個 canvas 的渲染（不能再用 2D context）。
- 地球本體：`SphereGeometry` + `MeshBasicMaterial`（`map: earthTexture`）——用 `MeshBasicMaterial` 而非需要光源的 `MeshStandardMaterial`，因為範圍明確排除光影貼圖，用貼圖本身的明暗即可，不需要額外打光運算。
- `TextureLoader` 載入地球貼圖（非同步；載入完成前顯示現有的深色海洋佔位背景，避免白屏）。

### 2. 國界線疊加

把 `BORDERS`（`[lng,lat]` 折線陣列）轉換成 three.js 的 3D 座標：沿用現有 `sphereXYZ(lat,lng)` 的球面座標公式，只是半徑改成比地球貼圖球體半徑略大一點點（例如 1.001 倍），避免跟貼圖表面 z-fighting（兩個重疊面互相閃爍）。每條折線用 `THREE.BufferGeometry`+`THREE.Line`（`LineBasicMaterial`，淡白色半透明）畫出，跟現有向量國界颜色風格一致。

### 3. 互動：拖曳旋轉、縮放、pin 點擊

- **拖曳旋轉+慣性滑動+縮放**：用 three.js 官方 `OrbitControls`，設定 `enablePan=false`（不需要平移，只要旋轉+縮放）、`enableDamping=true`（帶阻尼的慣性滑動手感）、`minDistance`/`maxDistance` 對應現有的 0.6x-2.5x 縮放範圍。取代現有手刻的 `attachGlobeInteractions()` 拖曳/縮放邏輯。
- **Pin 標記**：每個行程的 pin 改成 `THREE.Sprite`（一張圓點材質貼圖，或用 `THREE.CanvasTexture` 動態畫一個發光圓點），定位在對應經緯度的球面座標上（半徑跟國界線一樣略高於地球表面）。
- **Pin 點擊/hover**：用 `THREE.Raycaster` 從滑鼠/觸控位置打一條線，檢查跟哪個 pin sprite 相交，取代現有 `Math.hypot(p._sx-mx,p._sy-my)<10` 的 2D 螢幕距離判斷。點擊命中後的行為（顯示 tooltip、點擊 tooltip 開啟行程詳情）不變，只是命中判定方式換了。

### 4. 移除的程式碼

`CONTINENTS`/`DENSE_CONTINENTS`、`HIGHLANDS`/`MOUNTAINS`/`DENSE_HIGHLANDS`/`DENSE_MOUNTAINS`、`RIVERS`/`DENSE_RIVERS`、`fillRingSet`/`fillFeatheredRingSet`/`strokePolylineSet`/`tracePath`/`densifyRings`/`densifyPolylines`/`sphereXYZ`/`rotX`/`rotY`/`slerp`/`projectGlobe`/`buildGlobeGradients`/`renderGlobeCanvas`/`resizeGlobeCanvas`/`attachGlobeInteractions` 這一整組 Canvas 2D 向量渲染管線都會被新的 three.js 場景邏輯取代。`BORDERS` 資料本身保留，取球面座標公式的部分邏輯（等效於 `sphereXYZ`）會在新的 three.js 版本裡重新實作一次（因為座標系統慣例可能需要對齊 three.js 的座標軸方向）。

## 錯誤處理

- 貼圖圖片載入失敗（離線、CDN 掛掉）：顯示現有的深色海洋色 fallback（球體先用純色材質渲染，貼圖載入成功後再替換），並在 UI 上不阻塞——地球儀是裝飾性/導覽用途，不是核心資料功能，載入失敗不該讓整個 Atlas tab 掛掉。
- three.js CDN 載入失敗：同樣需要 fallback，但如果連 three.js 本身都載入失敗，整個地球儀功能無法運作，這種情況直接顯示一個簡單的「地球儀載入失敗」提示，不嘗試恢復成舊版 Canvas 2D 渲染（避免同時維護兩套地球儀邏輯）。

## 測試

- Playwright 視覺驗證：確認貼圖正確載入顯示（不是黑球/白球）、國界線疊加在正確位置、pin 點擊命中判定正確、拖曳旋轉/縮放手感正常。
- 效能：three.js 用 GPU 渲染，預期比純 CPU Canvas 2D 版本更流暢，但要驗證在低階裝置（模擬節流的 CPU/GPU）下沒有明顯掉幀。
- 檔案大小影響驗證：確認貼圖是外部檔案載入（檢查 network request），不是被誤 base64 內嵌進 `travel-atlas.html`（避免 HTML 本體不小心暴增）。
- 部署驗證：貼圖檔案需要跟著 `travel-atlas.html`/`netlify-travel-atlas/index.html` 一起放到 Netlify 部署資料夾，確認正式環境（`delightful-sprite-74e6ab.netlify.app`）能正確載入這個外部圖片路徑。
