# 地球儀升級為真實衛星貼圖 3D 球體 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `travel-atlas.html` 的地球儀從手刻 Canvas 2D 向量渲染換成 three.js（WebGL）+ 真實地球日間貼圖，保留國界線疊加、拖曳旋轉、縮放、pin 點擊互動。

**Architecture:** three.js 透過 CDN `importmap` 以 ES module 載入並掛到 `window.THREE`/`window.OrbitControls`，讓既有的 classic `<script>`（定義 `drawMap`/`mapZoom` 等被 HTML `onclick` 呼叫的全域函式）維持不變的呼叫方式。地球本體是貼了真實貼圖的 `SphereGeometry`，國界線用既有 `BORDERS` 經緯度資料轉成 3D `Line` 疊在球面上，pin 用 `Sprite`+`Raycaster` 做點擊判定，拖曳/縮放交給 three.js 官方 `OrbitControls`。

**Tech Stack:** three.js 0.165.0（CDN, ES module）、`OrbitControls` addon、Solar System Scope 2K 地球貼圖（外部圖片檔案）。

---

## 背景知識（開始前必讀）

- `travel-atlas.html` 是 single-file PWA，沒有測試框架，驗證一律用 `node --check` 語法檢查 + Playwright 瀏覽器內視覺/互動驗證。
- **這個計畫已經被完整驗證過一次**：本文件裡的每一段程式碼都在本機起服務、用 Playwright 實際跑過（貼圖正確顯示、地理位置準確——東京 pin 準確落在日本、國界線可見、pin 點擊命中、拖曳/縮放、canvas 被替換時不留殭屍渲染迴圈、全程 0 console error）。照抄本文件的程式碼即可，不需要重新設計。
- **測試 app 需要種假資料才能看到地球儀**：這個 app 進入畫面前需要 Firebase 設定（存在 `localStorage['travel_atlas_cfg']`，格式 `{"url":"...","bucket":"..."}`）且要有至少一筆行程資料（透過 `onTripsUpdate(trips)` 灌入）才會建立 `#mapCanvas` 並呼叫 `drawMap()`。正式環境的 Firebase 設定值：RTDB `https://travel-atlas-ff15e-default-rtdb.asia-southeast1.firebasedatabase.app`、Storage bucket `travel-atlas-ff15e.firebasestorage.app`。
- 地球儀相關的 tab 是 `'atlas'`（用 `goTab('atlas')` 切換，不是 `'home'`）。
- **重要的既有限制**：`#mapCanvas` 這個 DOM 元素會在每次 `renderAtlas()` 執行時被整個 `innerHTML` 模板重新生成（Firebase 資料一有更新就會發生），也就是舊的 canvas 元素會被丟棄、換一個全新的 canvas（id 相同但是不同的 DOM 物件）。所以三.js 的 renderer/scene 不能只在頁面載入時初始化一次就假設 canvas 永遠不變——`drawMap()` 每次被呼叫都要檢查「現在的 canvas 元素跟上次綁定的是不是同一個」，不同的話要重新建立整個 three.js 場景並取消舊的動畫迴圈（`cancelAnimationFrame`），否則會有殭屍渲染迴圈一直在背景畫一個已經從 DOM 移除的 canvas。這個計畫的程式碼已經處理了這個問題（`globeBoundCanvas` 這個變數），不要拿掉這段邏輯。

---

### Task 1: 透過 CDN 載入 three.js + OrbitControls

**Files:**
- Modify: `travel-atlas.html`（`<head>` 內，firebase script 標籤之後）

- [ ] **Step 1: 找到 firebase script 標籤區塊**

用 `grep -n 'firebase-storage-compat.js' travel-atlas.html` 找到這一行：

```html
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-storage-compat.js"></script>
```

- [ ] **Step 2: 在這行後面插入 importmap + three.js 載入用的 module script**

```html
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-storage-compat.js"></script>
<script type="importmap">
{
  "imports": {
    "three": "https://unpkg.com/three@0.165.0/build/three.module.js",
    "three/addons/": "https://unpkg.com/three@0.165.0/examples/jsm/"
  }
}
</script>
<script type="module">
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
window.THREE = THREE;
window.OrbitControls = OrbitControls;
window.dispatchEvent(new Event("three-ready"));
</script>
```

（`window.THREE`/`window.OrbitControls` 讓後面主要的 classic `<script>`（非 module，裡面定義了一堆被 `onclick="..."` 呼叫的全域函式）可以直接當全域變數使用，不用把整個檔案改成 module。`three-ready` 事件是給 Task 4 的 `drawMap()` 用的：如果 three.js 還沒載入完成就被呼叫，先訂閱這個事件、載入完成後自動重試一次。）

- [ ] **Step 2: 語法檢查（確認沒有破壞既有的主要 script block）**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/travel-atlas.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=|type=\"importmap\"|type=\"module\")[^>])*>(.*?)</script>', content, re.S)
print(len(scripts), 'main script blocks')
open('/tmp/_check_globe3d_1.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_globe3d_1.js && echo OK
```

Expected: `1 main script blocks` 、`OK`

- [ ] **Step 3: Playwright 驗證 three.js 有載入**

起本機伺服器（例如 port 8951），Playwright 開啟，執行：

```javascript
async () => {
  await new Promise(r=>setTimeout(r,500));
  return {hasThree: !!window.THREE, hasOrbit: !!window.OrbitControls};
}
```

Expected: `{hasThree: true, hasOrbit: true}`

- [ ] **Step 4: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add travel-atlas.html
git commit -m "feat: load three.js via CDN importmap for globe WebGL upgrade"
```

---

### Task 2: 準備地球貼圖資產

**Files:**
- Create: `Jenna_agent/assets/2k_earth_daymap.jpg`

- [ ] **Step 1: 下載貼圖**

```bash
mkdir -p "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/assets"
curl -sL "https://www.solarsystemscope.com/textures/download/2k_earth_daymap.jpg" \
  -o "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/assets/2k_earth_daymap.jpg"
file "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/assets/2k_earth_daymap.jpg"
```

Expected: `JPEG image data ... 2048x1024`（實測檔案大小約 463KB，Solar System Scope CC BY 4.0 授權）

- [ ] **Step 2: Commit（圖片是二進位檔案，直接加進 git）**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add assets/2k_earth_daymap.jpg
git commit -m "feat: add real earth daymap texture asset for WebGL globe"
```

---

### Task 3: 刪除舊的 Canvas 2D 向量地球儀，換成 three.js 版本

**Files:**
- Modify: `travel-atlas.html`（刪除 `CONTINENTS`/`HIGHLANDS`/`MOUNTAINS`/`RIVERS` 資料與整套向量渲染函式，保留 `BORDERS` 資料，新增 three.js 場景邏輯）

**這是本計畫最大的一步，用 Python 腳本做精確的區塊刪除+替換（這些資料陣列每行內容都是幾百字的座標數字，用手動比對文字容易出錯，用程式碼定位比較可靠）。已經在測試環境跑過這個腳本並確認產生的檔案語法正確、瀏覽器裡功能正常，照抄即可。**

- [ ] **Step 1: 建立要插入的新 three.js 程式碼區塊**

Write `/tmp/globe3d_new_block.js`（這段內容已經過瀏覽器實測驗證，包含：座標轉換、國界線球面密化、pin sprite、raycasting 點擊判定、resize 處理、three.js 場景初始化含 canvas 替換偵測、`drawMap`/`mapZoom` 兩個外部呼叫的函式簽章維持不變）：

```javascript
// ─── 3D globe (three.js + real earth texture) ─────────
let globePins=[];
let globeScene=null,globeCamera=null,globeRenderer=null,globeControls=null;
let globeRaycaster=null,globePinObjects=[],globeMesh=null;
let globeAnimId=null,globeBoundCanvas=null,globeResizeTimer=null;
const GLOBE_RADIUS=1;
const GLOBE_INITIAL_DISTANCE=3.2;
const GLOBE_MIN_DISTANCE=1.4;
const GLOBE_MAX_DISTANCE=5.5;
const BORDER_MAX_EDGE_DEG=6;
let _lastZoomPct=null;

// Standard lat/lng -> Vector3 mapping that matches SphereGeometry's default
// UV unwrap for an equirectangular texture (lng -180..180 maps around the
// seam behind the +X axis). Radius 1 = unit sphere; scale via multiplyScalar
// for border/pin placement slightly above the textured surface.
function latLngToVector3(lat,lng,radius){
  const phi=(90-lat)*Math.PI/180;
  const theta=(lng+180)*Math.PI/180;
  return new THREE.Vector3(
    -radius*Math.sin(phi)*Math.cos(theta),
    radius*Math.cos(phi),
    radius*Math.sin(phi)*Math.sin(theta)
  );
}
function slerpVec3(a,b,t){
  const dot=Math.max(-1,Math.min(1,a.dot(b)));
  const theta=Math.acos(dot);
  if(theta<1e-6)return a.clone();
  const s=Math.sin(theta);
  const w1=Math.sin((1-t)*theta)/s,w2=Math.sin(t*theta)/s;
  return new THREE.Vector3(a.x*w1+b.x*w2,a.y*w1+b.y*w2,a.z*w1+b.z*w2);
}
// Densify a [lng,lat] polyline via spherical interpolation before drawing it
// as straight THREE.Line segments — without this, the chord between two
// sparse RDP-simplified points cuts inside the sphere instead of hugging its
// surface (same problem the old Canvas 2D renderer's densifyRings solved).
function densifyBorderLine(line,radius,maxEdgeDeg){
  const unit=line.map(([lng,lat])=>latLngToVector3(lat,lng,1));
  const out=[];
  for(let i=0;i<unit.length-1;i++){
    const a=unit[i],b=unit[i+1];
    out.push(a);
    const dot=Math.max(-1,Math.min(1,a.dot(b)));
    const angDeg=Math.acos(dot)*180/Math.PI;
    const steps=Math.min(48,Math.ceil(angDeg/maxEdgeDeg));
    for(let s=1;s<steps;s++)out.push(slerpVec3(a,b,s/steps));
  }
  out.push(unit[unit.length-1]);
  return out.map(p=>p.clone().multiplyScalar(radius));
}

let _pinSpriteMat=null;
function buildPinSpriteMaterial(){
  if(_pinSpriteMat)return _pinSpriteMat;
  const c=document.createElement('canvas');
  c.width=64;c.height=64;
  const cctx=c.getContext('2d');
  const g=cctx.createRadialGradient(32,32,0,32,32,32);
  g.addColorStop(0,'rgba(255,246,221,1)');
  g.addColorStop(0.25,'rgba(244,201,93,.95)');
  g.addColorStop(1,'rgba(244,201,93,0)');
  cctx.fillStyle=g;cctx.beginPath();cctx.arc(32,32,32,0,Math.PI*2);cctx.fill();
  const tex=new THREE.CanvasTexture(c);
  _pinSpriteMat=new THREE.SpriteMaterial({map:tex,transparent:true,depthTest:true});
  return _pinSpriteMat;
}

function updateGlobePins(){
  if(!globeScene)return;
  globePinObjects.forEach(obj=>globeScene.remove(obj));
  globePinObjects=[];
  const mat=buildPinSpriteMaterial();
  globePins.forEach(pin=>{
    const sprite=new THREE.Sprite(mat);
    sprite.position.copy(latLngToVector3(pin.lat,pin.lng,GLOBE_RADIUS*1.02));
    sprite.scale.set(0.09,0.09,1);
    sprite.userData.pin=pin;
    globeScene.add(sprite);
    globePinObjects.push(sprite);
  });
}

function onGlobeCanvasClick(e){
  const canvas=globeBoundCanvas;
  if(!canvas)return;
  const rect=canvas.getBoundingClientRect();
  const mouse=new THREE.Vector2(
    ((e.clientX-rect.left)/rect.width)*2-1,
    -((e.clientY-rect.top)/rect.height)*2+1
  );
  globeRaycaster.setFromCamera(mouse,globeCamera);
  const hits=globeRaycaster.intersectObjects(globePinObjects);
  const tip=document.getElementById('mapTip');
  if(!tip)return;
  if(hits.length){
    const pin=hits[0].object.userData.pin;
    const screenPos=hits[0].object.position.clone().project(globeCamera);
    tip.style.display='block';
    tip.style.left=((screenPos.x+1)/2*100)+'%';
    tip.style.top=((1-screenPos.y)/2*100)+'%';
    tip.textContent=pin.title;
    tip.onclick=()=>openTripDetail(pin.id);
  }else{
    tip.style.display='none';
  }
}

function onGlobeResize(){
  clearTimeout(globeResizeTimer);
  globeResizeTimer=setTimeout(()=>{
    const canvas=globeBoundCanvas;
    if(!canvas||!globeRenderer)return;
    const rect=canvas.getBoundingClientRect();
    if(!rect.width)return;
    globeCamera.aspect=rect.width/rect.height;
    globeCamera.updateProjectionMatrix();
    globeRenderer.setSize(rect.width,rect.height,false);
  },150);
}

function initGlobeScene(canvas){
  if(globeAnimId){cancelAnimationFrame(globeAnimId);globeAnimId=null;}
  if(globeRenderer){globeRenderer.dispose();}
  globeScene=new THREE.Scene();
  const rect=canvas.getBoundingClientRect();
  const aspect=(rect.width||1)/(rect.height||1);
  globeCamera=new THREE.PerspectiveCamera(45,aspect,0.1,100);
  globeCamera.position.set(0,0,GLOBE_INITIAL_DISTANCE);
  globeRenderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true});
  globeRenderer.setPixelRatio(window.devicePixelRatio||1);
  globeRenderer.setSize(rect.width||canvas.clientWidth||360,rect.height||canvas.clientHeight||360,false);

  const geo=new THREE.SphereGeometry(GLOBE_RADIUS,64,64);
  globeMesh=new THREE.Mesh(geo,new THREE.MeshBasicMaterial({color:0x14314a}));
  globeScene.add(globeMesh);
  new THREE.TextureLoader().load(
    'assets/2k_earth_daymap.jpg',
    tex=>{globeMesh.material=new THREE.MeshBasicMaterial({map:tex});},
    undefined,
    ()=>{/* keep the placeholder navy sphere on load failure */}
  );

  const borderGroup=new THREE.Group();
  BORDERS.forEach(line=>{
    const pts=densifyBorderLine(line,GLOBE_RADIUS*1.001,BORDER_MAX_EDGE_DEG);
    const geom=new THREE.BufferGeometry().setFromPoints(pts);
    const mat=new THREE.LineBasicMaterial({color:0xffffff,transparent:true,opacity:0.35});
    borderGroup.add(new THREE.Line(geom,mat));
  });
  globeScene.add(borderGroup);

  globeControls=new OrbitControls(globeCamera,globeRenderer.domElement);
  globeControls.enablePan=false;
  globeControls.enableDamping=true;
  globeControls.dampingFactor=0.1;
  globeControls.minDistance=GLOBE_MIN_DISTANCE;
  globeControls.maxDistance=GLOBE_MAX_DISTANCE;
  globeControls.rotateSpeed=0.5;

  globeRaycaster=new THREE.Raycaster();
  canvas.addEventListener('click',onGlobeCanvasClick);
  window.addEventListener('resize',onGlobeResize);

  function animate(){
    globeAnimId=requestAnimationFrame(animate);
    globeControls.update();
    globeRenderer.render(globeScene,globeCamera);
    const dist=globeCamera.position.distanceTo(globeControls.target);
    const pct=Math.round((GLOBE_INITIAL_DISTANCE/dist)*100);
    if(pct!==_lastZoomPct){
      _lastZoomPct=pct;
      const lbl=document.getElementById('mapZoomLabel');
      if(lbl)lbl.textContent=pct+'%';
    }
  }
  animate();
}

function drawMap(trips){
  globePins=trips.filter(t=>t.lat!=null&&t.lng!=null).map(t=>({lat:t.lat,lng:t.lng,title:t.title,id:t.id}));
  if(!window.THREE||!window.OrbitControls){
    window.addEventListener('three-ready',()=>drawMap(trips),{once:true});
    return;
  }
  const canvas=document.getElementById('mapCanvas');
  if(!canvas)return;
  if(canvas!==globeBoundCanvas){
    initGlobeScene(canvas);
    globeBoundCanvas=canvas;
  }
  updateGlobePins();
}

function mapZoom(factor){
  if(!globeControls||!globeCamera)return;
  const dir=new THREE.Vector3().subVectors(globeCamera.position,globeControls.target);
  const newLen=Math.max(GLOBE_MIN_DISTANCE,Math.min(GLOBE_MAX_DISTANCE,dir.length()/factor));
  dir.setLength(newLen);
  globeCamera.position.copy(globeControls.target).add(dir);
  globeControls.update();
}
```

- [ ] **Step 2: 執行刪除+替換腳本**

Write `/tmp/globe3d_splice.py`:

```python
path = "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/travel-atlas.html"
lines = open(path, encoding='utf-8').readlines()

# Cut 1: remove the comment header + CONTINENTS + HIGHLANDS + MOUNTAINS
# arrays (everything between the "Simplified world landmass outlines"
# comment and the start of the BORDERS array, which is kept as-is).
start1 = end1 = None
for i, l in enumerate(lines):
    if l.startswith('// Simplified world landmass outlines'):
        start1 = i
    if l.rstrip('\n') == 'const BORDERS=[':
        end1 = i
        break
assert start1 is not None and end1 is not None, "cut1 anchors not found"

# Cut 2: remove RIVERS array through the end of the old
# attachGlobeInteractions() function (the entire old Canvas 2D rendering
# pipeline), to be replaced with the new three.js block.
start2 = end2 = None
for i, l in enumerate(lines):
    if l.rstrip('\n') == 'const RIVERS=[':
        start2 = i
    if start2 is not None and l.rstrip('\n') == "  },{passive:false});":
        end2 = i + 1  # the closing '}' of attachGlobeInteractions
        break
assert start2 is not None and end2 is not None, "cut2 anchors not found"
assert lines[end2].rstrip('\n') == '}', f"expected closing brace, got: {lines[end2]!r}"

new_block = open('/tmp/globe3d_new_block.js', encoding='utf-8').read()

out = lines[:start1] + lines[end1:start2] + [new_block] + lines[end2+1:]
open(path, 'w', encoding='utf-8').writelines(out)
print(f"cut1: removed {end1-start1} lines (comment+CONTINENTS+HIGHLANDS+MOUNTAINS)")
print(f"cut2: removed {end2-start2+1} lines (RIVERS through old attachGlobeInteractions)")
print(f"new file: {len(out)} lines")
```

Run:

```bash
python3 /tmp/globe3d_splice.py
```

Expected output:
```
cut1: removed 53 lines (comment+CONTINENTS+HIGHLANDS+MOUNTAINS)
cut2: removed 385 lines (RIVERS through old attachGlobeInteractions)
new file: 1320 lines
```

(如果數字不一樣，代表 `travel-atlas.html` 從寫這份計畫之後又被改過，先用 `grep -n "^// Simplified world landmass outlines\|^const BORDERS=\[\|^const RIVERS=\[\|passive:false" travel-atlas.html` 確認這幾個錨點還在、位置合理，再繼續。)

- [ ] **Step 3: 確認舊符號都清乾淨了**

```bash
grep -n "renderGlobeCanvas\|attachGlobeInteractions\|globeView\b\|sphereXYZ\|resizeGlobeCanvas\|fillRingSet\|fillFeatheredRingSet\|strokePolylineSet\|tracePath\|densifyRings\|globeDragging\|globeDpr\|^const CONTINENTS\|^const HIGHLANDS\|^const MOUNTAINS\|^const RIVERS\|projectGlobe\|buildGlobeGradients" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/travel-atlas.html"
```

Expected: 沒有任何符合的行（空輸出）。

- [ ] **Step 4: 確認 `BORDERS` 資料還在**

```bash
grep -c "^const BORDERS=\[" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/travel-atlas.html"
```

Expected: `1`

- [ ] **Step 5: 語法檢查**

```bash
python3 -c "
import re
content = open('/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/travel-atlas.html', encoding='utf-8').read()
scripts = re.findall(r'<script(?:(?!src=|type=\"importmap\"|type=\"module\")[^>])*>(.*?)</script>', content, re.S)
print(len(scripts), 'main script blocks')
open('/tmp/_check_globe3d_2.js','w',encoding='utf-8').write(scripts[0])
"
node --check /tmp/_check_globe3d_2.js && echo OK
```

Expected: `1 main script blocks`、`OK`

- [ ] **Step 6: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add travel-atlas.html
git commit -m "feat: replace Canvas 2D vector globe with three.js real-texture globe"
```

---

### Task 4: 端對端驗證

**Files:** 無檔案修改，純驗證。

- [ ] **Step 1: 起本機伺服器並種假資料**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent" && (python3 -m http.server 8952 > /tmp/httpserver_globe3d.log 2>&1 &) ; sleep 1
```

用 Playwright 開啟 `http://localhost:8952/travel-atlas.html`，`browser_resize` 設 390×844。用 `browser_evaluate` 種 Firebase 設定並 reload：

```javascript
() => {
  localStorage.setItem('travel_atlas_cfg', JSON.stringify({
    url: 'https://travel-atlas-ff15e-default-rtdb.asia-southeast1.firebasedatabase.app',
    bucket: 'travel-atlas-ff15e.firebasestorage.app'
  }));
  return 'seeded';
}
```

重新 `browser_navigate` 到同一個網址（讓 config 生效），然後灌一筆測試行程資料並切到 atlas tab：

```javascript
async () => {
  const trips = {
    t1: {title:'🇯🇵東京', lat:35.6762, lng:139.6503, region:'east-asia', startDate:'2024-01-01', endDate:'2024-01-05'},
    t2: {title:'🇫🇷巴黎', lat:48.8566, lng:2.3522, region:'europe', startDate:'2024-02-01', endDate:'2024-02-05'}
  };
  onTripsUpdate(trips);
  goTab('atlas');
  await new Promise(r=>setTimeout(r,1200));
  return {hasThree: !!window.THREE, canvasExists: !!document.getElementById('mapCanvas')};
}
```

Expected: `{hasThree: true, canvasExists: true}`

- [ ] **Step 2: 視覺驗證真實貼圖 + 地理位置**

截圖，肉眼確認：(a) 球體顯示真實地球紋理（海洋藍、陸地綠棕、雲層白，不是單色球），(b) 東京 pin（金色發光點）落在日本列島上，不是隨機位置或海裡。

- [ ] **Step 3: 驗證國界線**

用 `mapZoom(3)` 放大到某個大陸區域，截圖確認可以看到淡白色國界線疊在貼圖上（貼圖本身沒有政治國界，這條線是額外疊加的 `BORDERS` 資料）。

- [ ] **Step 4: 驗證 pin 點擊命中**

```javascript
() => {
  const canvas = document.getElementById('mapCanvas');
  const rect = canvas.getBoundingClientRect();
  const pinObj = globePinObjects.find(o=>o.userData.pin.title.includes('東京'));
  const proj = pinObj.position.clone().project(globeCamera);
  const x = rect.left + (proj.x+1)/2*rect.width;
  const y = rect.top + (1-proj.y)/2*rect.height;
  canvas.dispatchEvent(new MouseEvent('click', {clientX:x, clientY:y, bubbles:true}));
  const tip = document.getElementById('mapTip');
  return {tipVisible: tip.style.display==='block', tipText: tip.textContent};
}
```

Expected: `{tipVisible: true, tipText: "🇯🇵東京"}`

- [ ] **Step 5: 驗證 canvas 替換時不留殭屍渲染迴圈**

```javascript
async () => {
  const oldCanvas = document.getElementById('mapCanvas');
  const before = globeAnimId;
  onTripsUpdate({
    t1: {title:'🇯🇵東京', lat:35.6762, lng:139.6503, region:'east-asia', startDate:'2024-01-01', endDate:'2024-01-05'},
    t2: {title:'🇫🇷巴黎', lat:48.8566, lng:2.3522, region:'europe', startDate:'2024-02-01', endDate:'2024-02-05'},
    t3: {title:'🇦🇺雪梨', lat:-33.8688, lng:151.2093, region:'oceania', startDate:'2024-03-01', endDate:'2024-03-05'}
  });
  await new Promise(r=>setTimeout(r,400));
  const newCanvas = document.getElementById('mapCanvas');
  return {
    canvasReplaced: oldCanvas !== newCanvas,
    boundToNew: newCanvas === globeBoundCanvas,
    animIdChanged: before !== globeAnimId,
    pinCount: globePinObjects.length
  };
}
```

Expected: `{canvasReplaced: true, boundToNew: true, animIdChanged: true, pinCount: 3}`

- [ ] **Step 6: 拖曳旋轉 + 縮放按鈕驗證**

模擬拖曳（`pointerdown`→數次`pointermove`→`pointerup`，帶 `bubbles:true`+`pointerId`），確認畫面角度有變化。點擊 `+`/`-` 按鈕（`mapZoom(1.5)`/`mapZoom(1/1.5)`），確認 `mapZoomLabel` 的百分比數字有變化、球體視覺大小也跟著變。

- [ ] **Step 7: Console 錯誤檢查**

用 `mcp__playwright__browser_console_messages`（`level:"error"`，`all:true`）確認整個驗證過程 0 error。

- [ ] **Step 8: 清理**

```bash
pkill -f "http.server 8952" 2>/dev/null
```

告知使用者若有測試截圖殘留在專案根目錄，需要使用者自己刪除（`rm` 在這個環境會被沙盒權限擋下）。

- [ ] **Step 9: 提醒部署注意事項（不用執行，寫進最終回報給使用者）**

`assets/2k_earth_daymap.jpg` 是新增的外部圖片檔案。之後同步到 `netlify-travel-atlas/` 部署資料夾時，除了複製 `travel-atlas.html`→`index.html`，也要把 `assets/2k_earth_daymap.jpg` 複製過去（相對路徑 `assets/2k_earth_daymap.jpg`），不然正式環境的地球儀貼圖會抓不到、只顯示深藍色佔位球體。

---

## Self-Review 紀錄

- **Spec coverage：** three.js+CDN 載入（Task 1）、貼圖資產（Task 2）、場景/國界線/pin/互動的完整替換（Task 3）、端對端視覺+互動+效能驗證（Task 4）對應 spec 的「資料/資源」「架構」四個小節。地形/河流向量疊加的移除已經包含在 Task 3 的刪除範圍內（`HIGHLANDS`/`MOUNTAINS`/`RIVERS` 都在刪除清單裡）。
- **Placeholder scan：** Task 3 的 python 腳本、three.js 程式碼都是完整可執行內容，且已經在測試環境實際跑過驗證，不是理論上的示意。
- **Type/命名一致性：** `drawMap(trips)`、`mapZoom(factor)` 這兩個被 HTML `onclick`/外部呼叫的函式簽章維持跟舊版一致；`globePins`（陣列）這個名稱沿用舊版慣例；`BORDERS`（資料）在 Task 3 保留原樣，新程式碼裡的 `densifyBorderLine`/`latLngToVector3` 是新函式，命名跟用途一致，沒有跟舊版函式名稱衝突或誤用。
- **已知的驗證環境細節**：Playwright 瀏覽器 profile 有時會被前一個 session 佔用，出現 `Target page, context or browser has been closed` 或 `Browser is already in use` 錯誤時，先 `pkill -f "ms-playwright-mcp"` 再重試一次 `browser_navigate`。
