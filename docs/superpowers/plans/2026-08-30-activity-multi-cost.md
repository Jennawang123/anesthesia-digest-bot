# 行程活動多筆花費 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 iceland-trip.html／family-trip-template.html／couple-trip-template.html／us-trip.html 四支旅遊 app 的「編輯活動」表單，金額從單一欄位改成可以新增多行（各自填描述/金額/幣別/付款人，couple/us 另外還有拆帳），每行各自同步一筆記帳紀錄。

**Architecture:** `act.cost`（單一物件）改成 `act.costs`（陣列）。新增一個共用工具函式 `actCostList(act)` 統一讀取新舊兩種格式（舊資料 fallback 成一筆陣列，不寫遷移腳本）。表單裡新增 `curActCosts` 陣列 + `renderActCostRows()`，模式沿用既有 `curActImages`／`renderActImgPreviews()` 那套「JS 陣列驅動、整段重繪」。儲存/搬動/刪除活動時，逐行同步 `/expenses/actcost_{did}_{aid}_{n}`（`n`=陣列索引）取代原本固定 id 的單筆同步；行程卡片改成逐行顯示。純渲染/表單層改動，`/expenses` 平面清單結構不變，統計/圓餅圖/記帳分頁完全不受影響。

**Tech Stack:** 純前端 HTML/JS（無框架、無建置流程），Firebase Realtime Database。測試用檔案內建的 `_selftest()` 搭配 `python3 -m http.server` + Playwright 瀏覽器執行；`saveAct`/`moveAct`/`delAct` 這幾個會打 Firebase 的函式，用一個輕量的假 `DB` stub（本 plan 內建，模擬路徑巢狀讀寫）在瀏覽器 console 裡驗證，不連真實 Firebase。

---

## 背景說明（給執行者）

這是純 HTML 檔案（無 build step），四支檔案內容高度相似但不是逐字相同——`iceland-trip.html`／`couple-trip-template.html`／`us-trip.html` 三支有地理定位／跨夜住宿／移動日期選單這些 `family-trip-template.html` 沒有的欄位；`couple-trip-template.html`／`us-trip.html` 兩支另外有 `iceland`／`family` 沒有的兩人拆帳 `split`（均分/p1自付/p2自付）欄位。所以本 plan 分成兩種變體：

- **變體 A**（iceland、family）：每行「描述＋金額＋幣別下拉＋付款人下拉」
- **變體 B**（couple、us）：每行「描述＋金額＋幣別下拉＋付款人下拉＋怎麼分下拉」

iceland／couple／us 三支彼此的 `saveAct`/`moveAct`/`delAct`/`openActM`/`openActEdit` 結構逐字相同（只差變體 A/B 的欄位差異與 `'JPY'` vs `DEF_CUR`），family 因為少了地理定位/跨夜住宿/移動選單，函式内容比較簡短。

**測試方式**：跟前一次跨夜住宿那個 plan 一樣，`_selftest()` 用 `ok(name,cond)` helper，跑法是 `python3 -m http.server` + Playwright 開頁面在 console 執行 `_selftest()`。這次額外需要驗證會寫入 Firebase 的函式（`saveAct`/`moveAct`/`delAct`），但不能真的連 Firebase（背景是使用者真實資料庫）——用下面這段**假 DB stub**（每個檔案的驗證步驟都會重複用到，內容完全相同）：

```js
() => {
  window.__tree = {schedule:{day1:{date:'2026-09-14',acts:{}}}};
  window.__writes = [];
  function getPath(p){
    const parts=p.split('/').filter(Boolean);
    let n=window.__tree;
    for(const k of parts){ if(n==null)return null; n=n[k]; }
    return n===undefined?null:n;
  }
  function setPath(p,v){
    const parts=p.split('/').filter(Boolean);
    let n=window.__tree;
    for(let i=0;i<parts.length-1;i++){ if(n[parts[i]]==null)n[parts[i]]={}; n=n[parts[i]]; }
    if(v===null)delete n[parts[parts.length-1]]; else n[parts[parts.length-1]]=v;
  }
  DB = {
    ref(path){
      return {
        once(ev,cb){ cb({val:()=>getPath(path)}); return Promise.resolve(); },
        set(v){ window.__writes.push({path,op:'set',v}); setPath(path,v); return Promise.resolve(); },
        remove(){ window.__writes.push({path,op:'remove'}); setPath(path,null); return Promise.resolve(); },
        update(v){ window.__writes.push({path,op:'update',v}); Object.entries(v).forEach(([k,vv])=>setPath(k,vv)); return Promise.resolve(); },
      };
    }
  };
  CFG.members=['Mike','Monica'];
  lastSched={day1:{date:'2026-09-14',acts:{}}};
  return 'stubbed';
}
```

這段用 `DB = {...}`（不是 `window.DB = {...}`）直接改寫 `let DB` 這個全域變數，因為 Playwright/console 的 evaluate 是跟頁面共用同一個全域字彙範圍，`window.DB=` 只會加一個跟 `let DB` binding 無關的 window 屬性，`saveAct()` 裡讀到的還是舊的 `DB`（跟本系列前一個 plan 操作 `lastSched`/`curDay` 是同一個原理）。`getPath`/`setPath` 模擬 Firebase RTDB 的路徑巢狀寫入語意，讓 `/schedule/day1/acts/xxx` 寫進去後，`/schedule/day1` 讀出來能看到巢狀的 `acts.xxx`。

**檔案路徑**：全部在專案根目錄 `/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/`。

**部署**：四支都是 Netlify 手動拖拉部署，不會因為 commit 自動上線。本 plan 只負責把程式碼改對、commit 進 git。

---

## File Structure

只修改既有檔案：

- Modify: `iceland-trip.html` — 變體 A + 地理定位/跨夜住宿/移動選單
- Modify: `family-trip-template.html` — 變體 A，無地理定位/跨夜住宿/移動選單
- Modify: `couple-trip-template.html` — 變體 B（含拆帳）+ 地理定位/跨夜住宿/移動選單
- Modify: `us-trip.html` — 變體 B（含拆帳）+ 地理定位/跨夜住宿/移動選單（跟 couple 逐字相同）

---

## Task 1: iceland-trip.html — 工具函式、CSS、表單 HTML、狀態與渲染函式

**Files:**
- Modify: `iceland-trip.html:612-620`（`mapActCat` 後面插入 `actCostList`）
- Modify: `iceland-trip.html:134`（CSS）
- Modify: `iceland-trip.html:545-554`（cost-box HTML）
- Modify: `iceland-trip.html:625`（新增 `curActCosts` 狀態）
- Modify: `iceland-trip.html`（新增 `addActCostRow`/`removeActCostRow`/`renderActCostRows`，刪除 `selACur`/`selAPayer`）

- [ ] **Step 1: 新增 `actCostList()` 工具函式**

把：

```js
// Map schedule activity type → expense category
function mapActCat(actCat){
  if(actCat==='food')return'food';
  if(actCat==='transport')return'transport';
  if(actCat==='hotel')return'hotel';
  if(actCat==='shopping')return'shopping';
  if(actCat==='sight')return'ticket';
  if(actCat==='dessert')return'cafe';
  return'activity';
}
```

改成：

```js
// Map schedule activity type → expense category
function mapActCat(actCat){
  if(actCat==='food')return'food';
  if(actCat==='transport')return'transport';
  if(actCat==='hotel')return'hotel';
  if(actCat==='shopping')return'shopping';
  if(actCat==='sight')return'ticket';
  if(actCat==='dessert')return'cafe';
  return'activity';
}
// 活動花費：新格式是 costs 陣列，舊資料只有單一 cost 物件——讀取端統一轉成陣列，
// 不管上層是新舊哪種格式。不主動遷移舊資料，使用者下次編輯儲存那筆活動時才會自然轉檔。
function actCostList(act){
  if(Array.isArray(act?.costs))return act.costs;
  if(act?.cost?.amt>0)return [act.cost];
  return [];
}
```

- [ ] **Step 2: 新增 `.act-cost-row` CSS**

把：

```css
.cost-box{background:#F0FDF4;border-radius:10px;padding:14px;margin-bottom:14px;}
```

改成：

```css
.cost-box{background:#F0FDF4;border-radius:10px;padding:14px;margin-bottom:14px;}
.act-cost-row{display:flex;gap:6px;align-items:center;margin-bottom:8px;flex-wrap:wrap;}
.act-cost-row .inp{flex:1 1 70px;min-width:0;}
```

- [ ] **Step 3: 改寫 cost-box 表單 HTML**

把：

```html
    <div class="cost-box">
      <label class="lb">💰 行程花費（選填，自動加入記帳）</label>
      <div class="fr">
        <div class="fg" style="flex:0 0 130px"><label class="lb">金額</label><input class="inp" id="a_cost" type="number" placeholder="0.00" step="0.01" min="0"></div>
        <div class="fg"><label class="lb">幣別</label>
          <div class="cur-row" id="cur-row-act"></div>
        </div>
      </div>
      <div class="fg"><label class="lb">誰付</label><div class="pr" id="payer-row-act"></div></div>
    </div>
```

改成：

```html
    <div class="cost-box">
      <label class="lb">💰 行程花費（選填，自動加入記帳，可加多筆）</label>
      <div id="act-cost-rows"></div>
      <button type="button" class="btn btn-g" style="margin-top:6px;font-size:15px;padding:8px 12px" onclick="addActCostRow()">＋ 加一行</button>
    </div>
```

- [ ] **Step 4: 新增 `curActCosts` 狀態，刪除不再使用的 `curACur`/`curAPayer`**

把：

```js
let curAC='sight',curACur='JPY',curAPayer=0;
```

改成：

```js
let curAC='sight',curActCosts=[];
```

- [ ] **Step 5: 刪除 `selACur`/`selAPayer`，新增花費多行的狀態與渲染函式**

把：

```js
function selACur(c){curACur=c;renderCurChips('cur-row-act',c,'selACur');}
function selAPayer(i){curAPayer=i;renderPayerPicker('payer-row-act',i,'selAPayer');}
```

改成：

```js
function addActCostRow(){
  const last=curActCosts[curActCosts.length-1];
  curActCosts.push({desc:'',amt:'',cur:last?.cur||'JPY',paidBy:last?.paidBy||CFG.members[0]});
  renderActCostRows();
}
function removeActCostRow(i){curActCosts.splice(i,1);renderActCostRows();}
function renderActCostRows(){
  document.getElementById('act-cost-rows').innerHTML=curActCosts.map((c,i)=>`
    <div class="fr act-cost-row">
      <input class="inp" style="flex:0 0 78px" placeholder="描述" value="${esc(c.desc||'')}" oninput="curActCosts[${i}].desc=this.value">
      <input class="inp" style="flex:0 0 76px" type="number" step="0.01" min="0" placeholder="0.00" value="${c.amt||''}" oninput="curActCosts[${i}].amt=this.value">
      <select class="inp" style="flex:0 0 84px" onchange="curActCosts[${i}].cur=this.value">${PRESET_CURRENCIES.map(cc=>`<option value="${cc.code}"${cc.code===c.cur?' selected':''}>${cc.flag} ${cc.code}</option>`).join('')}</select>
      <select class="inp" onchange="curActCosts[${i}].paidBy=this.value">${CFG.members.map(m=>`<option value="${esc(m)}"${m===c.paidBy?' selected':''}>${esc(m)}</option>`).join('')}</select>
      <button type="button" class="ib" onclick="removeActCostRow(${i})">✕</button>
    </div>`).join('');
}
```

**注意**：`renderCurChips`／`renderPayerPicker` 這兩個函式本身不要刪，「記帳」分頁的 `cur-row-exp`／`payer-row-exp`（`selCur`／`selPayer`）還在用同一套。只有 `-act` 那組（活動花費專用的 chip picker）不再需要。

- [ ] **Step 6: 確認沒有語法錯誤**

執行：`python3 -m http.server 8765 --directory "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"`（背景執行）

用 Playwright 開 `http://localhost:8765/iceland-trip.html`，讀 console，確認沒有紅字 JS 錯誤（頁面會停在 Setup 畫面，這是預期行為）。

- [ ] **Step 7: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add iceland-trip.html
git commit -m "$(cat <<'EOF'
feat(iceland): 活動花費表單改可加多行

編輯活動的金額原本只有一格，一個活動最多只能連一筆花費。cost-box
改成可重複的清單，每行各自描述/金額/幣別/付款人，幣別跟付款人改用
原生 select（沿用整排 chip 按鈕的話，乘上好幾行會把表單拉得很長）。
新增 actCostList() 統一讀取新舊格式，讀取端 fallback 不用寫遷移腳本。

這一步只動表單層（開表單/加行/刪行/畫面渲染），儲存/同步記帳/卡片
顯示留給下一個 commit。
EOF
)"
```

---

## Task 2: iceland-trip.html — 儲存/搬動/刪除同步、卡片顯示、selftest

**Files:**
- Modify: `iceland-trip.html:2469-2483`（`openActM`）
- Modify: `iceland-trip.html:2484-2514`（`openActEdit`）
- Modify: `iceland-trip.html:2523-2576`（`saveAct`）
- Modify: `iceland-trip.html:2577`（`delAct`）
- Modify: `iceland-trip.html:1970-1986`（`moveAct`）
- Modify: `iceland-trip.html`（行程卡片花費顯示那行）
- Modify: `iceland-trip.html`（`_selftest()` 新增 `actCostList` 測試）

- [ ] **Step 1: 改寫 `openActM`**

把：

```js
function openActM(did){
  document.getElementById('m-act-t').textContent='新增活動';
  document.getElementById('ma-did').value=did;document.getElementById('ma-aid').value='';
  document.getElementById('a_name').value='';
  document.getElementById('a_loc').value='';document.getElementById('a_note').value='';document.getElementById('a_cost').value='';
  document.getElementById('a_geoq').value='';document.getElementById('a_geo_result').textContent='';
  document.getElementById('a_custom_ico').value='';
  curActImages=[];renderActImgPreviews();
  curAC='sight';renderACGrid();selAPayer(0);selACur('JPY');
  curClosed=[];renderDowPicker();
  curStay=null;fillStayInputs(null);
  document.getElementById('move-day-row').style.display='none';   // 新增時沒有「移動」可言
  applyCatFields();
  openM('m-act');setTimeout(()=>document.getElementById('a_name').focus(),280);
}
```

改成：

```js
function openActM(did){
  document.getElementById('m-act-t').textContent='新增活動';
  document.getElementById('ma-did').value=did;document.getElementById('ma-aid').value='';
  document.getElementById('a_name').value='';
  document.getElementById('a_loc').value='';document.getElementById('a_note').value='';
  document.getElementById('a_geoq').value='';document.getElementById('a_geo_result').textContent='';
  document.getElementById('a_custom_ico').value='';
  curActImages=[];renderActImgPreviews();
  curActCosts=[];renderActCostRows();
  curAC='sight';renderACGrid();
  curClosed=[];renderDowPicker();
  curStay=null;fillStayInputs(null);
  document.getElementById('move-day-row').style.display='none';   // 新增時沒有「移動」可言
  applyCatFields();
  openM('m-act');setTimeout(()=>document.getElementById('a_name').focus(),280);
}
```

- [ ] **Step 2: 改寫 `openActEdit`**

把：

```js
function openActEdit(did,aid){
  DB.ref('/schedule/'+did+'/acts/'+aid).once('value',snap=>{
    const a=snap.val();if(!a)return;
    document.getElementById('m-act-t').textContent='編輯活動';
    document.getElementById('ma-did').value=did;document.getElementById('ma-aid').value=aid;
    document.getElementById('a_name').value=a.name||'';
    document.getElementById('a_loc').value=a.loc||'';document.getElementById('a_note').value=a.note||'';
    document.getElementById('a_geoq').value=a.geoQ||'';
    document.getElementById('a_geo_result').innerHTML=a.geo
      ? `✅ 已定位：${esc(a.geo.q||'')}（${a.geo.lat.toFixed(3)}, ${a.geo.lng.toFixed(3)}）`
      : (a.geoFail?'❌ 目前查不到座標，可填上方的定位用地名再按試查':'');
    document.getElementById('a_cost').value=a.cost?.amt||'';
    curAC=a.cat||'sight';renderACGrid();
    document.getElementById('a_custom_ico').value=a.customIco||'';
    curClosed=Array.isArray(a.closed)?[...a.closed]:[];renderDowPicker();
    curStay=a.stay?{...a.stay}:null;fillStayInputs(curStay);
    curActImages=a.images?[...a.images]:[];renderActImgPreviews();
    selACur(a.cost?.cur||'JPY');selAPayer(Math.max(0,CFG.members.indexOf(a.cost?.paidBy)));
    curActOrder=a.order||0;
    // 一次只顯示一天之後，拖曳只能在當天內排序（別天的卡片根本不在畫面上），
    // 所以跨日移動改由這個選單負責。moveAct 是既有的，連記帳日期一起搬。
    const sel=document.getElementById('a_move_day');
    sel.innerHTML=Object.entries(lastSched)
      .sort((x,y)=>(parseInt(x[0].replace(/\D/g,''))||0)-(parseInt(y[0].replace(/\D/g,''))||0))
      .map(([d,day])=>`<option value="${d}"${d===did?' selected':''}>D${d.replace(/\D/g,'')}　${fmtD(day.date)}</option>`).join('');
    document.getElementById('move-day-row').style.display='';
    // 一定要排在 move-day-row 填好之後：renderStayOut 的入住日是從那個選單讀的
    applyCatFields();
    openM('m-act');
  });
}
```

改成：

```js
function openActEdit(did,aid){
  DB.ref('/schedule/'+did+'/acts/'+aid).once('value',snap=>{
    const a=snap.val();if(!a)return;
    document.getElementById('m-act-t').textContent='編輯活動';
    document.getElementById('ma-did').value=did;document.getElementById('ma-aid').value=aid;
    document.getElementById('a_name').value=a.name||'';
    document.getElementById('a_loc').value=a.loc||'';document.getElementById('a_note').value=a.note||'';
    document.getElementById('a_geoq').value=a.geoQ||'';
    document.getElementById('a_geo_result').innerHTML=a.geo
      ? `✅ 已定位：${esc(a.geo.q||'')}（${a.geo.lat.toFixed(3)}, ${a.geo.lng.toFixed(3)}）`
      : (a.geoFail?'❌ 目前查不到座標，可填上方的定位用地名再按試查':'');
    curAC=a.cat||'sight';renderACGrid();
    document.getElementById('a_custom_ico').value=a.customIco||'';
    curClosed=Array.isArray(a.closed)?[...a.closed]:[];renderDowPicker();
    curStay=a.stay?{...a.stay}:null;fillStayInputs(curStay);
    curActImages=a.images?[...a.images]:[];renderActImgPreviews();
    curActCosts=actCostList(a).map(c=>({...c}));renderActCostRows();
    curActOrder=a.order||0;
    // 一次只顯示一天之後，拖曳只能在當天內排序（別天的卡片根本不在畫面上），
    // 所以跨日移動改由這個選單負責。moveAct 是既有的，連記帳日期一起搬。
    const sel=document.getElementById('a_move_day');
    sel.innerHTML=Object.entries(lastSched)
      .sort((x,y)=>(parseInt(x[0].replace(/\D/g,''))||0)-(parseInt(y[0].replace(/\D/g,''))||0))
      .map(([d,day])=>`<option value="${d}"${d===did?' selected':''}>D${d.replace(/\D/g,'')}　${fmtD(day.date)}</option>`).join('');
    document.getElementById('move-day-row').style.display='';
    // 一定要排在 move-day-row 填好之後：renderStayOut 的入住日是從那個選單讀的
    applyCatFields();
    openM('m-act');
  });
}
```

- [ ] **Step 3: 改寫 `saveAct`**

把：

```js
function saveAct(){
  const did=document.getElementById('ma-did').value,aid=document.getElementById('ma-aid').value;
  const name=document.getElementById('a_name').value.trim();if(!name){toast('請輸入活動名稱');return;}
  const costAmt=parseFloat(document.getElementById('a_cost').value);
  const hasCost=!isNaN(costAmt)&&costAmt>0;
  DB.ref('/schedule/'+did).once('value',daySnap=>{
    const dayData=daySnap.val()||{};
    const existingActs=Object.values(dayData.acts||{});
    const maxOrder=existingActs.length?Math.max(...existingActs.map(a=>a.order||0)):0;
    const isNew=!aid;
    const customIco=document.getElementById('a_custom_ico').value.trim();
    const geoQ=document.getElementById('a_geoq').value.trim();
    const obj={cat:curAC,name,
      ...(curAC==='custom'&&customIco?{customIco}:{}),
      images:curActImages.length?[...curActImages]:null,
      loc:document.getElementById('a_loc').value.trim(),note:document.getElementById('a_note').value.trim(),
      ...(geoQ?{geoQ}:{}),
      // 類型改成交通／住宿之後那排圓圈就藏起來了，此時把 closed 一起清掉；
      // 否則畫面上看不到、卻還會冒出「⚠️ 公休日」，怎麼點都關不掉。
      closed:(!NO_CLOSED_CATS.includes(curAC)&&curClosed.length)?[...curClosed]:null,
      stay:curAC==='hotel'?{
        out:document.getElementById('a_stay_out').value||null,
        ci:document.getElementById('a_stay_ci').value.trim()||null,
        co:document.getElementById('a_stay_co').value.trim()||null,
        arr:document.getElementById('a_stay_arr').value.trim()||null,
        src:curStay?.src||null,
      }:null,
      cost:hasCost?{amt:costAmt,cur:curACur,paidBy:CFG.members[curAPayer]}:null,
      order:isNew?(maxOrder+1):curActOrder};
    const id=aid||('a'+uid());
    // 這裡是整筆 set，obj 沒有 geo 欄位，所以不特別處理的話「改個備註」都會把
    // 已經查好的座標洗掉、下次開 app 再跑一次地理編碼。定位字串沒變就把座標帶回來；
    // 變了才讓它重查，這也正是使用者填「定位用地名」之後期待發生的事。
    const prev=(dayData.acts||{})[id];
    if(prev&&geoQueryOf(prev)===geoQueryOf(obj)){
      if(prev.geo)obj.geo=prev.geo;
      if(prev.geoFail)obj.geoFail=prev.geoFail;
    }
    DB.ref('/schedule/'+did+'/acts/'+id).set(obj);
    const expId='actcost_'+did+'_'+id;
    if(hasCost){DB.ref('/expenses/'+expId).set({desc:name,amt:costAmt,cur:curACur,cat:mapActCat(curAC),paidBy:CFG.members[curAPayer],date:dayData.date||'',fromAct:true,at:new Date().toISOString()});}
    else{DB.ref('/expenses/'+expId).remove();}
    // 編輯模式下若選了別天，先存回原處再整筆搬過去（moveAct 會一併處理記帳的日期）
    const moveTo=document.getElementById('move-day-row').style.display!=='none'
      ? document.getElementById('a_move_day').value : did;
    if(!isNew&&moveTo&&moveTo!==did){
      moveAct(did,id,obj,moveTo);
      curDay=moveTo;_overviewChosen=false;   // 跟著跳到目的地那天，否則活動看起來像消失了
      closeM('m-act');
      return;
    }
    closeM('m-act');toast('✅ 已儲存');
  });
}
```

改成：

```js
function saveAct(){
  const did=document.getElementById('ma-did').value,aid=document.getElementById('ma-aid').value;
  const name=document.getElementById('a_name').value.trim();if(!name){toast('請輸入活動名稱');return;}
  const costs=curActCosts.map(c=>({desc:(c.desc||'').trim(),amt:parseFloat(c.amt),cur:c.cur||'JPY',paidBy:c.paidBy||CFG.members[0]})).filter(c=>!isNaN(c.amt)&&c.amt>0);
  DB.ref('/schedule/'+did).once('value',daySnap=>{
    const dayData=daySnap.val()||{};
    const existingActs=Object.values(dayData.acts||{});
    const maxOrder=existingActs.length?Math.max(...existingActs.map(a=>a.order||0)):0;
    const isNew=!aid;
    const customIco=document.getElementById('a_custom_ico').value.trim();
    const geoQ=document.getElementById('a_geoq').value.trim();
    const obj={cat:curAC,name,
      ...(curAC==='custom'&&customIco?{customIco}:{}),
      images:curActImages.length?[...curActImages]:null,
      loc:document.getElementById('a_loc').value.trim(),note:document.getElementById('a_note').value.trim(),
      ...(geoQ?{geoQ}:{}),
      // 類型改成交通／住宿之後那排圓圈就藏起來了，此時把 closed 一起清掉；
      // 否則畫面上看不到、卻還會冒出「⚠️ 公休日」，怎麼點都關不掉。
      closed:(!NO_CLOSED_CATS.includes(curAC)&&curClosed.length)?[...curClosed]:null,
      stay:curAC==='hotel'?{
        out:document.getElementById('a_stay_out').value||null,
        ci:document.getElementById('a_stay_ci').value.trim()||null,
        co:document.getElementById('a_stay_co').value.trim()||null,
        arr:document.getElementById('a_stay_arr').value.trim()||null,
        src:curStay?.src||null,
      }:null,
      costs:costs.length?costs:null,
      order:isNew?(maxOrder+1):curActOrder};
    const id=aid||('a'+uid());
    // 這裡是整筆 set，obj 沒有 geo 欄位，所以不特別處理的話「改個備註」都會把
    // 已經查好的座標洗掉、下次開 app 再跑一次地理編碼。定位字串沒變就把座標帶回來；
    // 變了才讓它重查，這也正是使用者填「定位用地名」之後期待發生的事。
    const prev=(dayData.acts||{})[id];
    if(prev&&geoQueryOf(prev)===geoQueryOf(obj)){
      if(prev.geo)obj.geo=prev.geo;
      if(prev.geoFail)obj.geoFail=prev.geoFail;
    }
    DB.ref('/schedule/'+did+'/acts/'+id).set(obj);
    // 舊格式固定 id 的記帳紀錄改成逐行索引，這個路徑往後不會再用到，順手清掉，
    // 不然舊資料第一次編輯儲存後，這筆連同新的 _0 一起留著會變成多算一筆。
    DB.ref('/expenses/actcost_'+did+'_'+id).remove();
    const prevCostCount=actCostList(prev).length;
    costs.forEach((c,i)=>{
      DB.ref('/expenses/actcost_'+did+'_'+id+'_'+i).set({desc:c.desc||name,amt:c.amt,cur:c.cur,cat:mapActCat(curAC),paidBy:c.paidBy,date:dayData.date||'',fromAct:true,at:new Date().toISOString()});
    });
    // 這次存的行數比之前少，代表使用者刪掉了某幾行，多出來的舊索引要一併刪除，
    // 否則會留下沒人記得、金額已經跟表單對不上的孤兒記帳項目。
    for(let i=costs.length;i<prevCostCount;i++)DB.ref('/expenses/actcost_'+did+'_'+id+'_'+i).remove();
    // 編輯模式下若選了別天，先存回原處再整筆搬過去（moveAct 會一併處理記帳的日期）
    const moveTo=document.getElementById('move-day-row').style.display!=='none'
      ? document.getElementById('a_move_day').value : did;
    if(!isNew&&moveTo&&moveTo!==did){
      moveAct(did,id,obj,moveTo);
      curDay=moveTo;_overviewChosen=false;   // 跟著跳到目的地那天，否則活動看起來像消失了
      closeM('m-act');
      return;
    }
    closeM('m-act');toast('✅ 已儲存');
  });
}
```

- [ ] **Step 4: 改寫 `delAct`**

把：

```js
function delAct(did,aid){if(!confirm('確定刪除此活動？'))return;DB.ref('/schedule/'+did+'/acts/'+aid).remove();DB.ref('/expenses/actcost_'+did+'_'+aid).remove();toast('🗑️ 已刪除');}
```

改成：

```js
function delAct(did,aid){
  if(!confirm('確定刪除此活動？'))return;
  DB.ref('/schedule/'+did+'/acts/'+aid).once('value',snap=>{
    const n=actCostList(snap.val()).length;
    DB.ref('/schedule/'+did+'/acts/'+aid).remove();
    DB.ref('/expenses/actcost_'+did+'_'+aid).remove();
    for(let i=0;i<n;i++)DB.ref('/expenses/actcost_'+did+'_'+aid+'_'+i).remove();
    toast('🗑️ 已刪除');
  });
}
```

- [ ] **Step 5: 改寫 `moveAct`**

把：

```js
function moveAct(fromDid,aid,act,toDid){
  DB.ref('/schedule/'+toDid+'/date').once('value',snap=>{
    const newDate=snap.val()||'';
    DB.ref('/schedule/'+toDid+'/acts/'+aid).set(act);
    DB.ref('/schedule/'+fromDid+'/acts/'+aid).remove();
    if(act.cost?.amt>0){
      DB.ref('/expenses/actcost_'+fromDid+'_'+aid).remove();
      DB.ref('/expenses/actcost_'+toDid+'_'+aid).set({desc:act.name,amt:act.cost.amt,cur:act.cost.cur||'JPY',cat:mapActCat(act.cat),paidBy:act.cost.paidBy||CFG.members[0],date:newDate,fromAct:true,at:new Date().toISOString()});
    }
    toast('✅ 已移動到 '+toDid.replace('day','Day '));
  });
}
```

改成：

```js
function moveAct(fromDid,aid,act,toDid){
  DB.ref('/schedule/'+toDid+'/date').once('value',snap=>{
    const newDate=snap.val()||'';
    DB.ref('/schedule/'+toDid+'/acts/'+aid).set(act);
    DB.ref('/schedule/'+fromDid+'/acts/'+aid).remove();
    DB.ref('/expenses/actcost_'+fromDid+'_'+aid).remove();   // 舊格式殘留一併清掉
    actCostList(act).forEach((c,i)=>{
      DB.ref('/expenses/actcost_'+fromDid+'_'+aid+'_'+i).remove();
      DB.ref('/expenses/actcost_'+toDid+'_'+aid+'_'+i).set({desc:c.desc||act.name,amt:c.amt,cur:c.cur||'JPY',cat:mapActCat(act.cat),paidBy:c.paidBy||CFG.members[0],date:newDate,fromAct:true,at:new Date().toISOString()});
    });
    toast('✅ 已移動到 '+toDid.replace('day','Day '));
  });
}
```

- [ ] **Step 6: 改寫行程卡片的花費顯示**

用 grep 找到目前位置：

```bash
grep -n "const sym=curSym(act.cost" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/iceland-trip.html"
```

把：

```js
            const sym=curSym(act.cost?.cur||'JPY');
            const dp=0;
```

改成：

```js
            const dp=0;
```

再把：

```js
                ${act.cost?.amt>0?`<div class="act-cost">💰 ${sym}${parseFloat(act.cost.amt).toFixed(dp)} ${act.cost.cur||'JPY'}</div>`:''}
```

改成：

```js
                ${actCostList(act).map(c=>`<div class="act-cost">💰 ${c.desc?esc(c.desc)+' ':''}${curSym(c.cur||'JPY')}${parseFloat(c.amt||0).toFixed(dp)} ${c.cur||'JPY'}</div>`).join('')}
```

- [ ] **Step 7: `_selftest()` 新增 `actCostList` 測試**

找到：

```js
  const near=(a,b,tol)=>Math.abs(a-b)<=tol;

  // ---- stripImages ----
```

改成：

```js
  const near=(a,b,tol)=>Math.abs(a-b)<=tol;

  // ---- actCostList ----
  {
    ok('新格式 costs 陣列直接回傳', actCostList({costs:[{amt:100},{amt:200}]}).length===2);
    ok('舊格式單一 cost 物件包成一筆陣列', actCostList({cost:{amt:100,cur:'JPY'}})[0].amt===100);
    ok('cost.amt 是 0 或負值不當作有效花費', actCostList({cost:{amt:0}}).length===0);
    ok('兩者都沒有回空陣列', actCostList({}).length===0);
    ok('costs 優先於 cost（新格式蓋過舊格式殘留）', actCostList({cost:{amt:999},costs:[{amt:1}]}).length===1);
  }

  // ---- stripImages ----
```

- [ ] **Step 8: 執行 selftest**

用 Playwright 開 `http://localhost:8765/iceland-trip.html`（沿用 Task 1 起的 server），console 執行 `_selftest()`，確認「失敗 0」。

- [ ] **Step 9: 假 DB 驗證多筆花費儲存/刪行清理**

在同一個頁面 console 依序執行（先貼上「背景說明」那段假 DB stub，再執行下面這段）：

```js
() => {
  openActM('day1');
  document.getElementById('a_name').value='黑沙灘';
  document.getElementById('ma-aid').value='atest1';   // 固定 id，模擬編輯既有活動，方便驗證覆寫/清理邏輯
  addActCostRow();addActCostRow();
  curActCosts[0]={desc:'門票',amt:'1200',cur:'JPY',paidBy:'Mike'};
  curActCosts[1]={desc:'午餐',amt:'350',cur:'JPY',paidBy:'Monica'};
  renderActCostRows();
  return document.querySelectorAll('#act-cost-rows .act-cost-row').length;
}
```

預期回傳 `2`。接著：

```js
() => { saveAct(); return window.__writes.filter(w=>w.path.startsWith('/expenses/')).map(w=>({path:w.path,op:w.op,amt:w.v?.amt,desc:w.v?.desc})); }
```

預期看到：`/expenses/actcost_day1_atest1`（`remove`）、`/expenses/actcost_day1_atest1_0`（`set`，`amt:1200,desc:'門票'`）、`/expenses/actcost_day1_atest1_1`（`set`，`amt:350,desc:'午餐'`）。

再測「刪掉一行重新儲存」的孤兒清理：

```js
() => {
  curActCosts.splice(1,1);   // 只留「門票」那行
  renderActCostRows();
  window.__writes.length=0;
  saveAct();
  return window.__writes.filter(w=>w.path.startsWith('/expenses/actcost_day1_atest1'));
}
```

預期看到 `/expenses/actcost_day1_atest1_0`（`set`）跟 `/expenses/actcost_day1_atest1_1`（`remove`，這就是孤兒清理），**不應該**再有 `/expenses/actcost_day1_atest1_1` 的 `set`。

驗證完關閉 http server（`lsof -ti:8765 | xargs kill`）。

- [ ] **Step 10: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add iceland-trip.html
git commit -m "$(cat <<'EOF'
feat(iceland): 多筆花費逐行同步記帳，卡片逐行顯示

saveAct/moveAct/delAct 從「一個活動最多同步一筆記帳」改成逐行同步
actcost_{did}_{aid}_{n}；儲存時行數變少要清掉多出來的舊索引，否則
會留下孤兒記帳項目。行程卡片的花費顯示改成逐行列出（有描述就帶上）。

假 DB stub 驗證：兩行花費存檔後 /expenses 出現對應兩筆索引記錄，
刪掉一行重存後多的那筆索引被清掉、不是留著金額歸零的孤兒記錄。
_selftest() 全過。
EOF
)"
```

---

## Task 3: family-trip-template.html — 工具函式、CSS、表單 HTML、狀態與渲染函式

**Files:**
- Modify: `family-trip-template.html`（`mapActCat` 後面插入 `actCostList`）
- Modify: `family-trip-template.html:131`（CSS）
- Modify: `family-trip-template.html:451-460`（cost-box HTML）
- Modify: `family-trip-template.html:538`（`curActCosts`）
- Modify: `family-trip-template.html`（新增花費多行函式，刪除 `selACur`/`selAPayer`）

family-trip-template.html 沒有地理定位/跨夜住宿/移動選單這些功能，`mapActCat`／CSS／cost-box HTML／`curActCosts`／`addActCostRow`／`removeActCostRow`／`renderActCostRows` 這幾塊內容跟 Task 1 的 Step 1～5 完全相同，直接套用同樣的 old/new 內容到 `family-trip-template.html`（行號會不同，用內容比對）。

- [ ] **Step 1～5**：依序對照 Task 1 的 Step 1～5，對 `family-trip-template.html` 做完全相同的 Edit。

- [ ] **Step 6: 確認沒有語法錯誤**

用 Playwright 開 `http://localhost:8765/family-trip-template.html`（背景起 http server，同 Task 1 Step 6 做法），確認 console 無錯誤。

- [ ] **Step 7: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add family-trip-template.html
git commit -m "$(cat <<'EOF'
feat(family): 活動花費表單改可加多行

同 iceland-trip.html 的實作（見該次 commit 說明）。這支沒有地理定位/
跨夜住宿/移動選單，cost-box 那塊改動跟 iceland 逐字相同。
EOF
)"
```

---

## Task 4: family-trip-template.html — 儲存/搬動/刪除同步、卡片顯示、selftest

**Files:**
- Modify: `family-trip-template.html:1309-1317`（`openActM`）
- Modify: `family-trip-template.html:1319-1335`（`openActEdit`）
- Modify: `family-trip-template.html:1336-1360`（`saveAct`）
- Modify: `family-trip-template.html:1361`（`delAct`）
- Modify: `family-trip-template.html:1199-1210`（`moveAct`）
- Modify: `family-trip-template.html`（行程卡片花費顯示那行）
- Modify: `family-trip-template.html`（`_selftest()` 新增 `actCostList` 測試）

family 版沒有 geo/stay/move-day-row，這幾個函式比 iceland 簡短很多，直接給完整內容。

- [ ] **Step 1: 改寫 `openActM`**

把：

```js
function openActM(did){
  document.getElementById('m-act-t').textContent='新增活動';
  document.getElementById('ma-did').value=did;document.getElementById('ma-aid').value='';
  document.getElementById('a_name').value='';
  document.getElementById('a_loc').value='';document.getElementById('a_note').value='';document.getElementById('a_cost').value='';
  document.getElementById('a_custom_ico').value='';document.getElementById('custom-ico-row').style.display='none';
  curActImages=[];renderActImgPreviews();
  curAC='sight';renderACGrid();selAPayer(0);selACur('JPY');
  openM('m-act');setTimeout(()=>document.getElementById('a_name').focus(),280);
}
```

改成：

```js
function openActM(did){
  document.getElementById('m-act-t').textContent='新增活動';
  document.getElementById('ma-did').value=did;document.getElementById('ma-aid').value='';
  document.getElementById('a_name').value='';
  document.getElementById('a_loc').value='';document.getElementById('a_note').value='';
  document.getElementById('a_custom_ico').value='';document.getElementById('custom-ico-row').style.display='none';
  curActImages=[];renderActImgPreviews();
  curActCosts=[];renderActCostRows();
  curAC='sight';renderACGrid();
  openM('m-act');setTimeout(()=>document.getElementById('a_name').focus(),280);
}
```

- [ ] **Step 2: 改寫 `openActEdit`**

把：

```js
function openActEdit(did,aid){
  DB.ref('/schedule/'+did+'/acts/'+aid).once('value',snap=>{
    const a=snap.val();if(!a)return;
    document.getElementById('m-act-t').textContent='編輯活動';
    document.getElementById('ma-did').value=did;document.getElementById('ma-aid').value=aid;
    document.getElementById('a_name').value=a.name||'';
    document.getElementById('a_loc').value=a.loc||'';document.getElementById('a_note').value=a.note||'';
    document.getElementById('a_cost').value=a.cost?.amt||'';
    curAC=a.cat||'sight';renderACGrid();
    document.getElementById('a_custom_ico').value=a.customIco||'';
    document.getElementById('custom-ico-row').style.display=a.cat==='custom'?'':'none';
    curActImages=a.images?[...a.images]:[];renderActImgPreviews();
    selACur(a.cost?.cur||'JPY');selAPayer(Math.max(0,CFG.members.indexOf(a.cost?.paidBy)));
    curActOrder=a.order||0;
    openM('m-act');
  });
}
```

改成：

```js
function openActEdit(did,aid){
  DB.ref('/schedule/'+did+'/acts/'+aid).once('value',snap=>{
    const a=snap.val();if(!a)return;
    document.getElementById('m-act-t').textContent='編輯活動';
    document.getElementById('ma-did').value=did;document.getElementById('ma-aid').value=aid;
    document.getElementById('a_name').value=a.name||'';
    document.getElementById('a_loc').value=a.loc||'';document.getElementById('a_note').value=a.note||'';
    curAC=a.cat||'sight';renderACGrid();
    document.getElementById('a_custom_ico').value=a.customIco||'';
    document.getElementById('custom-ico-row').style.display=a.cat==='custom'?'':'none';
    curActImages=a.images?[...a.images]:[];renderActImgPreviews();
    curActCosts=actCostList(a).map(c=>({...c}));renderActCostRows();
    curActOrder=a.order||0;
    openM('m-act');
  });
}
```

- [ ] **Step 3: 改寫 `saveAct`**

把：

```js
function saveAct(){
  const did=document.getElementById('ma-did').value,aid=document.getElementById('ma-aid').value;
  const name=document.getElementById('a_name').value.trim();if(!name){toast('請輸入活動名稱');return;}
  const costAmt=parseFloat(document.getElementById('a_cost').value);
  const hasCost=!isNaN(costAmt)&&costAmt>0;
  DB.ref('/schedule/'+did).once('value',daySnap=>{
    const dayData=daySnap.val()||{};
    const existingActs=Object.values(dayData.acts||{});
    const maxOrder=existingActs.length?Math.max(...existingActs.map(a=>a.order||0)):0;
    const isNew=!aid;
    const customIco=document.getElementById('a_custom_ico').value.trim();
    const obj={cat:curAC,name,
      ...(curAC==='custom'&&customIco?{customIco}:{}),
      images:curActImages.length?[...curActImages]:null,
      loc:document.getElementById('a_loc').value.trim(),note:document.getElementById('a_note').value.trim(),
      cost:hasCost?{amt:costAmt,cur:curACur,paidBy:CFG.members[curAPayer]}:null,
      order:isNew?(maxOrder+1):curActOrder};
    const id=aid||('a'+uid());
    DB.ref('/schedule/'+did+'/acts/'+id).set(obj);
    const expId='actcost_'+did+'_'+id;
    if(hasCost){DB.ref('/expenses/'+expId).set({desc:name,amt:costAmt,cur:curACur,cat:mapActCat(curAC),paidBy:CFG.members[curAPayer],date:dayData.date||'',fromAct:true,at:new Date().toISOString()});}
    else{DB.ref('/expenses/'+expId).remove();}
    closeM('m-act');toast('✅ 已儲存');
  });
}
```

改成：

```js
function saveAct(){
  const did=document.getElementById('ma-did').value,aid=document.getElementById('ma-aid').value;
  const name=document.getElementById('a_name').value.trim();if(!name){toast('請輸入活動名稱');return;}
  const costs=curActCosts.map(c=>({desc:(c.desc||'').trim(),amt:parseFloat(c.amt),cur:c.cur||'JPY',paidBy:c.paidBy||CFG.members[0]})).filter(c=>!isNaN(c.amt)&&c.amt>0);
  DB.ref('/schedule/'+did).once('value',daySnap=>{
    const dayData=daySnap.val()||{};
    const existingActs=Object.values(dayData.acts||{});
    const maxOrder=existingActs.length?Math.max(...existingActs.map(a=>a.order||0)):0;
    const isNew=!aid;
    const customIco=document.getElementById('a_custom_ico').value.trim();
    const obj={cat:curAC,name,
      ...(curAC==='custom'&&customIco?{customIco}:{}),
      images:curActImages.length?[...curActImages]:null,
      loc:document.getElementById('a_loc').value.trim(),note:document.getElementById('a_note').value.trim(),
      costs:costs.length?costs:null,
      order:isNew?(maxOrder+1):curActOrder};
    const id=aid||('a'+uid());
    const prev=(dayData.acts||{})[id];
    DB.ref('/schedule/'+did+'/acts/'+id).set(obj);
    DB.ref('/expenses/actcost_'+did+'_'+id).remove();
    const prevCostCount=actCostList(prev).length;
    costs.forEach((c,i)=>{
      DB.ref('/expenses/actcost_'+did+'_'+id+'_'+i).set({desc:c.desc||name,amt:c.amt,cur:c.cur,cat:mapActCat(curAC),paidBy:c.paidBy,date:dayData.date||'',fromAct:true,at:new Date().toISOString()});
    });
    for(let i=costs.length;i<prevCostCount;i++)DB.ref('/expenses/actcost_'+did+'_'+id+'_'+i).remove();
    closeM('m-act');toast('✅ 已儲存');
  });
}
```

**注意**：family 版原本沒有 `const prev=(dayData.acts||{})[id];` 這行（沒有 geo 保留邏輯），這裡是新增的，只為了取得 `prevCostCount`，不要順手把 iceland 版那段 geo 保留的程式碼也搬過來——family 版沒有 `geoQueryOf`/`geo` 欄位這回事。

- [ ] **Step 4: 改寫 `delAct`**

把：

```js
function delAct(did,aid){if(!confirm('確定刪除此活動？'))return;DB.ref('/schedule/'+did+'/acts/'+aid).remove();DB.ref('/expenses/actcost_'+did+'_'+aid).remove();toast('🗑️ 已刪除');}
```

改成：

```js
function delAct(did,aid){
  if(!confirm('確定刪除此活動？'))return;
  DB.ref('/schedule/'+did+'/acts/'+aid).once('value',snap=>{
    const n=actCostList(snap.val()).length;
    DB.ref('/schedule/'+did+'/acts/'+aid).remove();
    DB.ref('/expenses/actcost_'+did+'_'+aid).remove();
    for(let i=0;i<n;i++)DB.ref('/expenses/actcost_'+did+'_'+aid+'_'+i).remove();
    toast('🗑️ 已刪除');
  });
}
```

- [ ] **Step 5: 改寫 `moveAct`**

把：

```js
function moveAct(fromDid,aid,act,toDid){
  DB.ref('/schedule/'+toDid+'/date').once('value',snap=>{
    const newDate=snap.val()||'';
    DB.ref('/schedule/'+toDid+'/acts/'+aid).set(act);
    DB.ref('/schedule/'+fromDid+'/acts/'+aid).remove();
    if(act.cost?.amt>0){
      DB.ref('/expenses/actcost_'+fromDid+'_'+aid).remove();
      DB.ref('/expenses/actcost_'+toDid+'_'+aid).set({desc:act.name,amt:act.cost.amt,cur:act.cost.cur||'JPY',cat:mapActCat(act.cat),paidBy:act.cost.paidBy||CFG.members[0],date:newDate,fromAct:true,at:new Date().toISOString()});
    }
    toast('✅ 已移動到 '+toDid.replace('day','Day '));
  });
}
```

改成：

```js
function moveAct(fromDid,aid,act,toDid){
  DB.ref('/schedule/'+toDid+'/date').once('value',snap=>{
    const newDate=snap.val()||'';
    DB.ref('/schedule/'+toDid+'/acts/'+aid).set(act);
    DB.ref('/schedule/'+fromDid+'/acts/'+aid).remove();
    DB.ref('/expenses/actcost_'+fromDid+'_'+aid).remove();
    actCostList(act).forEach((c,i)=>{
      DB.ref('/expenses/actcost_'+fromDid+'_'+aid+'_'+i).remove();
      DB.ref('/expenses/actcost_'+toDid+'_'+aid+'_'+i).set({desc:c.desc||act.name,amt:c.amt,cur:c.cur||'JPY',cat:mapActCat(act.cat),paidBy:c.paidBy||CFG.members[0],date:newDate,fromAct:true,at:new Date().toISOString()});
    });
    toast('✅ 已移動到 '+toDid.replace('day','Day '));
  });
}
```

- [ ] **Step 6: 改寫行程卡片的花費顯示**

用 grep 找到位置：

```bash
grep -n "const sym=curSym(act.cost" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/family-trip-template.html"
```

把：

```js
            const sym=curSym(act.cost?.cur||'JPY');
            const dp=0;
```

改成：

```js
            const dp=0;
```

再把：

```js
                ${act.cost?.amt>0?`<div class="act-cost">💰 ${sym}${parseFloat(act.cost.amt).toFixed(dp)} ${act.cost.cur||'JPY'}</div>`:''}
```

改成：

```js
                ${actCostList(act).map(c=>`<div class="act-cost">💰 ${c.desc?esc(c.desc)+' ':''}${curSym(c.cur||'JPY')}${parseFloat(c.amt||0).toFixed(dp)} ${c.cur||'JPY'}</div>`).join('')}
```

- [ ] **Step 7: `_selftest()` 新增 `actCostList` 測試**

family 版的 `_selftest()` 開頭是：

```js
function _selftest(){
  const out=[];let pass=0,fail=0;
  const ok=(name,cond,extra='')=>{cond?pass++:fail++;out.push(`${cond?'✅':'❌'} ${name}${extra&&!cond?'  → '+extra:''}`);};
  const saved=CFG.fs;
```

改成：

```js
function _selftest(){
  const out=[];let pass=0,fail=0;
  const ok=(name,cond,extra='')=>{cond?pass++:fail++;out.push(`${cond?'✅':'❌'} ${name}${extra&&!cond?'  → '+extra:''}`);};
  // ---- actCostList ----
  {
    ok('新格式 costs 陣列直接回傳', actCostList({costs:[{amt:100},{amt:200}]}).length===2);
    ok('舊格式單一 cost 物件包成一筆陣列', actCostList({cost:{amt:100,cur:'JPY'}})[0].amt===100);
    ok('cost.amt 是 0 或負值不當作有效花費', actCostList({cost:{amt:0}}).length===0);
    ok('兩者都沒有回空陣列', actCostList({}).length===0);
    ok('costs 優先於 cost（新格式蓋過舊格式殘留）', actCostList({cost:{amt:999},costs:[{amt:1}]}).length===1);
  }
  const saved=CFG.fs;
```

- [ ] **Step 8: 執行 selftest + 假 DB 驗證**

跟 Task 2 的 Step 8～9 做法相同，改開 `http://localhost:8765/family-trip-template.html`。family 版沒有 `move-day-row`／`a_geoq` 這些欄位，假 DB 驗證那段腳本（Task 2 Step 9）不涉及這些欄位，可以原樣照用。驗證完關閉 http server。

- [ ] **Step 9: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add family-trip-template.html
git commit -m "$(cat <<'EOF'
feat(family): 多筆花費逐行同步記帳，卡片逐行顯示

同 iceland-trip.html 的實作（見該次 commit 說明）。這支沒有 geo/搬移
邏輯，saveAct 只多讀一次 prev 取得 prevCostCount，其餘不變。
EOF
)"
```

---

## Task 5: couple-trip-template.html — 工具函式、CSS、表單 HTML、狀態與渲染函式（含拆帳）

**Files:**
- Modify: `couple-trip-template.html`（`mapActCat` 後面插入 `actCostList`）
- Modify: `couple-trip-template.html:124`（CSS）
- Modify: `couple-trip-template.html:534-545`（cost-box HTML）
- Modify: `couple-trip-template.html:632`（`curActCosts`）
- Modify: `couple-trip-template.html`（新增花費多行函式含拆帳，刪除 `selACur`/`selAPayer`/`selASplit`）

- [ ] **Step 1: 新增 `actCostList()` 工具函式**

跟 Task 1 Step 1 完全相同的 old/new 內容（`mapActCat` 函式在 couple-trip-template.html 逐字相同）。

- [ ] **Step 2: 新增 `.act-cost-row` CSS**

跟 Task 1 Step 2 完全相同的 old/new 內容（`.cost-box{...}` 這行逐字相同）。

- [ ] **Step 3: 改寫 cost-box 表單 HTML**

把：

```html
    <div class="cost-box">
      <label class="lb">💰 行程花費（選填，自動加入記帳）</label>
      <div class="fr">
        <div class="fg" style="flex:0 0 130px"><label class="lb">金額</label><input class="inp" id="a_cost" type="number" placeholder="0.00" step="0.01" min="0"></div>
        <div class="fg"><label class="lb">幣別</label>
          <div class="cur-row" id="cur-row-act"></div>
        </div>
      </div>
      <div class="fg"><label class="lb">誰付</label><div class="pr" id="payer-row-act"></div></div>
      <div class="fg"><label class="lb">怎麼分</label><div class="tw" id="split-row-act"></div></div>
    </div>
```

改成（跟 Task 1 Step 3 的新內容完全相同——多筆花費表單本身沒有分「均分/自付」的整體設定，改成每行各自一個下拉，下面 Step 5 處理）：

```html
    <div class="cost-box">
      <label class="lb">💰 行程花費（選填，自動加入記帳，可加多筆）</label>
      <div id="act-cost-rows"></div>
      <button type="button" class="btn btn-g" style="margin-top:6px;font-size:15px;padding:8px 12px" onclick="addActCostRow()">＋ 加一行</button>
    </div>
```

- [ ] **Step 4: 新增 `curActCosts` 狀態，刪除不再使用的 `curACur`/`curAPayer`/`curASplit`**

把：

```js
let curAC='sight',curACur=DEF_CUR,curAPayer=0,curASplit='both';
```

改成：

```js
let curAC='sight',curActCosts=[];
```

- [ ] **Step 5: 刪除 `selACur`/`selAPayer`/`selASplit`，新增花費多行的狀態與渲染函式（含拆帳下拉）**

把：

```js
function selACur(c){curACur=c;renderCurChips('cur-row-act',c,'selACur');}
function selAPayer(i){curAPayer=i;renderPayerPicker('payer-row-act',i,'selAPayer');}
function selASplit(m){curASplit=m;renderSplitPicker('split-row-act',m,'selASplit');}
```

改成：

```js
function addActCostRow(){
  const last=curActCosts[curActCosts.length-1];
  curActCosts.push({desc:'',amt:'',cur:last?.cur||DEF_CUR,paidBy:last?.paidBy||CFG.members[0],split:last?.split||'both'});
  renderActCostRows();
}
function removeActCostRow(i){curActCosts.splice(i,1);renderActCostRows();}
function renderActCostRows(){
  document.getElementById('act-cost-rows').innerHTML=curActCosts.map((c,i)=>`
    <div class="fr act-cost-row">
      <input class="inp" style="flex:0 0 70px" placeholder="描述" value="${esc(c.desc||'')}" oninput="curActCosts[${i}].desc=this.value">
      <input class="inp" style="flex:0 0 70px" type="number" step="0.01" min="0" placeholder="0.00" value="${c.amt||''}" oninput="curActCosts[${i}].amt=this.value">
      <select class="inp" style="flex:0 0 76px" onchange="curActCosts[${i}].cur=this.value">${PRESET_CURRENCIES.map(cc=>`<option value="${cc.code}"${cc.code===c.cur?' selected':''}>${cc.flag} ${cc.code}</option>`).join('')}</select>
      <select class="inp" style="flex:0 0 76px" onchange="curActCosts[${i}].paidBy=this.value">${CFG.members.map(m=>`<option value="${esc(m)}"${m===c.paidBy?' selected':''}>${esc(m)}</option>`).join('')}</select>
      <select class="inp" onchange="curActCosts[${i}].split=this.value">${['both','p1','p2'].map(m=>`<option value="${m}"${m===(c.split||'both')?' selected':''}>${splitLabel(m)}</option>`).join('')}</select>
      <button type="button" class="ib" onclick="removeActCostRow(${i})">✕</button>
    </div>`).join('');
}
```

**注意**：`renderCurChips`／`renderPayerPicker`／`renderSplitPicker`／`splitLabel` 這幾個函式本身不要刪，「記帳」分頁的 `-exp` 那組（`selCur`／`selPayer`／`selSplit`）還在用。只有 `-act` 那組不再需要。

- [ ] **Step 6: 確認沒有語法錯誤**

用 Playwright 開 `http://localhost:8765/couple-trip-template.html`（背景起 http server），確認 console 無錯誤。

- [ ] **Step 7: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add couple-trip-template.html
git commit -m "$(cat <<'EOF'
feat(couple): 活動花費表單改可加多行，每行各自拆帳

同 iceland-trip.html 的實作（見該次 commit 說明）。couple 版每行多一
個「怎麼分」下拉（均分/p1自付/p2自付，沿用既有 splitLabel()），因為
現在本來就是每筆花費各自拆帳，分成多行後自然也該各自可選。
EOF
)"
```

---

## Task 6: couple-trip-template.html — 儲存/搬動/刪除同步、卡片顯示、selftest（含拆帳）

**Files:**
- Modify: `couple-trip-template.html:2592-2606`（`openActM`）
- Modify: `couple-trip-template.html:2607-2637`（`openActEdit`）
- Modify: `couple-trip-template.html:2646-2700`（`saveAct`）
- Modify: `couple-trip-template.html:2700`（`delAct`）
- Modify: `couple-trip-template.html:2092-2108`（`moveAct`）
- Modify: `couple-trip-template.html`（行程卡片花費顯示那行）
- Modify: `couple-trip-template.html`（`_selftest()` 新增 `actCostList` 測試）

- [ ] **Step 1: 改寫 `openActM`**

把：

```js
function openActM(did){
  document.getElementById('m-act-t').textContent='新增活動';
  document.getElementById('ma-did').value=did;document.getElementById('ma-aid').value='';
  document.getElementById('a_name').value='';
  document.getElementById('a_loc').value='';document.getElementById('a_note').value='';document.getElementById('a_cost').value='';
  document.getElementById('a_geoq').value='';document.getElementById('a_geo_result').textContent='';
  document.getElementById('a_custom_ico').value='';
  curActImages=[];renderActImgPreviews();
  curAC='sight';renderACGrid();selAPayer(0);selACur(DEF_CUR);selASplit('both');
  curClosed=[];renderDowPicker();
  curStay=null;fillStayInputs(null);
  document.getElementById('move-day-row').style.display='none';   // 新增時沒有「移動」可言
  applyCatFields();
  openM('m-act');setTimeout(()=>document.getElementById('a_name').focus(),280);
}
```

改成：

```js
function openActM(did){
  document.getElementById('m-act-t').textContent='新增活動';
  document.getElementById('ma-did').value=did;document.getElementById('ma-aid').value='';
  document.getElementById('a_name').value='';
  document.getElementById('a_loc').value='';document.getElementById('a_note').value='';
  document.getElementById('a_geoq').value='';document.getElementById('a_geo_result').textContent='';
  document.getElementById('a_custom_ico').value='';
  curActImages=[];renderActImgPreviews();
  curActCosts=[];renderActCostRows();
  curAC='sight';renderACGrid();
  curClosed=[];renderDowPicker();
  curStay=null;fillStayInputs(null);
  document.getElementById('move-day-row').style.display='none';   // 新增時沒有「移動」可言
  applyCatFields();
  openM('m-act');setTimeout(()=>document.getElementById('a_name').focus(),280);
}
```

- [ ] **Step 2: 改寫 `openActEdit`**

把：

```js
function openActEdit(did,aid){
  DB.ref('/schedule/'+did+'/acts/'+aid).once('value',snap=>{
    const a=snap.val();if(!a)return;
    document.getElementById('m-act-t').textContent='編輯活動';
    document.getElementById('ma-did').value=did;document.getElementById('ma-aid').value=aid;
    document.getElementById('a_name').value=a.name||'';
    document.getElementById('a_loc').value=a.loc||'';document.getElementById('a_note').value=a.note||'';
    document.getElementById('a_geoq').value=a.geoQ||'';
    document.getElementById('a_geo_result').innerHTML=a.geo
      ? `✅ 已定位：${esc(a.geo.q||'')}（${a.geo.lat.toFixed(3)}, ${a.geo.lng.toFixed(3)}）`
      : (a.geoFail?'❌ 目前查不到座標，可填上方的定位用地名再按試查':'');
    document.getElementById('a_cost').value=a.cost?.amt||'';
    curAC=a.cat||'sight';renderACGrid();
    document.getElementById('a_custom_ico').value=a.customIco||'';
    curClosed=Array.isArray(a.closed)?[...a.closed]:[];renderDowPicker();
    curStay=a.stay?{...a.stay}:null;fillStayInputs(curStay);
    curActImages=a.images?[...a.images]:[];renderActImgPreviews();
    selACur(a.cost?.cur||DEF_CUR);selAPayer(Math.max(0,CFG.members.indexOf(a.cost?.paidBy)));selASplit(a.cost?.split||'both');
    curActOrder=a.order||0;
    // 一次只顯示一天之後，拖曳只能在當天內排序（別天的卡片根本不在畫面上），
    // 所以跨日移動改由這個選單負責。moveAct 是既有的，連記帳日期一起搬。
    const sel=document.getElementById('a_move_day');
    sel.innerHTML=Object.entries(lastSched)
      .sort((x,y)=>(parseInt(x[0].replace(/\D/g,''))||0)-(parseInt(y[0].replace(/\D/g,''))||0))
      .map(([d,day])=>`<option value="${d}"${d===did?' selected':''}>D${d.replace(/\D/g,'')}　${fmtD(day.date)}</option>`).join('');
    document.getElementById('move-day-row').style.display='';
    // 一定要排在 move-day-row 填好之後：renderStayOut 的入住日是從那個選單讀的
    applyCatFields();
    openM('m-act');
  });
}
```

改成：

```js
function openActEdit(did,aid){
  DB.ref('/schedule/'+did+'/acts/'+aid).once('value',snap=>{
    const a=snap.val();if(!a)return;
    document.getElementById('m-act-t').textContent='編輯活動';
    document.getElementById('ma-did').value=did;document.getElementById('ma-aid').value=aid;
    document.getElementById('a_name').value=a.name||'';
    document.getElementById('a_loc').value=a.loc||'';document.getElementById('a_note').value=a.note||'';
    document.getElementById('a_geoq').value=a.geoQ||'';
    document.getElementById('a_geo_result').innerHTML=a.geo
      ? `✅ 已定位：${esc(a.geo.q||'')}（${a.geo.lat.toFixed(3)}, ${a.geo.lng.toFixed(3)}）`
      : (a.geoFail?'❌ 目前查不到座標，可填上方的定位用地名再按試查':'');
    curAC=a.cat||'sight';renderACGrid();
    document.getElementById('a_custom_ico').value=a.customIco||'';
    curClosed=Array.isArray(a.closed)?[...a.closed]:[];renderDowPicker();
    curStay=a.stay?{...a.stay}:null;fillStayInputs(curStay);
    curActImages=a.images?[...a.images]:[];renderActImgPreviews();
    curActCosts=actCostList(a).map(c=>({...c}));renderActCostRows();
    curActOrder=a.order||0;
    // 一次只顯示一天之後，拖曳只能在當天內排序（別天的卡片根本不在畫面上），
    // 所以跨日移動改由這個選單負責。moveAct 是既有的，連記帳日期一起搬。
    const sel=document.getElementById('a_move_day');
    sel.innerHTML=Object.entries(lastSched)
      .sort((x,y)=>(parseInt(x[0].replace(/\D/g,''))||0)-(parseInt(y[0].replace(/\D/g,''))||0))
      .map(([d,day])=>`<option value="${d}"${d===did?' selected':''}>D${d.replace(/\D/g,'')}　${fmtD(day.date)}</option>`).join('');
    document.getElementById('move-day-row').style.display='';
    // 一定要排在 move-day-row 填好之後：renderStayOut 的入住日是從那個選單讀的
    applyCatFields();
    openM('m-act');
  });
}
```

- [ ] **Step 3: 改寫 `saveAct`**

把：

```js
function saveAct(){
  const did=document.getElementById('ma-did').value,aid=document.getElementById('ma-aid').value;
  const name=document.getElementById('a_name').value.trim();if(!name){toast('請輸入活動名稱');return;}
  const costAmt=parseFloat(document.getElementById('a_cost').value);
  const hasCost=!isNaN(costAmt)&&costAmt>0;
  DB.ref('/schedule/'+did).once('value',daySnap=>{
    const dayData=daySnap.val()||{};
    const existingActs=Object.values(dayData.acts||{});
    const maxOrder=existingActs.length?Math.max(...existingActs.map(a=>a.order||0)):0;
    const isNew=!aid;
    const customIco=document.getElementById('a_custom_ico').value.trim();
    const geoQ=document.getElementById('a_geoq').value.trim();
    const obj={cat:curAC,name,
      ...(curAC==='custom'&&customIco?{customIco}:{}),
      images:curActImages.length?[...curActImages]:null,
      loc:document.getElementById('a_loc').value.trim(),note:document.getElementById('a_note').value.trim(),
      ...(geoQ?{geoQ}:{}),
      // 類型改成交通／住宿之後那排圓圈就藏起來了，此時把 closed 一起清掉；
      // 否則畫面上看不到、卻還會冒出「⚠️ 公休日」，怎麼點都關不掉。
      closed:(!NO_CLOSED_CATS.includes(curAC)&&curClosed.length)?[...curClosed]:null,
      stay:curAC==='hotel'?{
        out:document.getElementById('a_stay_out').value||null,
        ci:document.getElementById('a_stay_ci').value.trim()||null,
        co:document.getElementById('a_stay_co').value.trim()||null,
        arr:document.getElementById('a_stay_arr').value.trim()||null,
        src:curStay?.src||null,
      }:null,
      cost:hasCost?{amt:costAmt,cur:curACur,paidBy:CFG.members[curAPayer],split:curASplit}:null,
      order:isNew?(maxOrder+1):curActOrder};
    const id=aid||('a'+uid());
    // 這裡是整筆 set，obj 沒有 geo 欄位，所以不特別處理的話「改個備註」都會把
    // 已經查好的座標洗掉、下次開 app 再跑一次地理編碼。定位字串沒變就把座標帶回來；
    // 變了才讓它重查，這也正是使用者填「定位用地名」之後期待發生的事。
    const prev=(dayData.acts||{})[id];
    if(prev&&geoQueryOf(prev)===geoQueryOf(obj)){
      if(prev.geo)obj.geo=prev.geo;
      if(prev.geoFail)obj.geoFail=prev.geoFail;
    }
    DB.ref('/schedule/'+did+'/acts/'+id).set(obj);
    const expId='actcost_'+did+'_'+id;
    if(hasCost){DB.ref('/expenses/'+expId).set({desc:name,amt:costAmt,cur:curACur,cat:mapActCat(curAC),paidBy:CFG.members[curAPayer],split:curASplit,date:dayData.date||'',fromAct:true,at:new Date().toISOString()});}
    else{DB.ref('/expenses/'+expId).remove();}
    // 編輯模式下若選了別天，先存回原處再整筆搬過去（moveAct 會一併處理記帳的日期）
    const moveTo=document.getElementById('move-day-row').style.display!=='none'
      ? document.getElementById('a_move_day').value : did;
    if(!isNew&&moveTo&&moveTo!==did){
      moveAct(did,id,obj,moveTo);
      curDay=moveTo;_overviewChosen=false;   // 跟著跳到目的地那天，否則活動看起來像消失了
      closeM('m-act');
      return;
    }
    closeM('m-act');toast('✅ 已儲存');
  });
}
```

改成：

```js
function saveAct(){
  const did=document.getElementById('ma-did').value,aid=document.getElementById('ma-aid').value;
  const name=document.getElementById('a_name').value.trim();if(!name){toast('請輸入活動名稱');return;}
  const costs=curActCosts.map(c=>({desc:(c.desc||'').trim(),amt:parseFloat(c.amt),cur:c.cur||DEF_CUR,paidBy:c.paidBy||CFG.members[0],split:c.split||'both'})).filter(c=>!isNaN(c.amt)&&c.amt>0);
  DB.ref('/schedule/'+did).once('value',daySnap=>{
    const dayData=daySnap.val()||{};
    const existingActs=Object.values(dayData.acts||{});
    const maxOrder=existingActs.length?Math.max(...existingActs.map(a=>a.order||0)):0;
    const isNew=!aid;
    const customIco=document.getElementById('a_custom_ico').value.trim();
    const geoQ=document.getElementById('a_geoq').value.trim();
    const obj={cat:curAC,name,
      ...(curAC==='custom'&&customIco?{customIco}:{}),
      images:curActImages.length?[...curActImages]:null,
      loc:document.getElementById('a_loc').value.trim(),note:document.getElementById('a_note').value.trim(),
      ...(geoQ?{geoQ}:{}),
      // 類型改成交通／住宿之後那排圓圈就藏起來了，此時把 closed 一起清掉；
      // 否則畫面上看不到、卻還會冒出「⚠️ 公休日」，怎麼點都關不掉。
      closed:(!NO_CLOSED_CATS.includes(curAC)&&curClosed.length)?[...curClosed]:null,
      stay:curAC==='hotel'?{
        out:document.getElementById('a_stay_out').value||null,
        ci:document.getElementById('a_stay_ci').value.trim()||null,
        co:document.getElementById('a_stay_co').value.trim()||null,
        arr:document.getElementById('a_stay_arr').value.trim()||null,
        src:curStay?.src||null,
      }:null,
      costs:costs.length?costs:null,
      order:isNew?(maxOrder+1):curActOrder};
    const id=aid||('a'+uid());
    // 這裡是整筆 set，obj 沒有 geo 欄位，所以不特別處理的話「改個備註」都會把
    // 已經查好的座標洗掉、下次開 app 再跑一次地理編碼。定位字串沒變就把座標帶回來；
    // 變了才讓它重查，這也正是使用者填「定位用地名」之後期待發生的事。
    const prev=(dayData.acts||{})[id];
    if(prev&&geoQueryOf(prev)===geoQueryOf(obj)){
      if(prev.geo)obj.geo=prev.geo;
      if(prev.geoFail)obj.geoFail=prev.geoFail;
    }
    DB.ref('/schedule/'+did+'/acts/'+id).set(obj);
    DB.ref('/expenses/actcost_'+did+'_'+id).remove();
    const prevCostCount=actCostList(prev).length;
    costs.forEach((c,i)=>{
      DB.ref('/expenses/actcost_'+did+'_'+id+'_'+i).set({desc:c.desc||name,amt:c.amt,cur:c.cur,cat:mapActCat(curAC),paidBy:c.paidBy,split:c.split,date:dayData.date||'',fromAct:true,at:new Date().toISOString()});
    });
    for(let i=costs.length;i<prevCostCount;i++)DB.ref('/expenses/actcost_'+did+'_'+id+'_'+i).remove();
    // 編輯模式下若選了別天，先存回原處再整筆搬過去（moveAct 會一併處理記帳的日期）
    const moveTo=document.getElementById('move-day-row').style.display!=='none'
      ? document.getElementById('a_move_day').value : did;
    if(!isNew&&moveTo&&moveTo!==did){
      moveAct(did,id,obj,moveTo);
      curDay=moveTo;_overviewChosen=false;   // 跟著跳到目的地那天，否則活動看起來像消失了
      closeM('m-act');
      return;
    }
    closeM('m-act');toast('✅ 已儲存');
  });
}
```

- [ ] **Step 4: 改寫 `delAct`**

跟 Task 2 Step 4 完全相同的 old/new 內容（`delAct` 在 couple-trip-template.html 逐字相同）。

- [ ] **Step 5: 改寫 `moveAct`**

把：

```js
function moveAct(fromDid,aid,act,toDid){
  DB.ref('/schedule/'+toDid+'/date').once('value',snap=>{
    const newDate=snap.val()||'';
    DB.ref('/schedule/'+toDid+'/acts/'+aid).set(act);
    DB.ref('/schedule/'+fromDid+'/acts/'+aid).remove();
    if(act.cost?.amt>0){
      DB.ref('/expenses/actcost_'+fromDid+'_'+aid).remove();
      DB.ref('/expenses/actcost_'+toDid+'_'+aid).set({desc:act.name,amt:act.cost.amt,cur:act.cost.cur||DEF_CUR,cat:mapActCat(act.cat),paidBy:act.cost.paidBy||CFG.members[0],split:act.cost.split||'both',date:newDate,fromAct:true,at:new Date().toISOString()});
    }
    toast('✅ 已移動到 '+toDid.replace('day','Day '));
  });
}
```

改成：

```js
function moveAct(fromDid,aid,act,toDid){
  DB.ref('/schedule/'+toDid+'/date').once('value',snap=>{
    const newDate=snap.val()||'';
    DB.ref('/schedule/'+toDid+'/acts/'+aid).set(act);
    DB.ref('/schedule/'+fromDid+'/acts/'+aid).remove();
    DB.ref('/expenses/actcost_'+fromDid+'_'+aid).remove();
    actCostList(act).forEach((c,i)=>{
      DB.ref('/expenses/actcost_'+fromDid+'_'+aid+'_'+i).remove();
      DB.ref('/expenses/actcost_'+toDid+'_'+aid+'_'+i).set({desc:c.desc||act.name,amt:c.amt,cur:c.cur||DEF_CUR,cat:mapActCat(act.cat),paidBy:c.paidBy||CFG.members[0],split:c.split||'both',date:newDate,fromAct:true,at:new Date().toISOString()});
    });
    toast('✅ 已移動到 '+toDid.replace('day','Day '));
  });
}
```

- [ ] **Step 6: 改寫行程卡片的花費顯示**

用 grep 找到位置：

```bash
grep -n "const sym=curSym(act.cost" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/couple-trip-template.html"
```

把：

```js
            const sym=curSym(act.cost?.cur||DEF_CUR);
            const dp=0;
```

改成：

```js
            const dp=0;
```

再把：

```js
                ${act.cost?.amt>0?`<div class="act-cost">💰 ${sym}${parseFloat(act.cost.amt).toFixed(dp)} ${act.cost.cur||DEF_CUR}</div>`:''}
```

改成：

```js
                ${actCostList(act).map(c=>`<div class="act-cost">💰 ${c.desc?esc(c.desc)+' ':''}${curSym(c.cur||DEF_CUR)}${parseFloat(c.amt||0).toFixed(dp)} ${c.cur||DEF_CUR}</div>`).join('')}
```

- [ ] **Step 7: `_selftest()` 新增 `actCostList` 測試**

跟 Task 2 Step 7 完全相同的插入內容與插入點（couple-trip-template.html 的 `_selftest()` 開頭跟 iceland 逐字相同）。

- [ ] **Step 8: 執行 selftest + 假 DB 驗證**

跟 Task 2 的 Step 8～9 做法相同，改開 `http://localhost:8765/couple-trip-template.html`。**額外驗證拆帳欄位**：在 Task 2 Step 9 的第一段腳本裡，把 `curActCosts[0]`/`curActCosts[1]` 多帶一個 `split` 欄位：

```js
curActCosts[0]={desc:'門票',amt:'1200',cur:'JPY',paidBy:'Mike',split:'p1'};
curActCosts[1]={desc:'午餐',amt:'350',cur:'JPY',paidBy:'Monica',split:'both'};
```

儲存後確認 `window.__writes` 裡 `/expenses/actcost_day1_atest1_0` 那筆的 `v.split==='p1'`、`_1` 那筆 `v.split==='both'`。其餘步驟（刪行清理孤兒記錄）跟 Task 2 Step 9 相同。驗證完關閉 http server。

- [ ] **Step 9: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add couple-trip-template.html
git commit -m "$(cat <<'EOF'
feat(couple): 多筆花費逐行同步記帳（含拆帳），卡片逐行顯示

同 iceland-trip.html 的實作（見該次 commit 說明）。每行的 split 欄位
跟著該行一起存進對應的 actcost_{did}_{aid}_{n} 記帳紀錄，calcBal()
本來就是掃 /expenses 平面清單算結算，不用改。
EOF
)"
```

---

## Task 7: us-trip.html — 工具函式、CSS、表單 HTML、狀態與渲染函式（含拆帳）

**Files:**
- Modify: `us-trip.html`（`mapActCat` 後面插入 `actCostList`）
- Modify: `us-trip.html:124`（CSS）
- Modify: `us-trip.html:532-543`（cost-box HTML）
- Modify: `us-trip.html:630`（`curActCosts`）
- Modify: `us-trip.html`（新增花費多行函式含拆帳，刪除 `selACur`/`selAPayer`/`selASplit`）

us-trip.html 這幾塊跟 couple-trip-template.html 逐字相同（已用 diff 核對過）。

- [ ] **Step 1～5**：依序對照 Task 5 的 Step 1～5，對 `us-trip.html` 做完全相同的 Edit（cost-box HTML／`curActCosts`／花費多行函式的 old/new 內容都跟 couple 版一致）。

- [ ] **Step 6: 確認沒有語法錯誤**

用 Playwright 開 `http://localhost:8765/us-trip.html`（背景起 http server），確認 console 無錯誤。

- [ ] **Step 7: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add us-trip.html
git commit -m "$(cat <<'EOF'
feat(us): 活動花費表單改可加多行，每行各自拆帳

同 couple-trip-template.html 的實作（見該次 commit 說明），這段程式碼
兩支逐字相同。
EOF
)"
```

---

## Task 8: us-trip.html — 儲存/搬動/刪除同步、卡片顯示、selftest（含拆帳）

**Files:**
- Modify: `us-trip.html:2634-2648`（`openActM`）
- Modify: `us-trip.html:2649-2679`（`openActEdit`）
- Modify: `us-trip.html:2688-2742`（`saveAct`）
- Modify: `us-trip.html:2742`（`delAct`）
- Modify: `us-trip.html:2134-2150`（`moveAct`）
- Modify: `us-trip.html`（行程卡片花費顯示那行）
- Modify: `us-trip.html`（`_selftest()` 新增 `actCostList` 測試）

us-trip.html 這幾個函式跟 couple-trip-template.html 逐字相同（已用 diff 核對過）。

- [ ] **Step 1～7**：依序對照 Task 6 的 Step 1～7，對 `us-trip.html` 做完全相同的 Edit（`openActM`／`openActEdit`／`saveAct`／`delAct`／`moveAct`／卡片花費顯示／`_selftest()` 插入內容全部跟 couple 版一致）。

- [ ] **Step 8: 執行 selftest + 假 DB 驗證**

跟 Task 6 Step 8 做法相同（含拆帳欄位驗證），改開 `http://localhost:8765/us-trip.html`。驗證完關閉 http server。

- [ ] **Step 9: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add us-trip.html
git commit -m "$(cat <<'EOF'
feat(us): 多筆花費逐行同步記帳（含拆帳），卡片逐行顯示

同 couple-trip-template.html 的實作（見該次 commit 說明），這段程式碼
兩支逐字相同。
EOF
)"
```

---

## Task 9: 收尾檢查

**Files:**
- 無新增/修改檔案，只做驗證

- [ ] **Step 1: 四支各自再跑一次完整 `_selftest()`**

依序對四個檔案執行（沿用同一個 http server）：

```js
_selftest()
```

四支都要是「失敗 0」。

- [ ] **Step 2: 停掉本機測試伺服器**

```bash
lsof -ti:8765 | xargs kill
```

- [ ] **Step 3: 確認 git log 八個 feature commit 都在**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git log --oneline -10
```

預期看到本次 8 個 commit（每支各 2 個：表單層一個、儲存同步層一個）。

- [ ] **Step 4: 提醒使用者手動部署**

不要自己執行部署——四支都是 Netlify **手動拖拉部署**，commit 不等於上線。跟使用者說完成了、需要她自己手動把四支拖去各自的 Netlify。
