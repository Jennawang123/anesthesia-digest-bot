# 地球儀細節精緻化 — 設計文件

## 背景

`travel-atlas.html` 的地球儀是手刻 Canvas 2D 向量渲染（無 WebGL/three.js），已有：
- `CONTINENTS`：11 塊 RDP 簡化海岸線
- `HIGHLANDS`/`MOUNTAINS`：ETOPO1 地形著色疊加
- 效能優化：漸層快取、拖曳中降密度、`requestAnimationFrame` 節流

使用者想繼續讓地球儀「精緻一點」，選定方向為**地圖細節度**：國界線、主要河流、國家/城市名稱標注三項。

## 問題發現

檢查現有實作時發現 `<canvas id="mapCanvas" width="360" height="360">` 的實體解析度是寫死的 360×360px，未依 `devicePixelRatio` 縮放。在高 DPR 裝置（多數手機 dpr≈2-3）上，畫面是被 CSS 放大顯示，本質上是模糊的。globe 半徑在 zoom=1 時約 147 實體像素。

在這個解析度下加國界線，多數小國的邊界會糊成雜訊而非可辨識的細節。因此本次範圍把「畫布解析度」列為前置條件，優先處理。

## 範圍

1. Canvas 依 `devicePixelRatio` 動態設定實體解析度
2. 國界線（全球，Natural Earth 110m 簡化）
3. 主要河流（約 20-30 條世界級河流，Natural Earth 110m 簡化）
4. 國家/城市名稱標注 — **不需新開發**，現有點擊 pin 的 tooltip 已顯示行程標題，已滿足「點擊才顯示」的需求

## 架構

### 1. Canvas 解析度

- 新增一個 `resizeGlobeCanvas()` 函式：讀取 canvas 容器的 CSS 顯示尺寸（`getBoundingClientRect()`）× `window.devicePixelRatio`，設定 `canvas.width`/`canvas.height`。
- 現有渲染程式碼（`renderGlobeCanvas`、`projectGlobe` 等）都是直接用 `canvas.width`/`canvas.height` 做座標運算，沒有假設 CSS 像素空間，因此解析度提升後這些函式不需要改動座標邏輯。
- 需要調整的是「視覺粗細」相關的常數：`ctx.lineWidth`（海岸線描邊、rim highlight）、pin 的半徑與 glow 半徑，這些要乘上 `dpr` 縮放係數，否則在高解析度下線條/pin 會顯得過細過小。
- 新增 resize 監聽（`window.addEventListener('resize', ...)`，debounce 後呼叫 `resizeGlobeCanvas()` + `renderGlobeCanvas()`），因為現在只在 `drawMap()` 呼叫時設定一次。

### 2. 資料處理（離線腳本，比照 ETOPO1 地形做法）

用 Natural Earth 110m 公開資料（跟現有海岸線同精度等級，透過 GitHub 上的 Natural Earth GeoJSON 鏡像下載，非即時 API 查詢）：

- **國界**：`ne_110m_admin_0_countries`。每個國家的（multi）polygon 轉成 `[lng,lat]` 環狀陣列，格式比照 `CONTINENTS`。用 RDP 演算法簡化到與現有海岸線相近的點數量級（目標：全部國界加總後的點數跟 `CONTINENTS`（約 1000 點）同數量級，不能大幅超過，避免拖累效能）。
- **河流**：`ne_110m_rivers_lake_centerlines`。依 `scalerank` 篩選最高等級（世界最主要的約 20-30 條河流，如尼羅河、亞馬遜河、長江、黃河、多瑙河等），轉成開放折線陣列（非閉合環）。

處理結果離線算好，寫死成 `BORDERS`、`RIVERS` 兩個 JS const 陣列直接嵌入 `travel-atlas.html`，不是 runtime 向外部 API 查詢——維持 single-file、無執行期依賴的架構慣例。

### 3. 渲染整合

- `DENSE_BORDERS`：沿用既有的 `densifyRings()` 密化管線（球面 slerp 插值，避免地平線裁切產生對角線瑕疵）。
- `DENSE_RIVERS`：河流是開放折線不是閉合環，`densifyRings()` 目前假設環狀（`(i+1)%unit.length` 會把最後一點跟第一點連起來），需要另外寫一個 `densifyPolylines()`，邏輯相同但不做首尾閉合。
- 國界繪製：沿用 `fillRingSet` 的地平線裁切迴圈邏輯，但 `doStroke=true`、不呼叫 `ctx.fill()`（傳入透明/跳過 fillStyle），描邊用淡白色細線（如 `rgba(255,255,255,.25)`）。
- 河流繪製：新寫 `strokePolylineSet()` 函式，邏輯與 `fillRingSet` 相似（同樣的可見半球判斷、`horizonPt` 裁切），但路徑不閉合、只 `stroke()`，用淡藍色（如 `rgba(120,180,220,.5)`）。
- 效能：國界與河流的繪製都放在 `renderGlobeCanvas()` 裡跟 `HIGHLANDS`/`MOUNTAINS` 同一個 `if(!globeDragging)` 區塊內——拖曳中略過，放開滑鼠才畫，維持既有的「拖曳中只畫最基本圖層」效能原則。

### 4. 名稱標注

不需新開發。`attachGlobeInteractions()` 裡 `pointerup` 已有 hit-test 邏輯，點中 pin 會顯示 `tip.textContent = hit.title`（行程標題，通常含國旗+城市名，如「🇰🇷首爾」）。此需求已被現有行為滿足。

## 錯誤處理

- 若 `devicePixelRatio` 不存在（極舊瀏覽器），fallback 為 `1`。
- `BORDERS`/`RIVERS` 資料是靜態嵌入陣列，沒有網路請求失敗的情境需要處理。
- resize 事件需要 debounce（例如 150ms），避免拖曳視窗邊框時高頻觸發重算。

## 測試

- Playwright 截圖比對 DPR 修正前後的清晰度（放大截圖檢查邊緣鋸齒/模糊程度差異）。
- 旋轉地球儀到不同角度，確認國界/河流的地平線裁切沒有產生對角線瑕疵（比照上次 `HIGHLANDS`/`MOUNTAINS` 驗證方式）。
- 效能基準測試：比照上次地形疊加的做法，量測 100 幀渲染耗時（拖曳模式 vs 靜止模式），確認新增的國界/河流沒有讓拖曳中的效能倒退（拖曳中應該完全跳過，理論上不受影響，但要驗證閒置時的渲染沒有明顯變慢）。
- 檢查新增的總點數（`BORDERS`+`RIVERS` 密化後的點數）維持在合理量級，不要讓靜止畫面的渲染耗時大幅上升。
