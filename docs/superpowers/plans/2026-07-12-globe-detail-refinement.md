# 地球儀細節精緻化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 travel-atlas.html 的手刻 Canvas 2D 地球儀在高解析度螢幕上顯示清晰，並疊加國界線與主要河流，提升地圖細節度。

**Architecture:** Canvas 實體解析度依 `devicePixelRatio` 動態設定（原本寫死 360×360）；國界/河流資料離線用 Natural Earth 110m GeoJSON 經 RDP 簡化後，比照既有 `HIGHLANDS`/`MOUNTAINS` 地形疊加的模式寫死成 JS 常數陣列，用既有的地平線裁切渲染管線描邊繪製，拖曳中略過以維持效能。

**Tech Stack:** 純 HTML/CSS/JS（無 build step），Canvas 2D API，離線 Python 資料前處理（Natural Earth GeoJSON → RDP 簡化 → JS 陣列字面量），Playwright 做視覺/效能驗證。

---

## 背景知識（開始前必讀）

- 專案是 **single-file PWA**：`travel-atlas.html` 一個檔案包含所有 HTML/CSS/JS，沒有 npm、沒有 build step，改完直接存檔即生效。沒有 pytest/jest 之類的測試框架——本計畫的「測試」一律是用 `node --check` 做語法檢查、Playwright 做瀏覽器內視覺與行為驗證。
- 地球儀渲染是手刻 Canvas 2D 向量繪圖（不是 WebGL/three.js），核心概念：
  - 地理座標存成 `[lng,lat]` 陣列（**注意順序是經度在前**，跟 GeoJSON 的 `[lon,lat]` 慣例一致，不需要對調）。
  - `sphereXYZ(lat,lng)` 把經緯度轉成單位球面上的 3D 座標。
  - `densifyRings()`（`travel-atlas.html:473`）把每個**封閉環**（如海岸線、國家外框）用球面內插（`slerp`）加密邊緣，避免地平線裁切時產生對角線瑕疵。**這個函式假設是封閉環**（`(i+1)%unit.length` 會把最後一點連回第一點），本計畫的國界/河流資料是**開放折線**，需要另外寫一個不閉合版本。
  - `fillRingSet()`（`travel-atlas.html:532`）畫封閉環（填色+可選描邊），內含地平線裁切邏輯（球體背面的部分不畫，邊界用 `horizonPt` 內插成地平線上的點）。
  - `renderGlobeCanvas()`（`travel-atlas.html:560`）是主渲染函式，每次拖曳/縮放都會呼叫。`globeDragging` 為真時（使用者正在拖曳）會跳過地形疊加（`HIGHLANDS`/`MOUNTAINS`）以維持流暢度——本計畫新增的國界/河流要沿用同樣的邏輯。
- 目前 `<canvas id="mapCanvas" width="360" height="360">`（`travel-atlas.html:365`）解析度寫死，CSS（`travel-atlas.html:81` `.map-wrap canvas{width:100%;aspect-ratio:1}`）讓它顯示時被瀏覽器縮放填滿容器寬度——在高 DPI 螢幕上這就是模糊的原因。

---

### Task 1: Canvas 依 devicePixelRatio 動態設定解析度

**Files:**
- Modify: `travel-atlas.html:447`（新增 `globeDpr` 全域變數）
- Modify: `travel-atlas.html:500`（`drawMap` 之前新增 `resizeGlobeCanvas` 函式）
- Modify: `travel-atlas.html:560-606`（`renderGlobeCanvas`：呼叫 resize、線寬/pin 半徑乘上 `globeDpr`）
- Modify: `travel-atlas.html:616-661`（`attachGlobeInteractions`：新增 debounce resize 監聽）

- [ ] **Step 1: 新增 `globeDpr` 全域變數**

在 `travel-atlas.html:447` 的 `let globeDragging=false;` 後面加一行：

```javascript
let globeDragging=false;
let globeDpr=1;
```

- [ ] **Step 2: 新增 `resizeGlobeCanvas` 函式**

在 `travel-atlas.html:500` 的 `function drawMap(trips){` 前面插入：

```javascript
// Canvas backing resolution was previously hardcoded to 360x360 and scaled
// up by CSS (`.map-wrap canvas{width:100%}`), which is blurry on any
// devicePixelRatio>1 screen. Resize the backing store to match the CSS
// display size * dpr so coastlines/borders/rivers render crisp. globeDpr
// tracks how much larger than the original 360px baseline the canvas now
// is, so pixel-sized constants (line widths, pin radii) can scale with it.
function resizeGlobeCanvas(canvas){
  const rect=canvas.getBoundingClientRect();
  const cssW=rect.width;
  if(!cssW)return false;
  const dpr=window.devicePixelRatio||1;
  const target=Math.max(1,Math.round(cssW*dpr));
  if(canvas.width===target)return false;
  canvas.width=target;
  canvas.height=target;
  globeDpr=target/360;
  return true;
}

function drawMap(trips){
```

（也就是把新函式插在既有 `function drawMap(trips){` 那一行的正上方，`drawMap` 本身內容不變。）

- [ ] **Step 3: 在 `renderGlobeCanvas` 開頭呼叫 resize**

修改 `travel-atlas.html:560-563`，原本：

```javascript
function renderGlobeCanvas(){
  const canvas=document.getElementById('mapCanvas');
  if(!canvas)return;
  const ctx=canvas.getContext('2d');
```

改成：

```javascript
function renderGlobeCanvas(){
  const canvas=document.getElementById('mapCanvas');
  if(!canvas)return;
  resizeGlobeCanvas(canvas);
  const ctx=canvas.getContext('2d');
```

- [ ] **Step 4: 線寬與 pin 尺寸乘上 `globeDpr`**

修改 `travel-atlas.html:576-577`，原本：

```javascript
  ctx.strokeStyle='rgba(23,42,26,.5)';
  ctx.lineWidth=1;
```

改成：

```javascript
  ctx.strokeStyle='rgba(23,42,26,.5)';
  ctx.lineWidth=1*globeDpr;
```

修改 `travel-atlas.html:594`，原本：

```javascript
  ctx.strokeStyle='rgba(74,222,128,.4)';ctx.lineWidth=1.5;
```

改成：

```javascript
  ctx.strokeStyle='rgba(74,222,128,.4)';ctx.lineWidth=1.5*globeDpr;
```

修改 `travel-atlas.html:596-605`（pin 繪製區塊），原本：

```javascript
  globePins.forEach(pin=>{
    const p=projectGlobe(pin.lat,pin.lng,R,cx,cy);
    pin._sx=p.sx;pin._sy=p.sy;pin._visible=p.z>0.02;
    if(!pin._visible)return;
    const glowR=9*Math.max(0.4,p.z);
    const grad=ctx.createRadialGradient(p.sx,p.sy,0,p.sx,p.sy,glowR);
    grad.addColorStop(0,'rgba(244,201,93,.95)');grad.addColorStop(1,'rgba(244,201,93,0)');
    ctx.fillStyle=grad;ctx.beginPath();ctx.arc(p.sx,p.sy,glowR,0,Math.PI*2);ctx.fill();
    ctx.fillStyle='#FFF6DD';ctx.beginPath();ctx.arc(p.sx,p.sy,2.2,0,Math.PI*2);ctx.fill();
  });
```

改成：

```javascript
  globePins.forEach(pin=>{
    const p=projectGlobe(pin.lat,pin.lng,R,cx,cy);
    pin._sx=p.sx;pin._sy=p.sy;pin._visible=p.z>0.02;
    if(!pin._visible)return;
    const glowR=9*globeDpr*Math.max(0.4,p.z);
    const grad=ctx.createRadialGradient(p.sx,p.sy,0,p.sx,p.sy,glowR);
    grad.addColorStop(0,'rgba(244,201,93,.95)');grad.addColorStop(1,'rgba(244,201,93,0)');
    ctx.fillStyle=grad;ctx.beginPath();ctx.arc(p.sx,p.sy,glowR,0,Math.PI*2);ctx.fill();
    ctx.fillStyle='#FFF6DD';ctx.beginPath();ctx.arc(p.sx,p.sy,2.2*globeDpr,0,Math.PI*2);ctx.fill();
  });
```

- [ ] **Step 5: 新增 debounced resize 監聽**

修改 `travel-atlas.html:616-621`，原本：

```javascript
function attachGlobeInteractions(){
  const canvas=document.getElementById('mapCanvas');
  if(!canvas||canvas._globeBound)return;
  canvas._globeBound=true;
  const tip=document.getElementById('mapTip');
  let lastX=0,lastY=0,moved=false;
```

改成：

```javascript
function attachGlobeInteractions(){
  const canvas=document.getElementById('mapCanvas');
  if(!canvas||canvas._globeBound)return;
  canvas._globeBound=true;
  const tip=document.getElementById('mapTip');
  let lastX=0,lastY=0,moved=false;
  let resizeTimer=null;
  window.addEventListener('resize',()=>{
    clearTimeout(resizeTimer);
    resizeTimer=setTimeout(()=>{resizeGlobeCanvas(canvas);renderGlobeCanvas();},150);
  });
```

- [ ] **Step 6: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/travel-atlas.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_globe.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_globe.js && echo OK
```

Expected: `OK`

- [ ] **Step 7: Playwright 驗證解析度變化生效**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent" && (python3 -m http.server 8940 > /tmp/httpserver_globe.log 2>&1 &) ; sleep 1
```

用 Playwright MCP（`mcp__playwright__browser_navigate` 到 `http://localhost:8940/travel-atlas.html`，`mcp__playwright__browser_resize` 設成手機尺寸如 390×844），然後 `mcp__playwright__browser_evaluate`：

```javascript
() => {
  window.__origDpr = Object.getOwnPropertyDescriptor(window, 'devicePixelRatio');
  Object.defineProperty(window, 'devicePixelRatio', {value: 3, configurable: true});
  goTab('home');
  const canvas = document.getElementById('mapCanvas');
  renderGlobeCanvas();
  return {width: canvas.width, height: canvas.height, globeDpr};
}
```

Expected: `canvas.width`/`height` 約為 CSS 顯示寬度 × 3（不再是固定 360），`globeDpr` 明顯大於 1（例如手機寬度 356px 時約為 356×3/360 ≈ 2.97）。

再驗證拖曳 hit-test 沒有因解析度改變而壞掉（`attachGlobeInteractions` 的 pointerup 已經是用 `canvas.width/r.width` 算 scale，理論上自動相容，但要實際驗證）：

```javascript
() => {
  attachGlobeInteractions();
  const canvas = document.getElementById('mapCanvas');
  const rect = canvas.getBoundingClientRect();
  const pin = globePins[0];
  const p = projectGlobe(pin.lat, pin.lng, Math.min(canvas.width,canvas.height)/2*0.82, canvas.width/2, canvas.height/2);
  const clientX = rect.left + (p.sx / canvas.width) * rect.width;
  const clientY = rect.top + (p.sy / canvas.height) * rect.height;
  canvas.dispatchEvent(new PointerEvent('pointerdown', {clientX, clientY, pointerId:1, bubbles:true}));
  canvas.dispatchEvent(new PointerEvent('pointerup', {clientX, clientY, pointerId:1, bubbles:true}));
  const tip = document.getElementById('mapTip');
  return {tipVisible: tip.style.display === 'block', tipText: tip.textContent};
}
```

Expected: `tipVisible: true`，`tipText` 是第一個行程的標題（證明高解析度下點擊 pin 仍然準確命中）。

用 `mcp__playwright__browser_console_messages`（`level: "error"`）確認沒有新的 console error。

```bash
pkill -f "http.server 8940" 2>/dev/null
```

- [ ] **Step 8: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add travel-atlas.html
git commit -m "feat: render globe canvas at devicePixelRatio resolution"
```

---

### Task 2: 國界線（Natural Earth land boundary lines）

**Files:**
- Create（暫存，離線資料處理用，不進 git）: `/tmp/globe-detail/build_borders.py`
- Modify: `travel-atlas.html:441`（`CONTINENTS` 陣列後插入 `const BORDERS=[...]`）
- Modify: `travel-atlas.html:473-491`（新增 `densifyPolylines`、`DENSE_BORDERS`）
- Modify: `travel-atlas.html:532-559`（新增 `strokePolylineSet` 函式）
- Modify: `travel-atlas.html:560-608`（`renderGlobeCanvas`：繪製 `DENSE_BORDERS`）

**為什麼用 `ne_110m_admin_0_boundary_lines_land` 而不是 `ne_110m_admin_0_countries`：** 後者是完整國家外框多邊形，包含海岸線部分——但海岸線已經被 `CONTINENTS` 畫過了，重複畫一次只會疊加雜訊、浪費點數。前者是 Natural Earth 專門提供的「只有陸地上國與國交界」資料集，量少很多（全球只有 333 條線、RDP 簡化後約 1500 點），正好是我們要的「國界」。

- [ ] **Step 1: 下載資料並確認可用**

```bash
mkdir -p /tmp/globe-detail
curl -s "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_boundary_lines_land.geojson" -o /tmp/globe-detail/borders_land.geojson
python3 -c "
import json
d=json.load(open('/tmp/globe-detail/borders_land.geojson'))
print('features:', len(d['features']))
"
```

Expected: `features: 331`

- [ ] **Step 2: 寫離線 RDP 簡化腳本**

Write `/tmp/globe-detail/build_borders.py`:

```python
import json, math

def rdp(points, epsilon):
    if len(points) < 3:
        return points
    def perp_dist(pt, a, b):
        (x, y), (x1, y1), (x2, y2) = pt, a, b
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(x - x1, y - y1)
        t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
        t = max(0, min(1, t))
        px, py = x1 + t * dx, y1 + t * dy
        return math.hypot(x - px, y - py)
    dmax, idx = 0, 0
    for i in range(1, len(points) - 1):
        d = perp_dist(points[i], points[0], points[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > epsilon:
        left = rdp(points[:idx+1], epsilon)
        right = rdp(points[idx:], epsilon)
        return left[:-1] + right
    return [points[0], points[-1]]

def lines_of(geom):
    if geom["type"] == "LineString":
        return [geom["coordinates"]]
    return geom["coordinates"]  # MultiLineString

def fmt_lines(lines):
    out = []
    for line in lines:
        pts = ",".join(f"[{round(x,2)},{round(y,2)}]" for x, y in line)
        out.append(f"[{pts}]")
    return "[\n  " + ",\n  ".join(out) + "\n]"

raw = json.load(open("/tmp/globe-detail/borders_land.geojson"))
border_lines = []
for f in raw["features"]:
    for line in lines_of(f["geometry"]):
        lons = [p[0] for p in line]
        if max(lons) - min(lons) > 180:
            continue  # antimeridian-wrapping segment, skip (same guard used for the terrain overlay data)
        simplified = rdp(line, 0.3)
        if len(simplified) >= 2:
            border_lines.append(simplified)

with open("/tmp/globe-detail/BORDERS.js", "w") as f:
    f.write("const BORDERS=" + fmt_lines(border_lines) + ";\n")
print("borders: lines=", len(border_lines), "points=", sum(len(l) for l in border_lines))
```

- [ ] **Step 3: 執行並確認點數量級合理**

```bash
cd /tmp/globe-detail && python3 build_borders.py
```

Expected: `borders: lines= 333 points= 1501`（跟現有 `CONTINENTS` 的 881 點同數量級，不會拖累效能）

- [ ] **Step 4: 把產生的 `BORDERS` 陣列插入 travel-atlas.html**

讀取 `/tmp/globe-detail/BORDERS.js` 的內容，插入 `travel-atlas.html:441` 的 `CONTINENTS` 陣列結尾（`];`）之後、`// ─── 3D globe ───` 註解之前：

```javascript
];

const BORDERS=[
  ... (貼上 /tmp/globe-detail/BORDERS.js 產生的完整內容，去掉開頭的 `const BORDERS=` 只留陣列本體)
];

// ─── 3D globe ────────────────────────────────────────
```

（實際操作：用 Read 讀 `/tmp/globe-detail/BORDERS.js`，把裡面的陣列字面量原封不動貼進 `travel-atlas.html`，變數名保持 `BORDERS`。）

- [ ] **Step 5: 新增開放折線版本的密化函式**

`densifyRings()`（`travel-atlas.html:473`）是為封閉環設計的（`(i+1)%unit.length` 會把最後一點接回第一點），國界是開放折線，不能共用。在 `travel-atlas.html:491` 的 `const DENSE_MOUNTAINS=densifyRings(MOUNTAINS,MAX_EDGE_DEG_DRAG);` 後面加：

```javascript
const DENSE_MOUNTAINS=densifyRings(MOUNTAINS,MAX_EDGE_DEG_DRAG);
// Borders/rivers are open polylines, not closed rings — densifyRings()'s
// (i+1)%length wraparound would incorrectly connect each line's last point
// back to its first, so use this variant instead.
function densifyPolylines(lines,maxEdgeDeg){
  return lines.map(line=>{
    const unit=line.map(([lng,lat])=>sphereXYZ(lat,lng));
    const out=[];
    for(let i=0;i<unit.length-1;i++){
      const a=unit[i],b=unit[i+1];
      out.push(a);
      const dot=Math.max(-1,Math.min(1,a[0]*b[0]+a[1]*b[1]+a[2]*b[2]));
      const angDeg=Math.acos(dot)*180/Math.PI;
      const steps=Math.min(48,Math.ceil(angDeg/maxEdgeDeg));
      for(let s=1;s<steps;s++)out.push(slerp(a,b,s/steps));
    }
    out.push(unit[unit.length-1]);
    return out;
  });
}
const DENSE_BORDERS=densifyPolylines(BORDERS,MAX_EDGE_DEG_DRAG);
```

（用 `MAX_EDGE_DEG_DRAG`＝9°而非海岸線用的 3°：國界線本來就細，不需要跟海岸線一樣高的密化精度，且拖曳中固定跳過不畫，不需要額外的低密度版本。）

- [ ] **Step 6: 新增開放折線的描邊繪製函式**

在 `travel-atlas.html:559`（`fillRingSet` 函式結束的 `}` 之後、`function renderGlobeCanvas(){` 之前）加：

```javascript
function strokePolylineSet(ctx,lines,rot3d,proj3d,horizonPt){
  lines.forEach(line=>{
    const pts=line.map(rot3d);
    let path=[];
    const flush=()=>{
      if(path.length>1){
        ctx.beginPath();
        path.forEach(([x,y],i)=>i===0?ctx.moveTo(x,y):ctx.lineTo(x,y));
        ctx.stroke();
      }
      path=[];
    };
    for(let i=0;i<pts.length;i++){
      const cur=pts[i];
      const curVis=cur[2]>ZC;
      if(i>0){
        const prev=pts[i-1];
        const prevVis=prev[2]>ZC;
        if(curVis!==prevVis){
          const h=horizonPt(prev,cur);
          if(prevVis){path.push([h.sx,h.sy]);flush();}
          else{flush();path.push([h.sx,h.sy]);}
        }
      }
      if(curVis){const p=proj3d(cur);path.push([p.sx,p.sy]);}
    }
    flush();
  });
}
```

- [ ] **Step 7: 在 renderGlobeCanvas 裡畫國界**

修改 `travel-atlas.html:589-592`，原本：

```javascript
  if(!globeDragging){
    fillRingSet(ctx,DENSE_HIGHLANDS,()=>highland,rot3d,proj3d,horizonPt,false);
    fillRingSet(ctx,DENSE_MOUNTAINS,()=>mountain,rot3d,proj3d,horizonPt,false);
  }
```

改成：

```javascript
  if(!globeDragging){
    fillRingSet(ctx,DENSE_HIGHLANDS,()=>highland,rot3d,proj3d,horizonPt,false);
    fillRingSet(ctx,DENSE_MOUNTAINS,()=>mountain,rot3d,proj3d,horizonPt,false);
    ctx.strokeStyle='rgba(255,255,255,.25)';
    ctx.lineWidth=0.6*globeDpr;
    strokePolylineSet(ctx,DENSE_BORDERS,rot3d,proj3d,horizonPt);
  }
```

- [ ] **Step 8: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/travel-atlas.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_globe2.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_globe2.js && echo OK
```

Expected: `OK`

- [ ] **Step 9: Playwright 視覺驗證**

起本機伺服器、用 Playwright 開啟、切到首頁 tab、轉動地球儀到至少 3 個不同角度（含會露出多國交界的角度，如歐洲、非洲）分別截圖，肉眼確認：
1. 國界線出現在陸地上，顏色是淡白色細線，跟地形疊加色不衝突
2. 旋轉地球儀時國界沒有在地平線邊緣出現對角線瑕疵（這是密化沒做對時的典型症狀）
3. 拖曳地球儀時（`globeDragging=true`）國界線會消失，放開後恢復——用 `browser_evaluate` 設定 `globeDragging=true; renderGlobeCanvas();` 截圖確認消失，再設 `false` 重繪確認恢復

```javascript
() => { globeView.rotLon=20; globeView.tilt=18; renderGlobeCanvas(); return 'reset'; }
```

然後截圖，再：

```javascript
() => { globeView.rotLon=-80; globeView.tilt=10; renderGlobeCanvas(); return 'rotated'; }
```

再截圖比對。

- [ ] **Step 10: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add travel-atlas.html
git commit -m "feat: add country border overlay to globe from Natural Earth data"
```

---

### Task 3: 主要河流（Natural Earth rivers）

**Files:**
- Create（暫存）: `/tmp/globe-detail/build_rivers.py`
- Modify: `travel-atlas.html`（`BORDERS` 陣列後插入 `const RIVERS=[...]`）
- Modify: `travel-atlas.html`（`DENSE_BORDERS` 那行後新增 `DENSE_RIVERS`）
- Modify: `renderGlobeCanvas` 內新增河流描邊

**注意：** Natural Earth 110m 精度的河流資料集只有 13 條（`scalerank` 1-2 的世界最主要河流：Brahmaputra、Mekong、Ob、Peace、Donau、Paraná、Congo、Lena、Chang、Nile、Amazonas、Mississippi、Yangtze），比原本 spec 估計的「20-30 條」少——110m 這個精度等級 Natural Earth 官方就只标注這些主要河流，這是資料集本身的限制，不是簡化流程篩掉的。

- [ ] **Step 1: 下載資料並確認**

```bash
curl -s "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_rivers_lake_centerlines.geojson" -o /tmp/globe-detail/rivers.geojson
python3 -c "
import json
d=json.load(open('/tmp/globe-detail/rivers.geojson'))
print('features:', len(d['features']))
print('names:', [f['properties']['name'] for f in d['features']])
"
```

Expected: `features: 13`

- [ ] **Step 2: 寫離線 RDP 簡化腳本**

Write `/tmp/globe-detail/build_rivers.py`:

```python
import json, math

def rdp(points, epsilon):
    if len(points) < 3:
        return points
    def perp_dist(pt, a, b):
        (x, y), (x1, y1), (x2, y2) = pt, a, b
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(x - x1, y - y1)
        t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
        t = max(0, min(1, t))
        px, py = x1 + t * dx, y1 + t * dy
        return math.hypot(x - px, y - py)
    dmax, idx = 0, 0
    for i in range(1, len(points) - 1):
        d = perp_dist(points[i], points[0], points[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > epsilon:
        left = rdp(points[:idx+1], epsilon)
        right = rdp(points[idx:], epsilon)
        return left[:-1] + right
    return [points[0], points[-1]]

def fmt_lines(lines):
    out = []
    for line in lines:
        pts = ",".join(f"[{round(x,2)},{round(y,2)}]" for x, y in line)
        out.append(f"[{pts}]")
    return "[\n  " + ",\n  ".join(out) + "\n]"

raw = json.load(open("/tmp/globe-detail/rivers.geojson"))
river_lines = []
for f in raw["features"]:
    line = f["geometry"]["coordinates"]
    lons = [p[0] for p in line]
    if max(lons) - min(lons) > 180:
        continue
    simplified = rdp(line, 0.15)
    if len(simplified) >= 2:
        river_lines.append(simplified)

with open("/tmp/globe-detail/RIVERS.js", "w") as f:
    f.write("const RIVERS=" + fmt_lines(river_lines) + ";\n")
print("rivers: lines=", len(river_lines), "points=", sum(len(l) for l in river_lines))
```

- [ ] **Step 3: 執行**

```bash
cd /tmp/globe-detail && python3 build_rivers.py
```

Expected: `rivers: lines= 13 points= 338`

- [ ] **Step 4: 把 `RIVERS` 陣列插入 travel-atlas.html**

讀取 `/tmp/globe-detail/RIVERS.js`，插入到 `BORDERS` 陣列結尾（`];`）之後、`// ─── 3D globe ───` 註解之前，變數名保持 `RIVERS`。

- [ ] **Step 5: 新增 `DENSE_RIVERS`**

在 `const DENSE_BORDERS=densifyPolylines(BORDERS,MAX_EDGE_DEG_DRAG);` 這行後面加：

```javascript
const DENSE_RIVERS=densifyPolylines(RIVERS,MAX_EDGE_DEG_DRAG);
```

- [ ] **Step 6: 在 renderGlobeCanvas 裡畫河流**

修改 Task 2 Step 7 改完的區塊，原本：

```javascript
  if(!globeDragging){
    fillRingSet(ctx,DENSE_HIGHLANDS,()=>highland,rot3d,proj3d,horizonPt,false);
    fillRingSet(ctx,DENSE_MOUNTAINS,()=>mountain,rot3d,proj3d,horizonPt,false);
    ctx.strokeStyle='rgba(255,255,255,.25)';
    ctx.lineWidth=0.6*globeDpr;
    strokePolylineSet(ctx,DENSE_BORDERS,rot3d,proj3d,horizonPt);
  }
```

改成：

```javascript
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

- [ ] **Step 7: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/travel-atlas.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=)[^>])*>(.*?)</script>', content, re.S)
open('/tmp/_check_globe3.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_globe3.js && echo OK
```

Expected: `OK`

- [ ] **Step 8: Playwright 視覺驗證**

旋轉地球儀到能看到長江/黃河/尼羅河/亞馬遜河等區域，截圖確認淺藍色河流線出現在正確位置（例如尼羅河應該是從東非往北流入地中海的一條線，不會憑空出現在海洋中央）。

- [ ] **Step 9: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add travel-atlas.html
git commit -m "feat: add major river overlay to globe from Natural Earth data"
```

---

### Task 4: 整體效能驗證

**Files:** 無檔案修改，純驗證。

**背景：** 前面幾次地球儀改動都有做「拖曳 100 幀 vs 靜止 100 幀」的效能基準測試（比較拖曳中是否維持流暢），這次新增了約 1839 個點（國界 1501 + 河流 338），雖然都放在 `!globeDragging` 區塊內（拖曳中完全跳過），但仍要驗證靜止畫面重繪沒有明顯變慢，以及 DPR 提升後（實體像素變多）整體渲染沒有意外變慢。

- [ ] **Step 1: 起本機伺服器並用 Playwright 開啟**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent" && (python3 -m http.server 8941 > /tmp/httpserver_globe2.log 2>&1 &) ; sleep 1
```

用 `mcp__playwright__browser_navigate` 開啟 `http://localhost:8941/travel-atlas.html`，`mcp__playwright__browser_resize` 設成 390×844（手機尺寸），切到首頁 tab。

- [ ] **Step 2: 執行效能基準測試**

```javascript
() => {
  function bench(drag){ globeDragging = drag; let t0=performance.now(); for(let i=0;i<100;i++){ globeView.rotLon+=1; renderGlobeCanvas(); } return performance.now()-t0; }
  bench(true); bench(false); // warmup
  const drag1=bench(true), idle1=bench(false), drag2=bench(true), idle2=bench(false);
  return {drag1,idle1,drag2,idle2};
}
```

Expected: `drag1`/`drag2`（拖曳模式，跳過國界/河流/地形）明顯低於或接近 `idle1`/`idle2`（靜止模式，畫全部圖層），且 idle 模式 100 幀耗時應維持在合理範圍（作為參考基準：上次只有地形疊加時 idle 模式 100 幀約 15ms；這次多了國界+河流，允許上升，但不應該上升超過 3-5 倍，例如超過 60ms 就代表有效能問題需要排查）。

- [ ] **Step 3: console error 檢查**

用 `mcp__playwright__browser_console_messages`（`level: "error"`）確認整個驗證過程中沒有新的 console error。

- [ ] **Step 4: 清理**

```bash
pkill -f "http.server 8941" 2>/dev/null
```

清掉 Playwright 產生的截圖檔案（在 `.playwright-mcp/` 目錄下，`git status` 確認這些不會被 commit）。

---

## Self-Review 紀錄

- **Spec coverage：** Canvas DPR 解析度（Task 1）、國界線（Task 2）、主要河流（Task 3）、效能驗證（Task 4）都對應到 spec 的「架構」四個小節。名稱標注一項 spec 已明確標註「不需新開發」，故本計畫沒有對應 Task。
- **Placeholder scan：** 每個 Task 的資料處理腳本、程式碼修改、指令都是完整可執行內容，沒有 TBD。
- **Type/命名一致性：** `BORDERS`/`RIVERS`（資料）、`DENSE_BORDERS`/`DENSE_RIVERS`（密化後）、`densifyPolylines`/`strokePolylineSet`（新函式）在 Task 2 定義、Task 3 沿用，命名前後一致。`globeDpr` 在 Task 1 定義，Task 2/3 的線寬設定沿用同一個變數名。
