# 地球儀視覺精緻化第二輪 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 travel-atlas.html 的地球儀邊緣平滑、地形色塊柔邊過渡、有 3D 立體陰影感，且拖曳旋轉中維持與靜止時相同的完整品質。

**Architecture:** 在既有的地平線裁切繪圖迴圈（`fillRingSet`/`strokePolylineSet`）裡把 `lineTo` 逐點直線改成貝茲曲線平滑；`HIGHLANDS`/`MOUNTAINS` 改用逐塊放射狀漸層柔邊取代硬邊實色；新增一層整球陰影疊加做 limb darkening；並移除現有 `globeDragging` 造成的降級渲染分支，改成固定全品質。

**Tech Stack:** 純 HTML/CSS/JS（無 build step），Canvas 2D API（`quadraticCurveTo`、`createRadialGradient`、`globalCompositeOperation`），Playwright 做視覺與效能驗證。

---

## 背景知識（開始前必讀）

- `travel-atlas.html` 是 single-file PWA，沒有測試框架，驗證一律用 `node --check` 語法檢查 + Playwright 瀏覽器內視覺/效能驗證。
- 本計畫接續 [2026-07-12-globe-detail-refinement.md](2026-07-12-globe-detail-refinement.md)（已完成：DPR 解析度、國界線 `BORDERS`、河流 `RIVERS`）之後的第二輪視覺精緻化。
- **執行前務必先讀取目前檔案裡這幾個函式的實際內容**（`grep -n "function fillRingSet\|function strokePolylineSet\|function renderGlobeCanvas\|function buildGlobeGradients\|const DENSE_CONTINENTS\|function densifyRings" travel-atlas.html`），因為每個 Task 都會修改同一個檔案，前一個 Task 的改動會讓行號往後移，**用程式碼內容比對，不要死板依賴本文件寫的行號**。
- 核心渲染管線：`renderGlobeCanvas()` 每次拖曳/縮放都會呼叫。目前對每個地理資料集合（海岸線 `DENSE_CONTINENTS`、地形 `DENSE_HIGHLANDS`/`DENSE_MOUNTAINS`、國界 `DENSE_BORDERS`、河流 `DENSE_RIVERS`）都跑同一種「地平線裁切」迴圈：把每個點轉到目前旋轉角度下的 3D 座標（`rot3d`），球體背面的點不畫，經過地平線的邊用 `horizonPt` 內插出裁切點，可見的點投影到螢幕座標（`proj3d`）後串成路徑，最後 `fill()`（封閉環，`fillRingSet`）或 `stroke()`（開放折線，`strokePolylineSet`）。
- `globeDragging` 是拖曳中為 `true` 的全域旗標。目前 `renderGlobeCanvas()` 用它做兩件降級：(1) 海岸線切到低密度版 `DENSE_CONTINENTS_DRAG`，(2) 完全跳過地形/國界/河流。上一輪效能測試量到靜止渲染 100 幀只要 39-47ms（每幀 <0.5ms），遠低於 60fps 的 16.6ms 預算，所以這次會拿掉這兩個降級分支。

---

### Task 1: 邊緣平滑化（貝茲曲線）

**Files:**
- Modify: `travel-atlas.html`（`buildGlobeGradients` 之後、`fillRingSet` 之前，新增 `tracePath` 函式）
- Modify: `travel-atlas.html`（`fillRingSet` 的 `flush` 內部）
- Modify: `travel-atlas.html`（`strokePolylineSet` 的 `flush` 內部）

- [ ] **Step 1: 新增 `tracePath` 平滑繪製函式**

用 `grep -n "function fillRingSet" travel-atlas.html` 找到 `function fillRingSet(ctx,rings,styleFn,rot3d,proj3d,horizonPt,doStroke){` 這一行，在它前面插入：

```javascript
// Draws a smoothed curve through `pts` instead of straight lineTo segments:
// each original point becomes a quadraticCurveTo control point and the
// curve actually passes through the midpoint of each consecutive pair. This
// is the standard cheap way to round off a jagged polyline in Canvas 2D —
// same number of draw calls as lineTo, no extra source data needed.
function tracePath(ctx,pts){
  const n=pts.length;
  ctx.moveTo(pts[0][0],pts[0][1]);
  if(n===2){ctx.lineTo(pts[1][0],pts[1][1]);return;}
  for(let i=1;i<n-1;i++){
    const[x,y]=pts[i],[nx,ny]=pts[i+1];
    ctx.quadraticCurveTo(x,y,(x+nx)/2,(y+ny)/2);
  }
  const[lx0,ly0]=pts[n-2],[lx1,ly1]=pts[n-1];
  ctx.quadraticCurveTo(lx0,ly0,lx1,ly1);
}
function fillRingSet(ctx,rings,styleFn,rot3d,proj3d,horizonPt,doStroke){
```

（也就是把 `tracePath` 插在既有 `function fillRingSet(...){` 那一行正上方，`fillRingSet` 本身內容目前不變，下一步才改。）

- [ ] **Step 2: `fillRingSet` 改用 `tracePath`**

在 `fillRingSet` 內找到：

```javascript
    const flush=()=>{
      if(path.length>2){
        ctx.beginPath();
        path.forEach(([x,y],i)=>i===0?ctx.moveTo(x,y):ctx.lineTo(x,y));
        ctx.closePath();ctx.fill();
        if(doStroke)ctx.stroke();
      }
      path=[];
    };
```

改成：

```javascript
    const flush=()=>{
      if(path.length>2){
        ctx.beginPath();
        tracePath(ctx,path);
        ctx.closePath();ctx.fill();
        if(doStroke)ctx.stroke();
      }
      path=[];
    };
```

- [ ] **Step 3: `strokePolylineSet` 改用 `tracePath`**

在 `strokePolylineSet` 內找到：

```javascript
    const flush=()=>{
      if(path.length>1){
        ctx.beginPath();
        path.forEach(([x,y],i)=>i===0?ctx.moveTo(x,y):ctx.lineTo(x,y));
        ctx.stroke();
      }
      path=[];
    };
```

改成：

```javascript
    const flush=()=>{
      if(path.length>1){
        ctx.beginPath();
        tracePath(ctx,path);
        ctx.stroke();
      }
      path=[];
    };
```

- [ ] **Step 4: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/travel-atlas.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_polish1.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_polish1.js && echo OK
```

Expected: `OK`

- [ ] **Step 5: Playwright 視覺驗證**

起本機伺服器（挑一個未被佔用的 port，例如 8945），用 Playwright 開啟、切到 `'atlas'` tab（globe 所在的 tab id，不是 `'home'`），旋轉到能看到破碎海岸線的角度（例如印尼群島、地中海沿岸），截圖後放大局部檢查：跟 Task 開始前的舊版比，折角應該變圓滑，海岸線不再是明顯的直線段拼接。用 `mcp__playwright__browser_console_messages`（`level:"error"`）確認 0 error。驗證完 `pkill` 掉本機伺服器。

- [ ] **Step 6: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add travel-atlas.html
git commit -m "feat: smooth globe coastline/border/river edges with quadratic curves"
```

---

### Task 2: 移除拖曳降級分支

**Files:**
- Modify: `travel-atlas.html`（`densifyRings` 呼叫區塊，刪除 `DENSE_CONTINENTS_DRAG`）
- Modify: `travel-atlas.html`（`renderGlobeCanvas` 內的地形/國界/河流繪製區塊）

**背景：** 上一輪效能測試量到静止渲染 100 幀只要 39-47ms（<0.5ms/幀），拖曳降級（低密度海岸線+跳過地形/國界/河流）帶來的效能收益可忽略，但使用者這次明確要求拖曳中也要完整效果。拿掉分支後程式碼也更簡單。

- [ ] **Step 1: 刪除未使用的 `DENSE_CONTINENTS_DRAG`**

找到（`grep -n "DENSE_CONTINENTS_DRAG" travel-atlas.html`）：

```javascript
const DENSE_CONTINENTS=densifyRings(CONTINENTS,MAX_EDGE_DEG);
const DENSE_CONTINENTS_DRAG=densifyRings(CONTINENTS,MAX_EDGE_DEG_DRAG);
const DENSE_HIGHLANDS=densifyRings(HIGHLANDS,MAX_EDGE_DEG_DRAG);
```

改成：

```javascript
const DENSE_CONTINENTS=densifyRings(CONTINENTS,MAX_EDGE_DEG);
const DENSE_HIGHLANDS=densifyRings(HIGHLANDS,MAX_EDGE_DEG_DRAG);
```

（`MAX_EDGE_DEG_DRAG` 這個常數本身還留著，`DENSE_HIGHLANDS`/`DENSE_MOUNTAINS`/`DENSE_BORDERS`/`DENSE_RIVERS` 都還在用它做密化，只是不再有「拖曳專用的低密度海岸線」这个用途。）

- [ ] **Step 2: `renderGlobeCanvas` 移除 `if(!globeDragging)` 分支**

找到 `renderGlobeCanvas()` 內這段（在 `const horizonPt=(a,b)=>{...};` 之後）：

```javascript
  const continentSet=globeDragging?DENSE_CONTINENTS_DRAG:DENSE_CONTINENTS;
  fillRingSet(ctx,continentSet,ringIdx=>ICY_IDX.has(ringIdx)?ice:DESERT_IDX.has(ringIdx)?desert:land,rot3d,proj3d,horizonPt,true);
  if(!globeDragging){
    fillRingSet(ctx,DENSE_HIGHLANDS,()=>highland,rot3d,proj3d,horizonPt,false);
    fillRingSet(ctx,DENSE_MOUNTAINS,()=>mountain,rot3d,proj3d,horizonPt,false);
    ctx.strokeStyle='rgba(255,255,255,.25)';
    ctx.lineWidth=0.6*globeDpr;
    strokePolylineSet(ctx,DENSE_BORDERS,rot3d,proj3d,horizonPt);
    ctx.strokeStyle='rgba(120,180,220,.55)';
    ctx.lineWidth=0.9*globeDpr;
    strokePolylineSet(ctx,DENSE_RIVERS,rot3d,proj3d,horizonPt);
  }
```

改成：

```javascript
  fillRingSet(ctx,DENSE_CONTINENTS,ringIdx=>ICY_IDX.has(ringIdx)?ice:DESERT_IDX.has(ringIdx)?desert:land,rot3d,proj3d,horizonPt,true);
  fillRingSet(ctx,DENSE_HIGHLANDS,()=>highland,rot3d,proj3d,horizonPt,false);
  fillRingSet(ctx,DENSE_MOUNTAINS,()=>mountain,rot3d,proj3d,horizonPt,false);
  ctx.strokeStyle='rgba(255,255,255,.25)';
  ctx.lineWidth=0.6*globeDpr;
  strokePolylineSet(ctx,DENSE_BORDERS,rot3d,proj3d,horizonPt);
  ctx.strokeStyle='rgba(120,180,220,.55)';
  ctx.lineWidth=0.9*globeDpr;
  strokePolylineSet(ctx,DENSE_RIVERS,rot3d,proj3d,horizonPt);
```

（`DENSE_HIGHLANDS`/`DENSE_MOUNTAINS` 這兩行下一個 Task 會再改成 `fillFeatheredRingSet`，這裡先只處理「拿掉 if 判斷、固定執行」。）

- [ ] **Step 3: 更新過時的註解**

在同一個函式裡，往上找到這段註解（在 `ctx.strokeStyle='rgba(23,42,26,.5)';` 之前）：

```javascript
  // Continents (land): clip each ring to the visible hemisphere so edges
  // follow the horizon instead of jumping in a straight chord across it.
  // While dragging, use a coarser edge budget and skip the decorative
  // terrain overlays entirely — cuts per-frame trig cost during interaction.
```

改成：

```javascript
  // Continents (land): clip each ring to the visible hemisphere so edges
  // follow the horizon instead of jumping in a straight chord across it.
  // Measured render cost (~0.5ms/frame even with borders+rivers+terrain) has
  // enough headroom that dragging no longer needs a reduced-quality path —
  // every layer renders at full density every frame.
```

- [ ] **Step 4: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/travel-atlas.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_polish2.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_polish2.js && echo OK
```

Expected: `OK`

- [ ] **Step 5: Playwright 驗證拖曳中維持完整圖層**

起本機伺服器，Playwright 開啟並切到 `'atlas'` tab，用 `browser_evaluate` 執行：

```javascript
() => { globeDragging=true; renderGlobeCanvas(); return 'dragging-rendered'; }
```

截圖，確認地形、國界、河流在拖曳狀態下依然畫出來（跟之前「拖曳中會消失」的行為相反）。再設回 `globeDragging=false` 確認畫面一致。

- [ ] **Step 6: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add travel-atlas.html
git commit -m "refactor: drop globe drag/idle quality split, render full detail always"
```

---

### Task 3: 地形色塊柔邊（放射狀漸層）

**Files:**
- Modify: `travel-atlas.html`（`buildGlobeGradients`：移除 `highland`/`mountain` 線性漸層）
- Modify: `travel-atlas.html`（`ICY_IDX`/`DESERT_IDX` 旁新增 `HIGHLAND_RGB`/`MOUNTAIN_RGB` 常數）
- Modify: `travel-atlas.html`（新增 `fillFeatheredRingSet` 函式）
- Modify: `travel-atlas.html`（`renderGlobeCanvas`：地形疊加改呼叫新函式、更新 `_grad` 解構）

- [ ] **Step 1: 新增地形基礎色常數**

找到（`grep -n "const DESERT_IDX" travel-atlas.html`）：

```javascript
const ICY_IDX=new Set([3,4]);
const DESERT_IDX=new Set([2]);
```

改成：

```javascript
const ICY_IDX=new Set([3,4]);
const DESERT_IDX=new Set([2]);
const HIGHLAND_RGB='203,174,114';
const MOUNTAIN_RGB='138,107,69';
```

- [ ] **Step 2: `buildGlobeGradients` 移除不再需要的 `highland`/`mountain` 線性漸層**

找到：

```javascript
function buildGlobeGradients(ctx,cx,cy,R){
  const bg=ctx.createRadialGradient(cx-R*0.35,cy-R*0.35,R*0.1,cx,cy,R);
  bg.addColorStop(0,'#1E6091');bg.addColorStop(0.55,'#154C74');bg.addColorStop(1,'#0A2A42');
  const land=ctx.createLinearGradient(cx,cy-R,cx,cy+R);
  land.addColorStop(0,'#7BA35A');land.addColorStop(0.5,'#5C8B4A');land.addColorStop(1,'#3F6B3A');
  const ice=ctx.createLinearGradient(cx,cy-R,cx,cy+R);
  ice.addColorStop(0,'#F0F5F7');ice.addColorStop(1,'#CBD9DF');
  const desert=ctx.createLinearGradient(cx,cy-R,cx,cy+R);
  desert.addColorStop(0,'#C9A66B');desert.addColorStop(1,'#A9895A');
  const highland=ctx.createLinearGradient(cx,cy-R,cx,cy+R);
  highland.addColorStop(0,'#CBAE72');highland.addColorStop(1,'#A88C52');
  const mountain=ctx.createLinearGradient(cx,cy-R,cx,cy+R);
  mountain.addColorStop(0,'#8A6B45');mountain.addColorStop(1,'#5E4530');
  return{bg,land,ice,desert,highland,mountain};
}
```

改成：

```javascript
function buildGlobeGradients(ctx,cx,cy,R){
  const bg=ctx.createRadialGradient(cx-R*0.35,cy-R*0.35,R*0.1,cx,cy,R);
  bg.addColorStop(0,'#1E6091');bg.addColorStop(0.55,'#154C74');bg.addColorStop(1,'#0A2A42');
  const land=ctx.createLinearGradient(cx,cy-R,cx,cy+R);
  land.addColorStop(0,'#7BA35A');land.addColorStop(0.5,'#5C8B4A');land.addColorStop(1,'#3F6B3A');
  const ice=ctx.createLinearGradient(cx,cy-R,cx,cy+R);
  ice.addColorStop(0,'#F0F5F7');ice.addColorStop(1,'#CBD9DF');
  const desert=ctx.createLinearGradient(cx,cy-R,cx,cy+R);
  desert.addColorStop(0,'#C9A66B');desert.addColorStop(1,'#A9895A');
  return{bg,land,ice,desert};
}
```

（`highland`/`mountain` 不再是固定方向的線性漸層——下一步改成每塊地形疊加各自的放射狀漸層，柔化邊界。）

- [ ] **Step 3: 新增 `fillFeatheredRingSet` 函式**

在 `strokePolylineSet` 函式結束的 `}` 之後、`function renderGlobeCanvas(){` 之前插入：

```javascript
// Like fillRingSet, but fills each ring with its own radial gradient
// (opaque at the shape's screen-space centroid, fully transparent at its
// edge) instead of one flat color — this feathers highland/mountain patches
// into the surrounding land color instead of a hard cutout edge.
function fillFeatheredRingSet(ctx,rings,colorRgb,rot3d,proj3d,horizonPt){
  rings.forEach(ring=>{
    const pts=ring.map(rot3d);
    const proj=pts.map(p=>p[2]>ZC?proj3d(p):null);
    let sx=0,sy=0,n=0;
    proj.forEach(p=>{if(p){sx+=p.sx;sy+=p.sy;n++;}});
    if(n===0)return; // whole shape on the far side of the globe this frame
    sx/=n;sy/=n;
    let maxR=1;
    proj.forEach(p=>{if(p){const d=Math.hypot(p.sx-sx,p.sy-sy);if(d>maxR)maxR=d;}});
    const grad=ctx.createRadialGradient(sx,sy,0,sx,sy,maxR*1.15);
    grad.addColorStop(0,`rgba(${colorRgb},0.85)`);
    grad.addColorStop(0.65,`rgba(${colorRgb},0.4)`);
    grad.addColorStop(1,`rgba(${colorRgb},0)`);
    ctx.fillStyle=grad;
    let path=[];
    const flush=()=>{
      if(path.length>2){
        ctx.beginPath();
        tracePath(ctx,path);
        ctx.closePath();ctx.fill();
      }
      path=[];
    };
    for(let i=0;i<pts.length;i++){
      const cur=pts[i],prev=pts[(i-1+pts.length)%pts.length];
      const curVis=cur[2]>ZC,prevVis=prev[2]>ZC;
      if(curVis!==prevVis){
        const h=horizonPt(prev,cur);
        if(prevVis){path.push([h.sx,h.sy]);flush();}
        else{flush();path.push([h.sx,h.sy]);}
      }
      if(curVis){const p=proj3d(cur);path.push([p.sx,p.sy]);}
    }
    flush();
  });
}
```

- [ ] **Step 4: `renderGlobeCanvas` 改呼叫 `fillFeatheredRingSet`**

找到（Task 2 改完後的樣子）：

```javascript
  fillRingSet(ctx,DENSE_HIGHLANDS,()=>highland,rot3d,proj3d,horizonPt,false);
  fillRingSet(ctx,DENSE_MOUNTAINS,()=>mountain,rot3d,proj3d,horizonPt,false);
```

改成：

```javascript
  fillFeatheredRingSet(ctx,DENSE_HIGHLANDS,HIGHLAND_RGB,rot3d,proj3d,horizonPt);
  fillFeatheredRingSet(ctx,DENSE_MOUNTAINS,MOUNTAIN_RGB,rot3d,proj3d,horizonPt);
```

- [ ] **Step 5: 更新 `_grad` 解構**

找到：

```javascript
  const{bg,land,ice,desert,highland,mountain}=_grad;
```

改成：

```javascript
  const{bg,land,ice,desert}=_grad;
```

- [ ] **Step 6: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/travel-atlas.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_polish3.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_polish3.js && echo OK
```

Expected: `OK`

- [ ] **Step 7: Playwright 視覺驗證**

起本機伺服器，Playwright 開啟並切到 `'atlas'` tab，旋轉到能看到喜馬拉雅/青藏高原疊加區塊的角度（`rotLon=-80,tilt=10` 附近，前一輪任務驗證過這個角度看得到），截圖確認：地形色塊中心顏色深、往外漸淡融入陸地色，沒有銳利硬邊界。用 `mcp__playwright__browser_console_messages` 確認 0 error。

- [ ] **Step 8: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add travel-atlas.html
git commit -m "feat: feather globe terrain overlay edges with radial gradients"
```

---

### Task 4: 3D 球體陰影疊加（limb darkening）

**Files:**
- Modify: `travel-atlas.html`（`renderGlobeCanvas`：新增陰影疊加，插在河流描邊之後、Rim highlight 之前）

- [ ] **Step 1: 新增陰影疊加**

找到（Task 2 改完後的樣子，`renderGlobeCanvas` 內河流繪製那兩行之後、`// Rim highlight` 註解之前）：

```javascript
  ctx.strokeStyle='rgba(120,180,220,.55)';
  ctx.lineWidth=0.9*globeDpr;
  strokePolylineSet(ctx,DENSE_RIVERS,rot3d,proj3d,horizonPt);
  // Rim highlight
```

改成：

```javascript
  ctx.strokeStyle='rgba(120,180,220,.55)';
  ctx.lineWidth=0.9*globeDpr;
  strokePolylineSet(ctx,DENSE_RIVERS,rot3d,proj3d,horizonPt);
  // 3D shading: directional highlight near the light source (same offset as
  // the ocean gradient) fading to limb-darkened edges. source-atop keeps the
  // gradient confined to pixels already painted (the sphere disc), so it
  // doesn't bleed onto the transparent canvas outside the globe.
  const shade=ctx.createRadialGradient(cx-R*0.35,cy-R*0.35,R*0.1,cx,cy,R*1.05);
  shade.addColorStop(0,'rgba(255,255,255,.18)');
  shade.addColorStop(0.5,'rgba(255,255,255,0)');
  shade.addColorStop(0.85,'rgba(0,0,0,.15)');
  shade.addColorStop(1,'rgba(0,0,0,.45)');
  ctx.globalCompositeOperation='source-atop';
  ctx.fillStyle=shade;
  ctx.fillRect(cx-R,cy-R,R*2,R*2);
  ctx.globalCompositeOperation='source-over';
  // Rim highlight
```

（放在 Rim highlight 跟 Pins 之前，陰影只影響陸地/海洋/國界/河流，不會蓋到之後畫的亮綠色邊框或黃色 pin 標記，保持 pin 清晰好辨識。）

- [ ] **Step 2: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/travel-atlas.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_polish4.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_polish4.js && echo OK
```

Expected: `OK`

- [ ] **Step 3: Playwright 視覺驗證**

起本機伺服器，Playwright 開啟並切到 `'atlas'` tab，截全頁截圖檢查：
1. 球體左上方（`cx-R*0.35,cy-R*0.35` 附近）看起來偏亮，邊緣（球體輪廓附近）看起來偏暗，整體有立體球感而不是平塗圓餅
2. 球體外側（畫布的深色背景區域）沒有被陰影污染——用 `browser_evaluate` 讀取球體外一個像素點（例如 canvas 左上角 `(5,5)`）的 pixel 顏色（`ctx.getImageData(5,5,1,1).data`），確認 alpha 為 0 或維持原本畫布底色，不是被 `fillRect` 誤畫到的深色/淺色陰影色
3. 黃色 pin 標記跟綠色 rim 邊框亮度不受影響（肉眼確認顏色跟疊加陰影前一致）

- [ ] **Step 4: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add travel-atlas.html
git commit -m "feat: add limb-darkening shading overlay for 3D globe depth"
```

---

### Task 5: 整體驗證（視覺+效能）

**Files:** 無檔案修改，純驗證。

- [ ] **Step 1: 效能重新基準測試**

起本機伺服器（例如 port 8946），Playwright 開啟、切到 `'atlas'` tab、`browser_resize` 設 390×844，執行：

```javascript
() => {
  function bench(drag){ globeDragging = drag; let t0=performance.now(); for(let i=0;i<100;i++){ globeView.rotLon+=1; renderGlobeCanvas(); } return performance.now()-t0; }
  bench(true); bench(false); // warmup
  const drag1=bench(true), idle1=bench(false), drag2=bench(true), idle2=bench(false);
  return {drag1,idle1,drag2,idle2};
}
```

Expected: 四個數字應該非常接近（因為 Task 2 已經拿掉 drag/idle 分支，兩種模式現在跑同一套邏輯），且都要遠低於 1666ms（100 幀 × 16.6ms 預算），也就是應該都在 100ms 以內（實際上依照先前基準抓，合理範圍是幾十 ms）。如果某次數字異常飆高（例如超過 300ms），要往回檢查 Task 3/4 新增的 gradient 建立邏輯是否有非預期的重複運算。

- [ ] **Step 2: 拖曳互動端對端驗證**

用 `dispatchEvent` 模擬真實拖曳（`pointerdown`→多次 `pointermove`→`pointerup`），確認：
1. 拖曳過程中畫面持續顯示地形/國界/河流（不會像改動前那樣消失）
2. 拖曳結束後 `globeDragging` 恢復 `false`
3. 全程 0 console error

- [ ] **Step 3: 綜合視覺截圖**

旋轉到至少 3 個不同角度截圖存查（不需要留在 repo 裡，看過即可），確認海岸線平滑、地形柔邊、3D 陰影、國界、河流、pin 全部疊在一起沒有互相打架或視覺錯亂。

- [ ] **Step 4: 清理**

```bash
pkill -f "http.server 8946" 2>/dev/null
```

告知使用者若有測試截圖殘留在專案根目錄，需要使用者自己刪除（`rm` 在這個環境會被沙盒權限擋下）。

---

## Self-Review 紀錄

- **Spec coverage：** 邊緣平滑化（Task 1）、移除拖曳降級分支（Task 2）、地形柔邊漸層（Task 3）、3D 陰影疊加（Task 4）、效能與視覺驗證（Task 5）對應 spec 的四個架構小節。
- **Placeholder scan：** 每個 Task 的程式碼修改都是完整可直接套用的 before/after diff，指令都是可執行的完整命令。
- **Type/命名一致性：** `tracePath`（Task 1 定義）在 Task 3 的 `fillFeatheredRingSet` 內重用；`HIGHLAND_RGB`/`MOUNTAIN_RGB`（Task 3 定義）在 `fillFeatheredRingSet` 呼叫處使用，命名一致。`fillRingSet`/`strokePolylineSet`/`fillFeatheredRingSet` 三個繪製函式的參數順序（`ctx,data,style,rot3d,proj3d,horizonPt[,...]`）保持一致，方便之後維護。
- **執行順序相依性：** Task 2 必須在 Task 3 之前執行（Task 3 的 diff 是基於 Task 2 移除 `if(!globeDragging)` 之後的程式碼位置去比對的）；Task 4 同樣依賴 Task 2 已完成。Task 1 跟 Task 2/3/4 互相獨立，但為了讓後續 diff 的比對文字準確，仍建議照 Task 1→2→3→4→5 的順序執行。
