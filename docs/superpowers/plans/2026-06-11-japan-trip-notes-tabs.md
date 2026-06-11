# Japan Trip App — Notes Tab + Tab Redesign + Rich Activity Notes

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** Add URL autolink + image upload to activity notes; merge 記帳/統計 into one tab with sub-toggle; add 記事本 tab with 記事 and 待辦清單 cards stored in Firebase.

**Architecture:** All changes in `japan-trip.html` (single-file PWA). New JS functions appended before closing `</script>`. New CSS appended before closing `</style>`. New modals appended before `</body>`. Firebase path `/notes/` for all note data.

**Tech Stack:** Vanilla JS, Firebase Realtime DB (compat 9.23), HTML Canvas (image compress), CSS variables (Morandi palette already in place).

---

## File Map

| Section | Location | Change |
|---------|----------|--------|
| CSS | before `</style>` (~line 205) | Add: acc-toggle, note-card, todo-item, act-img-thumb, lightbox |
| Global vars | line 461, 465 | Add: `curAcc`, `lastNotes`, `curActImages` |
| FAB menu HTML | lines 319–323 | Add note FAB items (hidden by default) |
| Tabbar HTML | lines 325–329 | Replace: 統計→記事本, update IDs |
| Page panels HTML | lines 256–275 | Add acc-toggle + statContent inside page-exp; rename page-stat→page-note |
| Activity modal HTML | after line 354 (note textarea) | Add image upload section |
| `goTab()` | line 707 | Update: note tab handling, FAB visibility, FAB colour |
| `fabTap()` | line 718 | Update: note tab opens note FAB menu |
| act-row render | line 938 | `esc(act.note)` → `autolink(act.note)`; add image thumbnails |
| `openActM()` | line ~963 | Reset `curActImages=[]` |
| `openActEdit()` | line ~974 | Restore `curActImages` from `a.images` |
| `saveAct()` | line ~997 | Include `images:curActImages` in saved obj |
| `_fbListen()` | line ~685 | Add `/notes` listener → `renderNotes` |
| New functions | before `</script>` | autolink, compressImage, note CRUD, todo CRUD, renderNotes, switchAcc, lightbox |
| New modals HTML | before `</body>` | 記事 modal, 待辦清單 modal, lightbox overlay |

---

## Task 1 — Utility Functions: `autolink` + `compressImage`

**Files:** Modify `japan-trip.html` — append to JS block before `</script>`

- [ ] **Step 1: Find closing script tag**

```bash
grep -n "</script>" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/japan-trip.html" | tail -1
```

- [ ] **Step 2: Add utility functions before `</script>`**

Insert the following two functions immediately before the final `</script>`:

```javascript
// ─── Utilities ───────────────────────────────────────
function autolink(text){
  if(!text)return'';
  return text.split(/(https?:\/\/\S+)/).map((part,i)=>{
    if(i%2===1)return`<a href="${part}" target="_blank" rel="noopener" style="color:var(--blue);word-break:break-all">${esc(part)}</a>`;
    return esc(part);
  }).join('');
}
function compressImage(file){
  return new Promise(resolve=>{
    const img=new Image(),url=URL.createObjectURL(file);
    img.onload=()=>{
      URL.revokeObjectURL(url);
      const max=800,scale=Math.min(1,max/Math.max(img.width,img.height));
      const w=Math.round(img.width*scale),h=Math.round(img.height*scale);
      const c=document.createElement('canvas');c.width=w;c.height=h;
      c.getContext('2d').drawImage(img,0,0,w,h);
      resolve(c.toDataURL('image/jpeg',0.7));
    };
    img.src=url;
  });
}
function openLightbox(src){
  document.getElementById('lb-img').src=src;
  openM('m-lb');
}
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add japan-trip.html
git commit -m "feat: add autolink, compressImage, openLightbox utilities"
```

---

## Task 2 — CSS: New Component Styles

**Files:** Modify `japan-trip.html` — append CSS before `</style>`

- [ ] **Step 1: Find closing style tag**

```bash
grep -n "</style>" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/japan-trip.html" | head -1
```

- [ ] **Step 2: Insert CSS before `</style>`**

```css
/* ── Acc sub-toggle ── */
.acc-toggle{display:flex;background:var(--bg);border-radius:10px;padding:3px;gap:3px;margin-bottom:12px;}
.acc-opt{flex:1;padding:8px 4px;text-align:center;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600;color:var(--muted);transition:all .15s;}
.acc-opt.on{background:var(--card);color:var(--blue);box-shadow:0 1px 4px rgba(0,0,0,.1);}
/* ── Activity images ── */
.act-imgs{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;}
.act-img-thumb{width:64px;height:64px;object-fit:cover;border-radius:8px;cursor:pointer;border:1px solid var(--border);}
.img-preview-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;}
.img-preview-item{position:relative;width:72px;height:72px;}
.img-preview-item img{width:100%;height:100%;object-fit:cover;border-radius:8px;border:1px solid var(--border);}
.img-preview-rm{position:absolute;top:-6px;right:-6px;width:18px;height:18px;border-radius:50%;background:var(--red);color:#fff;border:none;font-size:11px;cursor:pointer;display:flex;align-items:center;justify-content:center;line-height:1;}
/* ── Note cards ── */
.note-card{margin-bottom:10px;}
.note-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;}
.note-title{font-size:15px;font-weight:700;color:var(--text);}
.note-preview{font-size:13px;color:var(--muted);line-height:1.5;margin-bottom:6px;}
.note-thumbs{display:flex;gap:6px;flex-wrap:wrap;}
/* ── Todo items ── */
.todo-items{display:flex;flex-direction:column;gap:4px;margin-top:4px;}
.todo-item{padding:6px 2px;border-bottom:1px solid var(--border);font-size:14px;}
.todo-item:last-child{border-bottom:none;}
/* ── Lightbox ── */
#m-lb{background:rgba(0,0,0,.88);display:flex;align-items:center;justify-content:center;}
#m-lb img{max-width:100%;max-height:90dvh;object-fit:contain;border-radius:8px;}
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add japan-trip.html
git commit -m "feat: add CSS for acc-toggle, act-images, note cards, lightbox"
```

---

## Task 3 — Activity Modal: Image Upload UI

**Files:** Modify `japan-trip.html`

- [ ] **Step 1: Add global `curActImages` variable**

Find line containing `let curNT=`:
```bash
grep -n "let curNT=" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/japan-trip.html"
```

Replace:
```javascript
let curNT='text',curImg=null,curPieCur='JPY',lastExps={},exchRate=null;
```
With:
```javascript
let curNT='text',curImg=null,curPieCur='JPY',lastExps={},lastNotes={},exchRate=null,curActImages=[];
```

- [ ] **Step 2: Add image section to activity modal HTML**

Find the note textarea line:
```bash
grep -n "a_note.*placeholder" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/japan-trip.html"
```

After the `<div class="fg">...<textarea ... id="a_note"...></textarea></div>` block, insert:

```html
    <div class="fg">
      <label class="lb">圖片（最多 2 張）</label>
      <div id="act-img-previews" class="img-preview-row"></div>
      <button type="button" class="btn btn-g" style="margin-top:6px;font-size:13px;padding:8px 12px" onclick="document.getElementById('actImgFile').click()" id="act-img-btn">📷 新增圖片</button>
      <input type="file" id="actImgFile" accept="image/*" style="display:none" onchange="onActImgPick(event)">
    </div>
```

- [ ] **Step 3: Add `onActImgPick`, reset/restore logic before `</script>`**

```javascript
function onActImgPick(e){
  const file=e.target.files[0];if(!file)return;
  e.target.value='';
  if(curActImages.length>=2){toast('最多 2 張圖片');return;}
  compressImage(file).then(b64=>{
    curActImages.push(b64);
    renderActImgPreviews();
  });
}
function renderActImgPreviews(){
  const el=document.getElementById('act-img-previews');
  el.innerHTML=curActImages.map((b,i)=>`<div class="img-preview-item"><img src="${b}"><button class="img-preview-rm" onclick="removeActImg(${i})">✕</button></div>`).join('');
  document.getElementById('act-img-btn').style.display=curActImages.length>=2?'none':'';
}
function removeActImg(i){curActImages.splice(i,1);renderActImgPreviews();}
```

- [ ] **Step 4: Reset `curActImages` in `openActM()`**

Find line in `openActM` that resets `a_custom_ico`:
```bash
grep -n "a_custom_ico.*value.*''" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/japan-trip.html"
```

On that same line (or the next), also add:
```javascript
curActImages=[];renderActImgPreviews();
```

So the full reset line becomes:
```javascript
document.getElementById('a_custom_ico').value='';document.getElementById('custom-ico-row').style.display='none';
curActImages=[];renderActImgPreviews();
```

- [ ] **Step 5: Restore images in `openActEdit()`**

Find line in `openActEdit` that sets `a_custom_ico.value`:
```bash
grep -n "a_custom_ico.*value.*a\.customIco" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/japan-trip.html"
```

After that line, add:
```javascript
curActImages=a.images?[...a.images]:[];renderActImgPreviews();
```

- [ ] **Step 6: Include `images` in `saveAct()` obj**

Find line in `saveAct`:
```bash
grep -n "const customIco=document" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/japan-trip.html"
```

In the `obj` definition below it, after `...(curAC==='custom'...)`, add:
```javascript
images:curActImages.length?[...curActImages]:null,
```

Full `obj` becomes:
```javascript
const obj={cat:curAC,name,
  ...(curAC==='custom'&&customIco?{customIco}:{}),
  images:curActImages.length?[...curActImages]:null,
  loc:document.getElementById('a_loc').value.trim(),note:document.getElementById('a_note').value.trim(),
  cost:hasCost?{amt:costAmt,cur:curACur,paidBy:curAPayer===0?CFG.p1:CFG.p2,split:curASplit}:null,
  order:isNew?(maxOrder+1):curActOrder};
```

- [ ] **Step 7: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add japan-trip.html
git commit -m "feat: activity image upload — compress, preview, save to Firebase"
```

---

## Task 4 — Activity Card: Show Images + Lightbox + Autolink Note

**Files:** Modify `japan-trip.html`

- [ ] **Step 1: Replace note render + add image thumbnails in act-row**

Find:
```bash
grep -n "act\.note.*esc.*act\.note" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/japan-trip.html"
```

Replace the note line:
```javascript
${act.note?`<div class="act-note-t">💬 ${esc(act.note)}</div>`:''}
```
With:
```javascript
${act.note?`<div class="act-note-t">💬 ${autolink(act.note)}</div>`:''}
${act.images?.length?`<div class="act-imgs">${act.images.map(b=>`<img class="act-img-thumb" src="${b}" onclick="openLightbox('${b}')">`).join('')}</div>`:''}
```

- [ ] **Step 2: Add lightbox modal HTML before `</body>`**

```bash
grep -n "</body>" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/japan-trip.html"
```

Insert before `</body>`:
```html
<!-- Lightbox -->
<div class="ov" id="m-lb" onclick="closeM('m-lb')">
  <img id="lb-img" src="" alt="">
</div>
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add japan-trip.html
git commit -m "feat: activity card shows image thumbnails and autolinks note URLs"
```

---

## Task 5 — Tab Restructure: HTML + goTab + fabTap

**Files:** Modify `japan-trip.html`

- [ ] **Step 1: Replace tabbar HTML**

Find lines 325–329 (tabbar divs). Replace entire tabbar content:
```html
  <div class="tabbar">
    <div class="ti on" id="t-sched" onclick="goTab('sched')"><span class="ti-i">📅</span><span class="ti-l">行程</span></div>
    <div class="ti"    id="t-exp"   onclick="goTab('exp')"  ><span class="ti-i">💴</span><span class="ti-l">記帳</span></div>
    <div class="ti"    id="t-stat"  onclick="goTab('stat')" ><span class="ti-i">📊</span><span class="ti-l">統計</span></div>
    <div class="ti"    id="t-cfg"   onclick="goTab('cfg')"  ><span class="ti-i">⚙️</span><span class="ti-l">設定</span></div>
  </div>
```
With:
```html
  <div class="tabbar">
    <div class="ti on" id="t-sched" onclick="goTab('sched')"><span class="ti-i">📅</span><span class="ti-l">行程</span></div>
    <div class="ti"    id="t-exp"   onclick="goTab('exp')"  ><span class="ti-i">💴</span><span class="ti-l">記帳</span></div>
    <div class="ti"    id="t-note"  onclick="goTab('note')" ><span class="ti-i">📒</span><span class="ti-l">記事本</span></div>
    <div class="ti"    id="t-cfg"   onclick="goTab('cfg')"  ><span class="ti-i">⚙️</span><span class="ti-l">設定</span></div>
  </div>
```

- [ ] **Step 2: Restructure page panels HTML**

Find lines 256–275 (page divs). Replace:
```html
    <div class="page on" id="page-sched">
      <div class="bx" id="schedBox">
        <div class="empty"><div class="empty-i">📅</div><div class="empty-h">載入中…</div></div>
      </div>
    </div>

    <div class="page" id="page-exp">
      <div class="bx">
        <div id="balSec"></div>
        <div id="expList"></div>
      </div>
    </div>

    <div class="page" id="page-stat">
      <div class="bx">
        <div id="pieSec"></div>
        <div id="personSec"></div>
      </div>
    </div>
```
With:
```html
    <div class="page on" id="page-sched">
      <div class="bx" id="schedBox">
        <div class="empty"><div class="empty-i">📅</div><div class="empty-h">載入中…</div></div>
      </div>
    </div>

    <div class="page" id="page-exp">
      <div class="bx">
        <div class="acc-toggle">
          <div class="acc-opt on" id="acc-exp" onclick="switchAcc('exp')">支出清單</div>
          <div class="acc-opt"    id="acc-stat" onclick="switchAcc('stat')">統計圖表</div>
        </div>
        <div id="expContent">
          <div id="balSec"></div>
          <div id="expList"></div>
        </div>
        <div id="statContent" style="display:none">
          <div id="pieSec"></div>
          <div id="personSec"></div>
        </div>
      </div>
    </div>

    <div class="page" id="page-note">
      <div class="bx" id="noteList">
        <div class="empty"><div class="empty-i">📒</div><div class="empty-h">尚無記事</div></div>
      </div>
    </div>
```

- [ ] **Step 3: Update FAB menu HTML — add note FAB items**

Find the fabMenu div (currently has 2 items). Replace entire `<div class="fab-menu" id="fabMenu">...</div>`:
```html
  <div class="fab-menu" id="fabMenu">
    <div class="fab-item exp-fab" onclick="closeFabMenu();openExpM()">✏️ 手動輸入</div>
    <div class="fab-item exp-fab" onclick="closeFabMenu();document.getElementById('receiptFile').click()">📷 掃描收據</div>
    <div class="fab-item note-fab" style="display:none" onclick="closeFabMenu();openNoteM('note')">📝 新增記事</div>
    <div class="fab-item note-fab" style="display:none" onclick="closeFabMenu();openNoteM('todo')">✅ 新增待辦</div>
  </div>
```

- [ ] **Step 4: Add `curAcc` to global vars**

Find `let CFG={},DB=null,curTab='sched';` and replace with:
```javascript
let CFG={},DB=null,curTab='sched',curAcc='exp';
```

- [ ] **Step 5: Replace `goTab` function**

Find and replace the entire `goTab` function:
```javascript
function goTab(t){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('on'));
  document.querySelectorAll('.ti').forEach(x=>x.classList.remove('on'));
  document.getElementById('page-'+t).classList.add('on');
  document.getElementById('t-'+t).classList.add('on');
  curTab=t;
  const fab=document.getElementById('fab');
  fab.style.display=(t==='cfg')?'none':'flex';
  fab.style.background=t==='exp'?'var(--orange)':(t==='note'?'var(--green)':'var(--blue)');
  document.querySelectorAll('.exp-fab').forEach(el=>el.style.display=t==='exp'?'':'none');
  document.querySelectorAll('.note-fab').forEach(el=>el.style.display=t==='note'?'':'none');
  closeFabMenu();
}
```

- [ ] **Step 6: Update `fabTap` function**

Find and replace the entire `fabTap` function:
```javascript
function fabTap(){
  if(curTab==='sched'){openActM('day1');return;}
  if(curTab==='exp'||curTab==='note'){
    fabMenuOpen=!fabMenuOpen;
    document.getElementById('fabMenu').classList.toggle('open',fabMenuOpen);
  }
}
```

- [ ] **Step 7: Add `switchAcc` function before `</script>`**

```javascript
function switchAcc(t){
  curAcc=t;
  document.getElementById('expContent').style.display=t==='exp'?'':'none';
  document.getElementById('statContent').style.display=t==='stat'?'':'none';
  document.getElementById('acc-exp').classList.toggle('on',t==='exp');
  document.getElementById('acc-stat').classList.toggle('on',t==='stat');
  if(t==='stat')renderStat(lastExps);
}
```

- [ ] **Step 8: Remove stat tab reference from `renderStat` / `bootApp` if needed**

Verify `renderStat` still targets `#pieSec` and `#personSec` (those IDs are preserved inside `statContent`):
```bash
grep -n "pieSec\|personSec" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/japan-trip.html" | grep -v base64
```
No changes needed if it targets those IDs directly.

- [ ] **Step 9: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add japan-trip.html
git commit -m "feat: tab restructure — merge 記帳/統計, add 記事本 tab"
```

---

## Task 6 — Firebase Notes Listener + `renderNotes`

**Files:** Modify `japan-trip.html`

- [ ] **Step 1: Add notes listener in `_fbListen`**

Find inside `_fbListen`:
```javascript
  lastExps=d.expenses||{};
```

After that line add:
```javascript
  lastNotes=d.notes||{};
  renderNotes(lastNotes);
```

- [ ] **Step 2: Add `renderNotes` + `renderNoteCard` before `</script>`**

```javascript
// ─── Notes ───────────────────────────────────────────
function renderNotes(notes){
  const list=Object.entries(notes||{}).sort((a,b)=>(b[1].createdAt||'').localeCompare(a[1].createdAt||''));
  const el=document.getElementById('noteList');
  if(!el)return;
  if(!list.length){el.innerHTML='<div class="empty"><div class="empty-i">📒</div><div class="empty-h">尚無記事，點 ＋ 新增</div></div>';return;}
  el.innerHTML=list.map(([nid,n])=>renderNoteCard(nid,n)).join('');
}
function renderNoteCard(nid,n){
  if(n.type==='note'){
    const preview=esc((n.content||'').slice(0,80))+(n.content?.length>80?'…':'');
    const thumbs=(n.images||[]).map(b=>`<img class="act-img-thumb" src="${b}" onclick="openLightbox('${b}')">`).join('');
    return`<div class="card note-card">
      <div class="note-hdr">
        <div class="note-title">📝 ${esc(n.title||'（無標題）')}</div>
        <div style="display:flex;gap:4px">
          <button class="ib" onclick="openNoteEdit('${nid}')">✎</button>
          <button class="ib" onclick="delNote('${nid}')">✕</button>
        </div>
      </div>
      ${preview?`<div class="note-preview">${preview}</div>`:''}
      ${thumbs?`<div class="note-thumbs">${thumbs}</div>`:''}
    </div>`;
  }
  // todo
  const total=n.items?.length||0,doneCount=(n.items||[]).filter(x=>x.done).length;
  const items=(n.items||[]).map((item,i)=>`
    <div class="todo-item">
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
        <input type="checkbox" ${item.done?'checked':''} onchange="toggleTodoItem('${nid}',${i},this.checked)" style="width:16px;height:16px;accent-color:var(--green)">
        <span style="${item.done?'text-decoration:line-through;color:var(--muted)':''}">${esc(item.text||'')}</span>
      </label>
    </div>`).join('');
  return`<div class="card note-card">
    <div class="note-hdr">
      <div class="note-title">✅ ${esc(n.title||'待辦清單')}</div>
      <div style="display:flex;align-items:center;gap:6px">
        <span style="font-size:11px;color:var(--muted)">${doneCount}/${total}</span>
        <button class="ib" onclick="openTodoEdit('${nid}')">✎</button>
        <button class="ib" onclick="delNote('${nid}')">✕</button>
      </div>
    </div>
    <div class="todo-items">${items}</div>
  </div>`;
}
function toggleTodoItem(nid,idx,done){
  DB.ref('/notes/'+nid+'/items/'+idx+'/done').set(done);
}
function delNote(nid){
  if(!confirm('確定刪除？'))return;
  DB.ref('/notes/'+nid).remove();
  toast('🗑️ 已刪除');
}
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add japan-trip.html
git commit -m "feat: Firebase notes listener, renderNotes, renderNoteCard, toggleTodoItem"
```

---

## Task 7 — 記事 Modal + CRUD

**Files:** Modify `japan-trip.html`

- [ ] **Step 1: Add 記事 modal HTML before `</body>`**

```html
<!-- Note modal -->
<div class="ov" id="m-note">
  <div class="sheet">
    <div class="hdl"></div>
    <div class="st" id="m-note-t">新增記事</div>
    <input type="hidden" id="mn-id">
    <div class="fg"><label class="lb">標題</label><input class="inp" id="n_title" placeholder="記事標題…"></div>
    <div class="fg"><label class="lb">內容</label><textarea class="ta" id="n_content" placeholder="記錄想法、資訊…" rows="5"></textarea></div>
    <div class="fg">
      <label class="lb">圖片（最多 2 張）</label>
      <div id="note-img-previews" class="img-preview-row"></div>
      <button type="button" class="btn btn-g" style="margin-top:6px;font-size:13px;padding:8px 12px" onclick="document.getElementById('noteImgFile').click()" id="note-img-btn">📷 新增圖片</button>
      <input type="file" id="noteImgFile" accept="image/*" style="display:none" onchange="onNoteImgPick(event)">
    </div>
    <div class="fr"><button class="btn btn-g" style="flex:1" onclick="closeM('m-note')">取消</button><button class="btn btn-b" style="flex:2" onclick="saveNote()">儲存</button></div>
  </div>
</div>
```

- [ ] **Step 2: Add note image state variable + functions before `</script>`**

```javascript
let curNoteImages=[];
function onNoteImgPick(e){
  const file=e.target.files[0];if(!file)return;
  e.target.value='';
  if(curNoteImages.length>=2){toast('最多 2 張圖片');return;}
  compressImage(file).then(b64=>{curNoteImages.push(b64);renderNoteImgPreviews();});
}
function renderNoteImgPreviews(){
  const el=document.getElementById('note-img-previews');
  el.innerHTML=curNoteImages.map((b,i)=>`<div class="img-preview-item"><img src="${b}"><button class="img-preview-rm" onclick="removeNoteImg(${i})">✕</button></div>`).join('');
  document.getElementById('note-img-btn').style.display=curNoteImages.length>=2?'none':'';
}
function removeNoteImg(i){curNoteImages.splice(i,1);renderNoteImgPreviews();}
function openNoteM(type){
  if(type!=='note')return openTodoM();
  document.getElementById('m-note-t').textContent='新增記事';
  document.getElementById('mn-id').value='';
  document.getElementById('n_title').value='';
  document.getElementById('n_content').value='';
  curNoteImages=[];renderNoteImgPreviews();
  openM('m-note');setTimeout(()=>document.getElementById('n_title').focus(),280);
}
function openNoteEdit(nid){
  const n=lastNotes[nid];if(!n)return;
  document.getElementById('m-note-t').textContent='編輯記事';
  document.getElementById('mn-id').value=nid;
  document.getElementById('n_title').value=n.title||'';
  document.getElementById('n_content').value=n.content||'';
  curNoteImages=n.images?[...n.images]:[];renderNoteImgPreviews();
  openM('m-note');
}
function saveNote(){
  const nid=document.getElementById('mn-id').value||('n'+uid());
  const title=document.getElementById('n_title').value.trim();
  const content=document.getElementById('n_content').value.trim();
  const now=new Date().toISOString();
  const existing=lastNotes[nid];
  const obj={type:'note',title,content,
    images:curNoteImages.length?[...curNoteImages]:null,
    createdAt:existing?.createdAt||now,updatedAt:now};
  DB.ref('/notes/'+nid).set(obj);
  closeM('m-note');toast('✅ 已儲存');
}
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add japan-trip.html
git commit -m "feat: 記事 modal — create, edit, delete with image upload"
```

---

## Task 8 — 待辦清單 Modal + CRUD

**Files:** Modify `japan-trip.html`

- [ ] **Step 1: Add 待辦清單 modal HTML before `</body>`**

```html
<!-- Todo modal -->
<div class="ov" id="m-todo">
  <div class="sheet">
    <div class="hdl"></div>
    <div class="st" id="m-todo-t">新增待辦清單</div>
    <input type="hidden" id="mt-id">
    <div class="fg"><label class="lb">標題</label><input class="inp" id="t_title" placeholder="清單名稱…"></div>
    <div class="fg">
      <label class="lb">項目</label>
      <div id="todo-items-edit"></div>
      <div style="display:flex;gap:8px;margin-top:8px">
        <input class="inp" id="t_new_item" placeholder="新增項目…" style="flex:1" onkeydown="if(event.key==='Enter'){addTodoItem();event.preventDefault();}">
        <button class="btn btn-b" style="flex:0 0 60px;padding:0" onclick="addTodoItem()">＋</button>
      </div>
    </div>
    <div class="fr"><button class="btn btn-g" style="flex:1" onclick="closeM('m-todo')">取消</button><button class="btn btn-b" style="flex:2" onclick="saveTodo()">儲存</button></div>
  </div>
</div>
```

- [ ] **Step 2: Add todo CRUD functions before `</script>`**

```javascript
let curTodoItems=[];
function renderTodoItemsEdit(){
  document.getElementById('todo-items-edit').innerHTML=curTodoItems.map((item,i)=>`
    <div style="display:flex;align-items:center;gap:6px;padding:6px 0;border-bottom:1px solid var(--border)">
      <span style="flex:1;font-size:14px">${esc(item.text)}</span>
      <button class="ib" onclick="removeTodoItem(${i})">✕</button>
    </div>`).join('');
}
function addTodoItem(){
  const inp=document.getElementById('t_new_item');
  const text=inp.value.trim();if(!text)return;
  curTodoItems.push({text,done:false});
  inp.value='';
  renderTodoItemsEdit();
}
function removeTodoItem(i){curTodoItems.splice(i,1);renderTodoItemsEdit();}
function openTodoM(){
  document.getElementById('m-todo-t').textContent='新增待辦清單';
  document.getElementById('mt-id').value='';
  document.getElementById('t_title').value='';
  curTodoItems=[];renderTodoItemsEdit();
  openM('m-todo');setTimeout(()=>document.getElementById('t_title').focus(),280);
}
function openTodoEdit(nid){
  const n=lastNotes[nid];if(!n)return;
  document.getElementById('m-todo-t').textContent='編輯待辦清單';
  document.getElementById('mt-id').value=nid;
  document.getElementById('t_title').value=n.title||'';
  curTodoItems=n.items?n.items.map(x=>({...x})):[];
  renderTodoItemsEdit();
  openM('m-todo');
}
function saveTodo(){
  const nid=document.getElementById('mt-id').value||('n'+uid());
  const title=document.getElementById('t_title').value.trim();
  if(!curTodoItems.length){toast('請新增至少一個項目');return;}
  const now=new Date().toISOString();
  const existing=lastNotes[nid];
  const obj={type:'todo',title,items:[...curTodoItems],
    createdAt:existing?.createdAt||now,updatedAt:now};
  DB.ref('/notes/'+nid).set(obj);
  closeM('m-todo');toast('✅ 已儲存');
}
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add japan-trip.html
git commit -m "feat: 待辦清單 modal — create, edit, inline checkbox toggle"
```

---

## Task 9 — Final Wiring + Smoke Test

**Files:** Modify `japan-trip.html`

- [ ] **Step 1: Verify `openNoteM` is called correctly from FAB**

`openNoteM('note')` → opens 記事 modal ✓  
`openNoteM('todo')` → calls `openTodoM()` ✓ (handled by `if(type!=='note')return openTodoM()`)

- [ ] **Step 2: Verify `goTab` handles missing `page-stat`**

After the restructure, `page-stat` no longer exists. Search for any remaining `goTab('stat')` calls:
```bash
grep -n "goTab.*stat\|page-stat\|t-stat" "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/japan-trip.html" | grep -v base64
```
If any remain, remove or replace them.

- [ ] **Step 3: Verify `renderStat` is called on sub-toggle switch only**

Check `renderStat` is NOT called in `_fbListen` at initial load while `statContent` is hidden (it's fine if called; just won't be visible). The `switchAcc('stat')` calls `renderStat(lastExps)` on demand.

Actually check: `_fbListen` currently calls `renderStat(lastExps)`. This still works because `pieSec` and `personSec` IDs exist inside `statContent`. Leave it as-is.

- [ ] **Step 4: Final commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add japan-trip.html
git commit -m "feat: complete notes+tabs redesign — wiring verified"
```

- [ ] **Step 5: Deploy to Netlify**

Drag updated `japan-trip.html` to Netlify or push via connected repo.

- [ ] **Step 6: Smoke test checklist**

- [ ] 行程 tab: activity note with URL → clickable link
- [ ] 行程 tab: add activity image → shows thumbnail → tap → lightbox opens
- [ ] 記帳 tab: sub-toggle switches between 支出清單 and 統計圖表
- [ ] 記帳 tab: FAB shows 手動輸入 / 掃描收據
- [ ] 記事本 tab: FAB shows 新增記事 / 新增待辦
- [ ] 記事本: create 記事 with title, content, image → appears in list
- [ ] 記事本: create 待辦清單 with items → checkboxes work inline
- [ ] 記事本: edit / delete both card types
