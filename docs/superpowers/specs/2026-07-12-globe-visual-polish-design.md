# 地球儀視覺精緻化第二輪 — 設計文件

## 背景

上一輪（[2026-07-12-globe-detail-refinement-design.md](2026-07-12-globe-detail-refinement-design.md)）替地球儀加上了 DPR 解析度、國界線、主要河流。使用者看過參考截圖（別的 app 的平滑 3D 地球儀）後回饋現有效果仍有三個問題：

1. 陸地海岸線邊緣太粗糙鋸齒
2. 高山/平原色塊邊界太生硬，不符合地理上漸變的自然現象
3. 整體缺乏 3D 立體感

使用者要求三項一次修，且**拖曳旋轉中也要維持完整效果**（不接受像上一輪那樣拖曳中降級/跳過圖層）。

## 前提發現：效能餘裕重新評估

上一輪效能基準測試顯示：靜止時渲染 100 幀（含國界+河流+地形疊加+海岸線）耗時 39-47ms，即每幀 <0.5ms，離 60fps 的 16.6ms 預算有大量餘裕。這代表原本「拖曳中用低密度海岸線、跳過地形/國界/河流」的優化是過度保守的早期優化。既然使用者要求拖曳中維持完整效果，且效能數字證實撐得住，本次會**移除 `globeDragging` 判斷造成的降級分支**，所有圖層固定用最高品質渲染，程式碼也因此變簡單（少一組雙軌邏輯）。

## 三個問題的架構設計

### 1. 邊緣平滑化：貝茲曲線平滑折線

`fillRingSet()`（封閉環：海岸線、地形疊加）與 `strokePolylineSet()`（開放折線：國界、河流）目前都是用 `ctx.lineTo()` 逐點直線連接投影後的螢幕座標，相鄰點之間必然是硬折角。

改用「經過中點的二次貝茲曲線」技巧：把每個原始點當作控制點，實際曲線是連接相鄰點中點的 `quadraticCurveTo`。這是 Canvas 2D 平滑折線最輕量的標準做法——不需要更多來源資料點（不用重新處理 Natural Earth 資料），繪圖 API 呼叫次數與現在的 `lineTo` 版本相同（一點對一次呼叫），只是換成 `quadraticCurveTo`，成本可忽略。

兩個函式的路徑建構迴圈（`flush()` 內部）都會改成這個畫法，海岸線、國界、河流、地形疊加的邊緣會一併變平滑。

### 2. 地形色塊柔邊：放射狀漸層取代硬邊填色

`HIGHLANDS`/`MOUNTAINS` 目前用 `fillRingSet` 搭配單一、螢幕空間固定的線性漸層（`highland`/`mountain`，跟旋轉無關），對每一塊 convex hull 形狀做硬邊實色填滿——視覺上像貼紙。

新增 `fillFeatheredRingSet()` 函式：對每一塊地形疊加形狀，取其投影到螢幕後的可見點集合，計算螢幕空間重心與最大半徑，用該重心為圓心建立 `createRadialGradient`（中心不透明地形色 → 邊緣完全透明），取代原本固定的 `styleFn` 回傳單一漸層。這樣每塊高山/高原色塊會自然向外柔化融入底層陸地色，不再有一刀切的邊界。繪圖迴圈本身（地平線裁切邏輯）不變，只是換了 `fillStyle` 的產生方式，且套用同樣的貝茲曲線平滑（第 1 點）畫邊緣。

每幀會為每塊地形疊加（目前 23 塊高原 + 5 塊高山）各建立一個 radial gradient，共約 28 個 gradient 物件——`createRadialGradient`+`addColorStop` 是很輕量的 API，不快取也不會構成效能問題（相較於既有渲染總成本 <0.5ms/幀）。

### 3. 3D 立體感：整球一層陰影疊加（limb darkening）

在所有陸地/地形/國界/河流都畫完、pin 標記畫之前，新增一層「整顆球體」的放射狀陰影疊加：中心偏左上方亮（模擬光源方向，跟現有海洋漸層 `bg` 的光源方向一致 `cx-R*0.35,cy-R*0.35`）、邊緣變暗（模擬球體邊緣自然變暗，即 limb darkening，是真實星球/球體看起來立體的關鍵視覺線索）。

用 `ctx.globalCompositeOperation='source-atop'` 讓這層陰影只疊加在球體已經畫出的像素範圍內（圓形之外的畫布保持透明，不會把陰影畫到球體外側的背景上），畫完後把 `globalCompositeOperation` 重設回 `'source-over'`。這是每幀固定多一次 fillRect+gradient 的成本，跟地圖細節點數無關，O(1)。

### 4. 移除 drag/idle 雙軌分支

`renderGlobeCanvas()` 中現有的：
- `const continentSet=globeDragging?DENSE_CONTINENTS_DRAG:DENSE_CONTINENTS;`
- `if(!globeDragging){ ...畫地形/國界/河流... }`

會改成固定使用 `DENSE_CONTINENTS`（高密度版）與固定畫出地形/國界/河流，不再判斷 `globeDragging`。`DENSE_CONTINENTS_DRAG` 常數與相關的 `MAX_EDGE_DEG_DRAG` 密化用途跟著簡化（`MAX_EDGE_DEG_DRAG` 仍保留給 `densifyPolylines`/`densifyRings` 的國界/河流/地形密化使用，只是不再有「拖曳版」與「靜止版」的雙密度切換）。

`pointermove` 現有的 `requestAnimationFrame` 節流（避免同一幀觸發多次 `renderGlobeCanvas`）維持不變，這個優化跟畫面品質無關，仍然值得保留。

## 錯誤處理

- Canvas 2D API（`quadraticCurveTo`、`createRadialGradient`、`globalCompositeOperation`）都是標準 API，無相容性顧慮，不需要 fallback。
- `fillFeatheredRingSet` 若某塊地形疊加整圈都在球體背面（不可見），螢幕投影點集合為空，直接跳過該塊不畫（避免除以零算重心）。

## 測試

- Playwright 截圖比對：修改前後的海岸線邊緣、地形色塊邊界視覺差異（放大局部截圖檢查折角是否變圓滑）。
- 旋轉到多個角度確認地平線裁切仍然正確（曲線平滑化後容易在地平線邊緣出現新的接縫瑕疵，需要特別檢查裁切點附近的曲線銜接）。
- 效能重新基準測試：拖曳模式與靜止模式的 100 幀渲染耗時應該非常接近（因為移除了雙軌分支，兩者現在跑同一套邏輯），且都要維持在遠低於 16.6ms/幀的範圍內，證實拿掉 drag 優化分支後依然流暢。
- 3D 陰影疊加要確認只出現在球體圓形範圍內，不會在球體外的畫布區域留下陰影痕跡（`source-atop` 用錯範圍時容易發生）。
