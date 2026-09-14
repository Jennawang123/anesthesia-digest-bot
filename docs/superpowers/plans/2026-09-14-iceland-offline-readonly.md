# 冰島版離線唯讀 + Service Worker + 寫死連線資訊 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 `iceland-trip.html` 在完全沒網路時打得開、沒真正連上資料庫時一律唯讀，並在 iOS 清掉網站資料後有網路即可自動恢復連線。

**Architecture:** 單檔 HTML app 內新增一組「連線狀態 → body.ro → roBlock() 守門」機制，所有寫入入口呼叫 `roBlock()`；新增獨立的 `iceland-sw.js`（部署時名為 `sw.js`）負責主頁 network-first（3 秒逾時）、函式庫 cache-first、圖磚 cache-first 上限 3000；`window.onload` 改用 `deviceCfg()` 在本機沒設定時套寫死的網址與 apiKey。

**Tech Stack:** 純前端 HTML/JS（Firebase RTDB compat SDK 9.23.0、Leaflet 1.9.4）、Service Worker Cache API、Python Playwright 1.58（端對端測試）。

**Spec:** `docs/superpowers/specs/2026-09-14-iceland-offline-readonly-design.md`

---

## 動手前必讀（這個 repo 的規矩）

1. **這支檔案可能被使用者在另一個視窗同時修改。** 每個 Task 開始前先跑 `git status --short iceland-trip.html` 與 `git log --oneline -1 -- iceland-trip.html`；不要沿用先前查到的行號，一律用 Edit 工具的字串錨點（`old_string` 必須唯一，不唯一時 Edit 會失敗——那就是檔案被改過的訊號，停下來重新 Read 該段）。
2. **不可連線到真實的冰島資料庫。** 測試一律用 `scripts/test_iceland_offline.py`，它在 localStorage 預塞一個不存在的 Firebase 網址，apiKey 留空。不要在瀏覽器裡用真實網址開 app 測試——連上後背景的 `ensureActGeo`/`ensureLegs` 等會寫入真實資料。
3. **`window.scrollTo` 在這支 app 無效**（真正捲動的是 `.content`），本計畫不需要捲動，但別加。
4. **新增顯示文字的 CSS 字級要寫 `calc(Npx*var(--fs))`。**
5. **commit 後直接 push**；push 被拒時 `git pull --rebase --autostash` 再 push。**只 add 本計畫動到的檔案**，工作區裡 `CLAUDE.md`、`travel-atlas*.html`、`.gitignore` 有使用者未 commit 的變動，不可一起 commit。
6. commit 訊息結尾加：
   ```
   Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01QJ82qV5PuyuFZp1pHn5FMC
   ```
7. macOS 沒有 `python`，一律 `python3`。

## 檔案結構

| 檔案 | 動作 | 責任 |
|---|---|---|
| `iceland-trip.html` | 修改 | 連線狀態與唯讀守門、橫幅、認證離線處理、SW 註冊、寫死連線資訊、版本號 `v0914a` |
| `iceland-sw.js` | 新增 | Service Worker（部署時複製成 `sw.js`） |
| `scripts/test_iceland_offline.py` | 新增 | Playwright 端對端測試（本機 http server + 假資料，不連真實 DB） |
| `netlify-iceland/index.html`、`netlify-iceland/sw.js` | 新增（不進 git） | 部署資料夾，使用者整包拖到 Netlify |
| `.gitignore` | 修改 | 加 `netlify-iceland/`（只 stage 這一行） |

---

### Task 1: 測試腳手架

**Files:**
- Create: `scripts/test_iceland_offline.py`

- [ ] **Step 1: 建立測試腳本**

```python
#!/usr/bin/env python3
"""冰島版離線唯讀／Service Worker 端對端測試。

不連真實資料庫：localStorage 預先塞一個不存在的 Firebase 網址，apiKey 留空。
每次執行都把 iceland-trip.html 複製成暫存目錄的 index.html（iceland-sw.js 存在時複製成 sw.js），
用本機 http server 提供，因為 Service Worker 只在 http(s)/localhost 上運作，playwright 也擋 file:。

用法：
  python3 scripts/test_iceland_offline.py            # 全部
  python3 scripts/test_iceland_offline.py selftest   # 只跑指定測試
"""
import http.server
import json
import shutil
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PORT = 8765
BASE = f'http://localhost:{PORT}/'
FAKE_URL = 'https://offline-test-00000-default-rtdb.asia-southeast1.firebasedatabase.app'
SNAP = {'at': '2026-09-14T15:30:00.000Z', 'data': {
    'config': {'title': '測試旅程', 'members': ['A', 'B'], 'start': '2026-09-14', 'days': 2, 'tz': ''},
    'schedule': {
        'day1': {'label': 'Day 1', 'date': '2026-09-14',
                 'acts': {'a1': {'name': '藍湖溫泉', 'cat': 'sight', 'order': 0}}},
        'day2': {'label': 'Day 2', 'date': '2026-09-15', 'acts': {}},
    },
    'expenses': {'e1': {'desc': '午餐', 'amt': 3000, 'cur': 'ISK', 'cat': 'food',
                        'paidBy': 'A', 'date': '2026-09-14'}},
    'notes': {'n1': {'type': 'todo', 'title': '行李', 'order': 0,
                     'items': [{'text': '護照', 'done': False}]}},
}}

RESULTS = []


def check(name, cond, extra=''):
    RESULTS.append(bool(cond))
    print(f"{'✅' if cond else '❌'} {name}" + (f'  → {extra}' if extra and not cond else ''))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def build_site():
    d = Path(tempfile.mkdtemp(prefix='iceland-site-'))
    shutil.copy(ROOT / 'iceland-trip.html', d / 'index.html')
    if (ROOT / 'iceland-sw.js').exists():
        shutil.copy(ROOT / 'iceland-sw.js', d / 'sw.js')
    return d


def serve(d):
    handler = lambda *a, **k: Quiet(*a, directory=str(d), **k)
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(('localhost', PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def new_page(browser, api_key='', seed=True):
    """開一個全新的 context（等於一台全新的手機）。seed=False 表示 localStorage 全空。"""
    ctx = browser.new_context()
    if seed:
        dev = json.dumps({'url': FAKE_URL, 'apiKey': api_key})
        ctx.add_init_script(
            "if(!localStorage.getItem('iceland_trip')){"
            f"localStorage.setItem('iceland_trip',{json.dumps(dev)});"
            f"localStorage.setItem('iceland_trip_snap',{json.dumps(json.dumps(SNAP))});}}"
        )
    page = ctx.new_page()
    page.dialogs = []
    page.on('dialog', lambda dlg: (page.dialogs.append(dlg.message), dlg.dismiss()))
    page.goto(BASE)
    return ctx, page


# ───────────────────────── tests ─────────────────────────

def test_selftest(browser):
    ctx, page = new_page(browser)
    page.wait_for_selector('#app', state='visible')
    check('既有 _selftest() 全數通過', page.evaluate('_selftest()') is True)
    ctx.close()


TESTS = {
    'selftest': test_selftest,
}


def main():
    names = sys.argv[1:] or list(TESTS)
    srv = serve(build_site())
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for n in names:
                print(f'\n── {n}')
                TESTS[n](browser)
            browser.close()
    finally:
        srv.shutdown()
    passed = sum(RESULTS)
    print(f'\n通過 {passed} / 失敗 {len(RESULTS) - passed}')
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 跑 baseline**

Run: `python3 scripts/test_iceland_offline.py selftest`
Expected: `✅ 既有 _selftest() 全數通過`、`通過 1 / 失敗 0`。
若 `_selftest()` 回 false：先在 playwright 裡 `page.on('console', print)` 看是哪一條失敗，**那是既有問題，不是本計畫造成的**——記下失敗項目名稱，之後每個 Task 的判準改成「失敗項目不增加」。

- [ ] **Step 3: Commit**

```bash
git add scripts/test_iceland_offline.py
git commit -m "test(iceland): 離線唯讀端對端測試腳手架"
git push
```

---

### Task 2: 唯讀狀態核心（狀態、樣式、橫幅、helper）

**Files:**
- Modify: `iceland-trip.html`（CSS 區 `.dot.off`、HTML `.hdr` 之後、JS `sync()` 之後、`bootApp()`、`_selftest()` 結尾）
- Modify: `scripts/test_iceland_offline.py`

- [ ] **Step 1: 寫失敗的測試**

在 `scripts/test_iceland_offline.py` 的 `TESTS = {` 之前加：

```python
def test_ro_state(browser):
    ctx, page = new_page(browser)
    page.wait_for_selector('#app', state='visible')
    check('開 app 立即是唯讀（body.ro）', page.evaluate("document.body.classList.contains('ro')"))
    check('頭 4 秒內不顯示離線橫幅',
          not page.evaluate("document.getElementById('ro-banner').classList.contains('show')"))
    page.wait_for_timeout(4500)
    check('4 秒後仍未連上 → 顯示橫幅',
          page.evaluate("document.getElementById('ro-banner').classList.contains('show')"))
    check('橫幅帶快照時間',
          '離線唯讀' in page.evaluate("document.getElementById('ro-banner').textContent"))
    page.evaluate('setFbOnline(true)')
    check('連上後 ro 移除', not page.evaluate("document.body.classList.contains('ro')"))
    check('連上後橫幅隱藏',
          not page.evaluate("document.getElementById('ro-banner').classList.contains('show')"))
    page.evaluate('setFbOnline(false)')
    check('寬限期過後斷線 → 立即顯示橫幅',
          page.evaluate("document.getElementById('ro-banner').classList.contains('show')"))
    check('淡化編輯鈕：FAB opacity 0.4',
          page.evaluate("getComputedStyle(document.getElementById('fab')).opacity") == '0.4')
    ctx.close()
```

並在 `TESTS` 加一行 `'ro_state': test_ro_state,`

- [ ] **Step 2: 確認失敗**

Run: `python3 scripts/test_iceland_offline.py ro_state`
Expected: FAIL（`document.getElementById('ro-banner')` 為 null → evaluate 拋錯）

- [ ] **Step 3: 加 CSS**

用 Edit，old_string：
```
.dot.off{background:#9A8F89;}
```
new_string：
```
.dot.off{background:#9A8F89;}
/* 離線唯讀：沒真正連上資料庫時，編輯類控制項變淡（仍可點，點了會跳提示說明原因） */
body.ro :is(.fab,.ib,.day-eb,.act-handle,.note-handle,.todo-item input[type=checkbox],[onclick^="save"]:not([onclick^="saveApiKey"]),[onclick^="doCopyAct"],[onclick^="fixDates"],[onclick^="refreshOfflineData"],[onclick^="clearAll"],[onclick^="addTodoItem"]){opacity:.4;}
#ro-banner{display:none;background:#FEF3C7;color:#78350F;border-bottom:1px solid #F59E0B;padding:8px 16px;text-align:center;font-size:calc(15px*var(--fs));font-weight:600;}
#ro-banner.show{display:block;}
```

- [ ] **Step 4: 加橫幅節點**

先確認錨點唯一：`grep -c '<div class="content">' iceland-trip.html` 應為 1。
用 Edit，old_string：
```
  <div class="content">
```
new_string：
```
  <div id="ro-banner"></div>
  <div class="content">
```

- [ ] **Step 5: 加狀態與 helper**

用 Edit，old_string：
```
function openM(id){document.getElementById(id).classList.add('open');}
```
new_string：
```
// ─── 離線唯讀 ───────────────────────────────────────
// 「有網路」不等於「連得上資料庫」：訊號一格時 navigator.onLine 照樣是 true，
// 這時寫入只會排在 SDK 的記憶體佇列，關掉 app 就不見。所以以資料庫真正連上為準，沒連上一律唯讀。
let _fbOnline=false;
// 開 app 的頭 4 秒還在連線，不要馬上喊「離線」；超過 4 秒仍沒連上才出橫幅（按鈕從一開始就是淡的）
let _roGrace=true;
function setFbOnline(v){
  _fbOnline=!!v;
  document.body.classList.toggle('ro',!_fbOnline);
  if(_fbOnline){_roGrace=false;showRoBanner(false);sync('ok');}
  else if(!_roGrace){showRoBanner(true);sync('offline');}
}
function startRoGrace(){
  document.body.classList.add('ro');
  setTimeout(()=>{_roGrace=false;if(!_fbOnline){showRoBanner(true);sync('offline');}},4000);
}
function showRoBanner(on){
  const b=document.getElementById('ro-banner');if(!b)return;
  if(on){
    const s=snapLoad();
    const t=s?new Date(s.at).toLocaleString('zh-TW',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'';
    b.textContent=t?`📴 離線唯讀 · ${t} 的資料`:'📴 離線唯讀';
  }
  b.classList.toggle('show',on);
}
// 所有寫入入口的守門：沒連上就跳提示並回 true（呼叫端 return）
function roBlock(){
  if(_fbOnline)return false;
  toast('📴 離線唯讀中，連上網路才能修改');
  return true;
}
function openM(id){document.getElementById(id).classList.add('open');}
```

- [ ] **Step 6: bootApp 啟動寬限期、offline 事件同步狀態**

用 Edit，old_string：
```
function bootApp(){
  document.getElementById('setup').style.display='none';
```
new_string：
```
function bootApp(){
  startRoGrace();
  document.getElementById('setup').style.display='none';
```

用 Edit，old_string：
```
  window.addEventListener('offline',()=>sync('offline'));
```
new_string：
```
  window.addEventListener('offline',()=>{sync('offline');setFbOnline(false);});
```

- [ ] **Step 7: _selftest 補唯讀狀態檢查**

用 Edit，old_string：
```
  console.log(out.join('\n')+`\n\n通過 ${pass} / 失敗 ${fail}`);
```
new_string：
```
  // ---- 離線唯讀 ----
  {
    const was=_fbOnline,grace=_roGrace;
    _roGrace=false;
    setFbOnline(false);
    ok('沒連上時 body 有 ro', document.body.classList.contains('ro'));
    ok('沒連上時 roBlock 回 true', roBlock()===true);
    ok('寬限期過後斷線立即顯示橫幅', document.getElementById('ro-banner').classList.contains('show'));
    setFbOnline(true);
    ok('連上後 ro 移除', !document.body.classList.contains('ro'));
    ok('連上後 roBlock 回 false', roBlock()===false);
    ok('連上後橫幅隱藏', !document.getElementById('ro-banner').classList.contains('show'));
    setFbOnline(was);_roGrace=grace;
  }

  console.log(out.join('\n')+`\n\n通過 ${pass} / 失敗 ${fail}`);
```

- [ ] **Step 8: 跑測試**

Run: `python3 scripts/test_iceland_offline.py selftest ro_state`
Expected: 全部 ✅，`失敗 0`

- [ ] **Step 9: Commit**

```bash
git add iceland-trip.html scripts/test_iceland_offline.py
git commit -m "feat(iceland): 離線唯讀狀態、淡化編輯鈕與離線橫幅"
git push
```

---

### Task 3: 使用者寫入入口加守門

**Files:**
- Modify: `iceland-trip.html`
- Modify: `scripts/test_iceland_offline.py`

- [ ] **Step 1: 寫失敗的測試**

在 `TESTS = {` 之前加：

```python
def test_blocks_writes(browser):
    ctx, page = new_page(browser)
    page.wait_for_selector('#app', state='visible')
    r = page.evaluate("""()=>{
      window._w=0;
      const w={set(){_w++;return Promise.resolve()},update(){_w++;return Promise.resolve()},
               remove(){_w++;return Promise.resolve()},once(){_w++},on(){},
               get(){_w++;return Promise.resolve({val:()=>null})}};
      DB={ref:()=>w};            // 裸賦值才蓋得到頂層 let DB
      setFbOnline(false);
      const out={};
      fabTap();
      out.fabModal=!!document.querySelector('.ov.open');
      out.toast=document.getElementById('toast').textContent;
      document.getElementById('e_desc').value='測試';document.getElementById('e_amt').value='100';
      saveExp(); delExp('e1'); toggleTodoItem('n1',0,true); delNote('n1'); saveCfg(); clearAll();
      moveAct('day1','a1',{name:'x'},'day2'); saveAct(); saveDayM(); saveNote(); saveTodo(); doCopyAct();
      openActM('day1'); openActEdit('day1','a1'); openCopyAct('day1','a1'); openDayM('day1');
      openExpM(); openExpEdit('e1'); openNoteM('note'); openNoteEdit('n1'); openTodoM(); openTodoEdit('n1');
      out.writes=_w;
      out.modal=!!document.querySelector('.ov.open');
      setFbOnline(true);
      document.getElementById('e_desc').value='測試';document.getElementById('e_amt').value='100';
      saveExp();
      out.writesOnline=_w;
      return out;}""")
    check('唯讀時按 ＋ 不開表單', not r['fabModal'])
    check('唯讀時跳提示', '離線唯讀' in r['toast'], r['toast'])
    check('唯讀時所有儲存／刪除／開編輯都沒有碰資料庫', r['writes'] == 0, r['writes'])
    check('唯讀時沒有任何表單被打開', not r['modal'])
    check('唯讀時刪除不跳確認視窗（守門在 confirm 之前）', page.dialogs == [], page.dialogs)
    check('連上後 saveExp 正常寫入', r['writesOnline'] > 0, r['writesOnline'])
    ctx.close()
```

`TESTS` 加 `'blocks_writes': test_blocks_writes,`

- [ ] **Step 2: 確認失敗**

Run: `python3 scripts/test_iceland_offline.py blocks_writes`
Expected: FAIL（`writes` > 0、表單被打開、有 confirm dialog）

- [ ] **Step 3: 在函式開頭加 `if(roBlock())return;`**

以下每一項各用一次 Edit。old_string 是函式宣告那一行（含結尾換行），new_string 是同一行後面加一行 `  if(roBlock())return;`。例：

old_string：
```
function fabTap(){
```
new_string：
```
function fabTap(){
  if(roBlock())return;
```

逐一套用在這些宣告行（每行都已確認在檔案中唯一出現）：
```
function fabTap(){
function openDayM(did){
function saveDayM(){
function openActM(did){
function openActEdit(did,aid){
function saveAct(){
function delAct(did,aid){
function openCopyAct(did,aid){
function doCopyAct(){
function moveAct(fromDid,aid,act,toDid){
function openExpM(){
function openExpEdit(eid){
function saveExp(){
function saveCfg(){
function delNote(nid){
function openTodoM(){
function openTodoEdit(nid){
function saveTodo(){
function openNoteM(type){
function openNoteEdit(nid){
function saveNote(){
```

- [ ] **Step 4: 單行函式與特例**

Edit，old_string：
```
function delExp(eid){if(!confirm('確定刪除？'))return;
```
new_string：
```
function delExp(eid){if(roBlock())return;if(!confirm('確定刪除？'))return;
```

Edit，old_string：
```
function clearAll(){if(!confirm('⚠️ 確定清空所有資料？'))return;
```
new_string：
```
function clearAll(){if(roBlock())return;if(!confirm('⚠️ 確定清空所有資料？'))return;
```

勾選框在 onchange 時畫面已經打勾了，擋下後要重畫還原。Edit，old_string：
```
function toggleTodoItem(nid,idx,done){
```
new_string：
```
function toggleTodoItem(nid,idx,done){
  if(roBlock()){renderNotes(lastNotes);return;}
```

「立即更新」原本只看 `navigator.onLine`。Edit，old_string：
```
  if(!navigator.onLine){toast('⚠️ 目前離線，請連上網路再更新');return;}
```
new_string：
```
  if(roBlock())return;
```

「重新套用行程日期」按鈕呼叫 `fixDates(true)`，背景補正呼叫 `fixDates(false)`：使用者按的要提示、背景的靜默。Edit，old_string：
```
function fixDates(showToast=false){
```
new_string：
```
function fixDates(showToast=false){
  if(!_fbOnline){if(showToast)roBlock();return Promise.resolve();}
```

- [ ] **Step 5: 拖曳起點與放下時的寫入**

行程列觸控拖曳，Edit，old_string：
```
    if(!row||!e.target.closest('.act-handle'))return;
```
new_string：
```
    if(!row||!e.target.closest('.act-handle'))return;
    if(roBlock())return;
```

行程列桌面拖曳，Edit，old_string：
```
    if(_actDragFromHandle)return; // 交給 initActDnD 處理
```
new_string：
```
    if(_actDragFromHandle)return; // 交給 initActDnD 處理
    if(roBlock()){e.preventDefault();return;}
```

把手桌面拖曳，Edit，old_string：
```
    if(!_actDragFromHandle)return;
    const row=e.target.closest('.act-row');
```
new_string：
```
    if(!_actDragFromHandle)return;
    if(roBlock()){e.preventDefault();return;}
    const row=e.target.closest('.act-row');
```

記事觸控拖曳，Edit，old_string：
```
    if(!card||!e.target.closest('.note-handle'))return;   // 只認把手，捲動記事本才不會誤觸
```
new_string：
```
    if(!card||!e.target.closest('.note-handle'))return;   // 只認把手，捲動記事本才不會誤觸
    if(roBlock())return;
```

拖到一半斷線的放下寫入（三處）。Edit，old_string：
```
    aids.forEach((a,i)=>upd['/schedule/'+tgt+'/acts/'+a+'/order']=i);
    DB.ref('/').update(upd);
```
new_string：
```
    aids.forEach((a,i)=>upd['/schedule/'+tgt+'/acts/'+a+'/order']=i);
    if(roBlock())return;
    DB.ref('/').update(upd);
```

Edit，old_string：
```
    const upd={};ids.forEach((id,i)=>upd['/notes/'+id+'/order']=i);
    DB.ref('/').update(upd);
```
new_string：
```
    const upd={};ids.forEach((id,i)=>upd['/notes/'+id+'/order']=i);
    if(roBlock())return;
    DB.ref('/').update(upd);
```

Edit，old_string：
```
    DB.ref('/').update(updates);
    ADG.on=false;
```
new_string：
```
    if(roBlock()){ADG.on=false;return;}
    DB.ref('/').update(updates);
    ADG.on=false;
```

- [ ] **Step 6: 跑測試**

Run: `python3 scripts/test_iceland_offline.py selftest ro_state blocks_writes`
Expected: 全部 ✅
若「連上後 saveExp 正常寫入」失敗：Read `saveExp` 看它是否需要其他表單欄位（如 `curCat`），在測試裡補設定，**不要**改 `saveExp` 本身。

- [ ] **Step 7: Commit**

```bash
git add iceland-trip.html scripts/test_iceland_offline.py
git commit -m "feat(iceland): 所有使用者寫入入口在離線時擋下並提示"
git push
```

---

### Task 4: 背景寫入守門、連線偵測、認證離線處理

**Files:**
- Modify: `iceland-trip.html`
- Modify: `scripts/test_iceland_offline.py`

- [ ] **Step 1: 寫失敗的測試**

在 `TESTS = {` 之前加：

```python
def test_background_silent(browser):
    ctx, page = new_page(browser)
    page.wait_for_selector('#app', state='visible')
    r = page.evaluate("""async()=>{
      window._w=0;
      const w={set(){_w++;return Promise.resolve()},update(){_w++;return Promise.resolve()},
               remove(){_w++;return Promise.resolve()},once(){},on(){},
               get(){return Promise.resolve({val:()=>null})}};
      DB={ref:()=>w};
      setFbOnline(false);
      document.getElementById('toast').textContent='';
      await ensureActGeo(lastSched,true); await ensureFacilities(lastSched,true);
      await ensureSafety(lastSched,true); await ensureLegs(lastSched,true);
      await fixDates(false); createFullSchedule();
      return {writes:_w,toast:document.getElementById('toast').textContent};}""")
    check('離線時背景補資料不寫入', r['writes'] == 0, r['writes'])
    check('背景跳過不跳提示', r['toast'] == '', r['toast'])
    ctx.close()
```

`TESTS` 加 `'background_silent': test_background_silent,`

- [ ] **Step 2: 確認失敗**

Run: `python3 scripts/test_iceland_offline.py background_silent`
Expected: FAIL（`createFullSchedule()` 會寫入；`ensureActGeo` 會嘗試寫入）

- [ ] **Step 3: 背景函式守門**

Edit，old_string：
```
async function ensureActGeo(sched,force=false){
  if(_geoScanning)return;
```
new_string：
```
async function ensureActGeo(sched,force=false){
  if(_geoScanning||!_fbOnline)return;
```

Edit，old_string：
```
async function pruneDayOutliers(did,resolved){
  if(resolved.length<3)return;
```
new_string：
```
async function pruneDayOutliers(did,resolved){
  if(resolved.length<3||!_fbOnline)return;
```

Edit，old_string：
```
  if(_facScanning||!navigator.onLine||!DB)return;
```
new_string：
```
  if(_facScanning||!_fbOnline||!DB)return;
```

Edit，old_string：
```
  if(_legScanning||!navigator.onLine)return;
```
new_string：
```
  if(_legScanning||!_fbOnline)return;
```

Edit，old_string：
```
  if(_safetyScanning||!navigator.onLine)return;
```
new_string：
```
  if(_safetyScanning||!_fbOnline)return;
```

Edit，old_string：
```
function createFullSchedule(){
```
new_string：
```
function createFullSchedule(){
  if(!_fbOnline)return;
```

- [ ] **Step 4: `_fbListen` 掛連線偵測**

Edit，old_string：
```
function _fbListen(){
  DB.ref('/').on('value',snap=>{
    const d=snap.val()||{};
```
new_string：
```
function _fbListen(){
  // 資料庫真正連上／斷線的唯一可靠訊號；navigator.onLine 在訊號一格時照樣回 true
  DB.ref('.info/connected').on('value',s=>setFbOnline(s.val()===true));
  DB.ref('/').on('value',snap=>{
    // 收到伺服器資料就代表此刻連得上（web SDK 沒有磁碟快取，value 不會來自本機）。
    // .info/connected 與第一包資料的先後不保證，不補這行的話背景補資料可能整輪被跳過。
    if(!_fbOnline)setFbOnline(true);
    const d=snap.val()||{};
```

Edit，old_string：
```
    if(navigator.onLine){
      ensureActGeo(sched)
```
new_string：
```
    if(_fbOnline){
      ensureActGeo(sched)
```

Edit，old_string：
```
  },err=>{sync(navigator.onLine?'ok':'offline');toast('⚠️ Firebase 錯誤：'+err.message);});
```
new_string：
```
  },err=>{sync(_fbOnline?'ok':'offline');toast('⚠️ Firebase 錯誤：'+err.message);});
```

- [ ] **Step 5: 認證等 SDK 還原登入狀態，離線失敗不跳錯**

Edit，old_string：
```
function ensureAuth(){
  if(!CFG.apiKey)return Promise.resolve(null);
  const u=firebase.auth().currentUser;
  return u?Promise.resolve(u):firebase.auth().signInAnonymously();
}
function authFail(e){
  sync(false);
```
new_string：
```
// SDK 剛初始化時 currentUser 還沒從 IndexedDB 還原；直接判斷的話離線會走到 signInAnonymously 而失敗
function authReady(){return new Promise(res=>{const un=firebase.auth().onAuthStateChanged(u=>{un();res(u);});});}
function ensureAuth(){
  if(!CFG.apiKey)return Promise.resolve(null);
  return authReady().then(u=>u||firebase.auth().signInAnonymously());
}
function authFail(e){
  // 離線造成的登入失敗不是設定錯誤：維持唯讀，網路回來再連一次
  if(!navigator.onLine||e?.code==='auth/network-request-failed'){
    sync('offline');
    window.addEventListener('online',()=>connectFB(),{once:true});
    return;
  }
  sync(false);
```

- [ ] **Step 6: SDK 載入失敗且有快照時不蓋錯誤橫幅**

Edit，old_string：
```
    s1.onerror=()=>{
      sync(false);
      document.getElementById('fb-retry-banner').style.display='';
    };
```
new_string：
```
    s1.onerror=()=>{
      // 有快照時離線照樣看得到東西，唯讀橫幅已說明狀況，錯誤橫幅只會蓋住畫面；網路回來自動重試
      if(snapLoad()){sync('offline');window.addEventListener('online',()=>window._fbRetryLoad(),{once:true});return;}
      sync(false);
      document.getElementById('fb-retry-banner').style.display='';
    };
```

- [ ] **Step 7: 跑測試**

Run: `python3 scripts/test_iceland_offline.py selftest ro_state blocks_writes background_silent`
Expected: 全部 ✅

- [ ] **Step 8: Commit**

```bash
git add iceland-trip.html scripts/test_iceland_offline.py
git commit -m "feat(iceland): 以 .info/connected 判斷連線、背景寫入離線靜默跳過、離線登入不跳錯"
git push
```

---

### Task 5: Service Worker

**Files:**
- Create: `iceland-sw.js`
- Modify: `iceland-trip.html`（`window.onload` 註冊、`loadLeaflet`、地圖 `okL`、`tileLayer`）
- Modify: `scripts/test_iceland_offline.py`

- [ ] **Step 1: 寫失敗的測試**

在 `TESTS = {` 之前加：

```python
def wait_sw(page):
    page.evaluate("navigator.serviceWorker.ready.then(()=>true)")
    # 第一次安裝後頁面還沒被 SW 接管，重載一次讓 clients.claim 生效後的導覽走 SW
    page.reload()
    page.wait_for_selector('#app', state='visible')


def test_sw_offline(browser):
    ctx, page = new_page(browser)
    page.wait_for_selector('#app', state='visible')
    wait_sw(page)
    n_lib = page.evaluate("caches.open('lib-v0914a').then(c=>c.keys()).then(k=>k.length)")
    check('安裝時預抓 5 支函式庫', n_lib >= 5, n_lib)
    tile = 'https://tile.openstreetmap.org/5/15/9.png'
    page.evaluate(f"fetch('{tile}',{{mode:'cors'}}).then(r=>r.ok)")

    ctx.set_offline(True)
    page.reload()
    page.wait_for_selector('#app', state='visible')
    check('完全離線重開：頁面打得開、標題來自快照',
          page.evaluate("document.getElementById('appTitle').textContent") == '測試旅程')
    check('完全離線重開：行程由快照渲染', '藍湖溫泉' in page.content())
    check('完全離線重開：唯讀', page.evaluate("document.body.classList.contains('ro')"))
    page.wait_for_timeout(4500)
    check('完全離線重開：4 秒後出現離線橫幅',
          page.evaluate("document.getElementById('ro-banner').classList.contains('show')"))
    check('完全離線重開：Firebase 錯誤橫幅沒出現',
          page.evaluate("document.getElementById('fb-err-banner').style.display") == 'none')
    check('完全離線重開：SDK 載入失敗橫幅沒出現',
          page.evaluate("document.getElementById('fb-retry-banner').style.display") == 'none')
    check('完全離線重開：Firebase SDK 從快取載入', page.evaluate("typeof firebase") == 'object')
    check('完全離線重開：Leaflet 從快取載入', page.evaluate("loadLeaflet()") is True)
    check('完全離線：看過的圖磚從快取取得',
          page.evaluate(f"fetch('{tile}',{{mode:'cors'}}).then(r=>r.ok,()=>false)") is True)
    ctx.close()


def test_auth_offline(browser):
    ctx, page = new_page(browser, api_key='AIzaOfflineTestFakeKey000000000000000')
    page.wait_for_selector('#app', state='visible')
    wait_sw(page)
    ctx.set_offline(True)
    page.reload()
    page.wait_for_selector('#app', state='visible')
    page.wait_for_timeout(5000)
    check('有 apiKey 時離線重開：不跳匿名登入失敗',
          page.evaluate("document.getElementById('fb-err-banner').style.display") == 'none')
    check('有 apiKey 時離線重開：維持唯讀', page.evaluate("document.body.classList.contains('ro')"))
    ctx.close()
```

`TESTS` 加 `'sw_offline': test_sw_offline,` 與 `'auth_offline': test_auth_offline,`

- [ ] **Step 2: 確認失敗**

Run: `python3 scripts/test_iceland_offline.py sw_offline`
Expected: FAIL（`navigator.serviceWorker.ready` 永遠不會 resolve → playwright 逾時；或離線重開頁面空白）

- [ ] **Step 3: 建立 `iceland-sw.js`**

```js
// 冰島版 Service Worker：讓 app 在完全沒網路時打得開。
// 資料本身靠主頁的 localStorage 快照（iceland_trip_snap），這裡只負責「網頁與函式庫載得進來」。
// 部署時複製成網站根目錄的 sw.js。
const VERSION='v0914a';
const SHELL='shell-'+VERSION, LIB='lib-'+VERSION, TILES='tiles';
const LIB_URLS=[
  'https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js',
  'https://www.gstatic.com/firebasejs/9.23.0/firebase-database-compat.js',
  'https://www.gstatic.com/firebasejs/9.23.0/firebase-auth-compat.js',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
];
const NAV_TIMEOUT_MS=3000;   // 訊號微弱時請求不會失敗、只會一直轉；超過就改用快取
const TILE_MAX=3000;         // 只存看過的圖磚（OSM 政策禁止批次預抓），超過刪最早存的

self.addEventListener('install',e=>{
  e.waitUntil((async()=>{
    const lib=await caches.open(LIB);
    await lib.addAll(LIB_URLS.map(u=>new Request(u,{mode:'cors'})));
    // 主頁也先存一份，之後第一次離線開啟就有東西可用
    try{
      const r=await fetch('/',{cache:'no-store'});
      if(r.ok)await (await caches.open(SHELL)).put('/',r);
    }catch(_){}
    await self.skipWaiting();
  })());
});

self.addEventListener('activate',e=>{
  e.waitUntil((async()=>{
    const keep=[SHELL,LIB,TILES];
    for(const k of await caches.keys())if(!keep.includes(k))await caches.delete(k);
    await self.clients.claim();
  })());
});

self.addEventListener('fetch',e=>{
  const req=e.request;
  if(req.method!=='GET')return;
  const url=new URL(req.url);
  if(req.mode==='navigate'&&url.origin===self.location.origin){e.respondWith(navFetch(e));return;}
  if(LIB_URLS.includes(req.url)){e.respondWith(cacheFirst(LIB,req));return;}
  if(url.hostname==='fonts.googleapis.com'||url.hostname==='fonts.gstatic.com'){e.respondWith(cacheFirst(LIB,req));return;}
  if(url.hostname==='tile.openstreetmap.org'){e.respondWith(tileFetch(req));return;}
  // 其餘（Firebase 連線與認證、Nominatim、OSRM、Overpass、Open-Meteo、匯率）不攔截：即時資料不該被快取
});

async function navFetch(e){
  const cache=await caches.open(SHELL);
  // 逾時後網路請求仍繼續跑，拿到新版就寫回快取，下次開就是新的
  const net=fetch(e.request).then(r=>{if(r.ok)cache.put('/',r.clone());return r;});
  e.waitUntil(net.catch(()=>{}));
  try{
    return await Promise.race([net,new Promise((_,rej)=>setTimeout(()=>rej(new Error('timeout')),NAV_TIMEOUT_MS))]);
  }catch(_){
    const hit=await cache.match('/');
    return hit||new Response('請先在有網路時開啟一次',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8'}});
  }
}

async function cacheFirst(name,req){
  const c=await caches.open(name);
  const hit=await c.match(req);
  if(hit)return hit;
  const r=await fetch(req);
  if(r.ok||r.type==='opaque')c.put(req,r.clone());
  return r;
}

async function tileFetch(req){
  const c=await caches.open(TILES);
  const hit=await c.match(req);
  if(hit)return hit;
  const r=await fetch(req);
  // 只存 CORS 回應（tileLayer 設了 crossOrigin）；opaque 回應在瀏覽器配額裡會被灌水，3000 張會爆
  if(r.ok){await c.put(req,r.clone());trimTiles(c);}
  return r;
}

let _trimming=false;
async function trimTiles(c){
  if(_trimming)return;
  _trimming=true;
  try{
    const keys=await c.keys();   // 依寫入順序
    for(let i=0;i<keys.length-TILE_MAX;i++)await c.delete(keys[i]);
  }finally{_trimming=false;}
}
```

- [ ] **Step 4: 主頁註冊 SW**

Edit，old_string：
```
window.onload=()=>{
  const s=localStorage.getItem('iceland_trip');
```
new_string：
```
window.onload=()=>{
  // 讓 app 在完全沒網路時打得開；不支援或註冊失敗都不影響其他功能
  if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
  const s=localStorage.getItem('iceland_trip');
```

- [ ] **Step 5: 地圖離線時也嘗試載入（SW 快取會提供）**

Edit，old_string：
```
    s.onerror=()=>res(false);   // CDN 掛掉就走降級路徑，不讓整頁卡住
```
new_string：
```
    s.onerror=()=>{_leafletLoading=null;res(false);};   // CDN 掛掉就走降級路徑；清掉快取的失敗結果，網路回來才能重試
```

Edit，old_string：
```
  const okL=navigator.onLine?await loadLeaflet():false;
```
new_string：
```
  const okL=await loadLeaflet();   // 離線時由 Service Worker 快取提供；真的沒有才走降級
```

Edit，old_string：
```
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap'}).addTo(map);
```
new_string：
```
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap',crossOrigin:'anonymous'}).addTo(map);
```

- [ ] **Step 6: 跑測試**

Run: `python3 scripts/test_iceland_offline.py selftest ro_state blocks_writes background_silent sw_offline auth_offline`
Expected: 全部 ✅

若 `auth_offline` 的「不跳匿名登入失敗」失敗：在測試裡加 `page.on('console', lambda m: print(m.text))`，看 `signInAnonymously` 的錯誤碼。若不是 `auth/network-request-failed`，把該錯誤碼加進 `authFail()` 的離線判斷條件（只加網路類錯誤碼，不可把 `auth/api-key-not-valid` 之類的設定錯誤也吞掉）。

- [ ] **Step 7: Commit**

```bash
git add iceland-sw.js iceland-trip.html scripts/test_iceland_offline.py
git commit -m "feat(iceland): Service Worker 讓 app 完全離線打得開、看過的地圖圖磚留存"
git push
```

---

### Task 6: 寫死連線資訊

**Files:**
- Modify: `iceland-trip.html`（`TRIP_KEYS` 附近、`window.onload`、`_selftest`）
- Modify: `scripts/test_iceland_offline.py`

- [ ] **Step 1: 寫失敗的測試**

在 `TESTS = {` 之前加：

```python
def test_default_cfg(browser):
    ctx, page = new_page(browser, seed=False)
    page.wait_for_timeout(1500)
    r = page.evaluate("""()=>({
      setupHidden: document.getElementById('setup').style.display==='none',
      appShown: document.getElementById('app').style.display==='flex',
      url: CFG.url, key: CFG.apiKey, def: typeof DEF_FB_URL==='string' ? DEF_FB_URL : null })""")
    # 失敗訊息不可印出 r：裡面有真實網址與 apiKey
    check('localStorage 全空時不停在 Setup 畫面', r['setupHidden'] and r['appShown'])
    check('localStorage 全空時使用寫死的網址', r['def'] and r['url'] == r['def'])
    check('寫死的網址是冰島專案', 'iceland-2026-f13e6' in (r['url'] or ''))
    check('寫死的 apiKey 有值', (r['key'] or '').startswith('AIza'))
    ctx.close()
```

`TESTS` 加 `'default_cfg': test_default_cfg,`

⚠️ 這個測試**會用真實網址與 key 開 app**。為了不連到真實資料庫，本測試開頭改成先擋掉 Firebase SDK（SDK 載不進來就不會連線）。把 `ctx, page = new_page(browser, seed=False)` 那行換成：

```python
    ctx = browser.new_context(service_workers='block')
    ctx.route('https://www.gstatic.com/firebasejs/**', lambda route: route.abort())
    page = ctx.new_page()
    page.goto(BASE)
```

- [ ] **Step 2: 確認失敗**

Run: `python3 scripts/test_iceland_offline.py default_cfg`
Expected: FAIL（停在 Setup 畫面，`DEF_FB_URL` 不存在）

- [ ] **Step 3: 加預設值與 `deviceCfg()`**

Edit，old_string：
```
const TRIP_KEYS=['title','members','start','days','photo','city','cityQuery','lat','lng','tz'];
```
new_string：
```
const TRIP_KEYS=['title','members','start','days','photo','city','cityQuery','lat','lng','tz'];
// 寫死的連線資訊：iOS 清掉網站資料後，有網路就能自動恢復，不必重新輸入（爸媽不會記得網址和金鑰）。
// Firebase Web API Key 本來就會出現在前端，保護靠 Security Rules（2026-09-10 已鎖 auth != null）。
const DEF_FB_URL='__DEF_FB_URL__', DEF_FB_KEY='__DEF_FB_KEY__';
// 本機有值優先用本機（維持既有裝置行為），沒有才用寫死的
function deviceCfg(dev){dev=dev||{};return {...dev,url:dev.url||DEF_FB_URL,apiKey:dev.apiKey||DEF_FB_KEY};}
```

- [ ] **Step 4: 從憑證檔填入真實值（不經對話傳遞）**

```bash
python3 - <<'PY'
from pathlib import Path
cfg = {}
for line in (Path.home() / 'iceland-firebase.txt').read_text().splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        cfg[k.strip()] = v.strip()
url, key = cfg['url'].rstrip('/'), cfg['apikey']
assert url.startswith('https://') and 'iceland-2026-f13e6' in url, 'url 不對'
assert key.startswith('AIza'), 'apikey 不對'
p = Path('iceland-trip.html')
s = p.read_text()
for ph, val in (('__DEF_FB_URL__', url), ('__DEF_FB_KEY__', key)):
    assert s.count(ph) == 1, ph
    s = s.replace(ph, val)
p.write_text(s)
print('ok')
PY
```
Expected: `ok`。不要把值印出來。

- [ ] **Step 5: `window.onload` 改用 `deviceCfg()`**

Edit，old_string：
```
  const s=localStorage.getItem('iceland_trip');
  if(!s)return;
  const dev=JSON.parse(s);
  CFG={...dev};
```
new_string：
```
  let dev={};
  try{dev=JSON.parse(localStorage.getItem('iceland_trip')||'{}')||{};}catch(_){}
  CFG=deviceCfg(dev);
```

- [ ] **Step 6: _selftest 補 deviceCfg 檢查**

Edit，old_string：
```
  // ---- 離線唯讀 ----
```
new_string：
```
  // ---- 寫死連線資訊 ----
  {
    ok('本機沒設定時用寫死的網址', deviceCfg({}).url===DEF_FB_URL);
    ok('本機有網址時優先用本機', deviceCfg({url:'https://x.firebasedatabase.app'}).url==='https://x.firebasedatabase.app');
    ok('apiKey 空字串視為沒設定', deviceCfg({url:'u',apiKey:''}).apiKey===DEF_FB_KEY);
    ok('其他裝置設定（字級）保留', deviceCfg({fs:'l'}).fs==='l');
    ok('null 也不會炸', deviceCfg(null).url===DEF_FB_URL);
  }

  // ---- 離線唯讀 ----
```

- [ ] **Step 7: 跑全部測試**

Run: `python3 scripts/test_iceland_offline.py`
Expected: 全部 ✅，`失敗 0`

- [ ] **Step 8: Commit**

先確認 diff 裡的網址與 key 就是預期的兩個常數、沒有其他憑證：
```bash
git diff iceland-trip.html | grep -n "firebasedatabase.app\|AIza"
```
Expected: 只有 `const DEF_FB_URL=...` 那一行（含網址與 key）。

```bash
git add iceland-trip.html scripts/test_iceland_offline.py
git commit -m "feat(iceland): 寫死 Firebase 網址與 apiKey，本機資料被清掉時自動恢復連線"
git push
```

---

### Task 7: 版本號、部署資料夾、收尾

**Files:**
- Modify: `iceland-trip.html`（版本號）
- Modify: `.gitignore`（只 stage 一行）
- Create: `netlify-iceland/index.html`、`netlify-iceland/sw.js`（不進 git）

- [ ] **Step 1: 版本號**

Edit，old_string：
```
<span style="font-size:12px;opacity:.5">v0908a</span>
```
new_string：
```
<span style="font-size:12px;opacity:.5">v0914a</span>
```

- [ ] **Step 2: 全部測試**

Run: `python3 scripts/test_iceland_offline.py`
Expected: 全部 ✅，`失敗 0`

- [ ] **Step 3: 建立部署資料夾**

```bash
mkdir -p netlify-iceland
cp iceland-trip.html netlify-iceland/index.html
cp iceland-sw.js netlify-iceland/sw.js
cmp iceland-trip.html netlify-iceland/index.html && cmp iceland-sw.js netlify-iceland/sw.js && ls -la netlify-iceland
```
Expected: 兩個 cmp 無輸出、列出 `index.html` 與 `sw.js`

- [ ] **Step 4: `.gitignore` 只加一行、只 stage 這一行**

工作區的 `.gitignore` 有使用者未 commit 的變動，不可整檔 add。

```bash
grep -qx 'netlify-iceland/' .gitignore || echo 'netlify-iceland/' >> .gitignore
git show HEAD:.gitignore > "$TMPDIR/gi_head" && echo 'netlify-iceland/' >> "$TMPDIR/gi_head"
git update-index --cacheinfo 100644,$(git hash-object -w "$TMPDIR/gi_head"),.gitignore
git diff --cached .gitignore
```
Expected: staged diff 只有 `+netlify-iceland/` 一行；`git status --short netlify-iceland` 無輸出（已被忽略）

- [ ] **Step 5: Commit**

```bash
git add iceland-trip.html
git commit -m "chore(iceland): v0914a，部署資料夾 netlify-iceland 加入 gitignore"
git push
```

- [ ] **Step 6: 更新 memory**

在 `/Users/wangyingyu/.claude/projects/-Users-wangyingyu-Library-Mobile-Documents-com-apple-CloudDocs-Jenna-agent/memory/project_family_trip.md` 結尾新增一節（Edit 追加，不整檔重寫），重點：
- 2026-09-14 冰島版 `v0914a`：離線唯讀（`_fbOnline`／`roBlock()`／`body.ro`，以 `.info/connected` 與收到伺服器資料為準）、Service Worker（`iceland-sw.js` → 部署為 `sw.js`）、寫死 `DEF_FB_URL`/`DEF_FB_KEY`（`deviceCfg()` 本機優先）。
- **部署方式從此改為拖 `netlify-iceland/` 資料夾**（index.html + sw.js），不再拖單一 HTML；線上網址是根目錄 `/`（`/iceland-trip.html` 是 404）。每次改完要同步複製進去。
- 新增寫入入口時必須加 `if(roBlock())return;`；背景寫入用 `if(!_fbOnline)return;`。`saveApiKey`/`changeFB` 刻意不擋。
- 測試：`python3 scripts/test_iceland_offline.py`（不連真實 DB）。
- 部署狀態：⏳ 待使用者拖拉部署，四台手機各需「有網路開一次 → 關掉重開 → 飛航模式驗證」。
- 仍待使用者做：Google Cloud Console 為 apiKey 加 HTTP 參照網址限制。

同時更新 `MEMORY.md` 裡家庭旅遊 app 那行的冰島線上版本描述（Edit 最小替換）。

- [ ] **Step 7: 交付使用者部署說明**

告訴使用者：
1. 把 `Jenna_agent/netlify-iceland` **整個資料夾**拖到 Netlify 的 wang-iceland-2026 → Deploys。
2. 四台手機各做：有網路開 app 確認標題列 `v0914a` → 從背景滑掉重開一次 → 開飛航模式、滑掉重開 → 看得到行程＋「📴 離線唯讀」橫幅、按 ＋ 跳提示 → 關飛航模式，橫幅消失、可編輯。
3. Google Cloud Console → API 和服務 → 憑證 → 這把 key → 應用程式限制選「HTTP 參照網址」→ 加 `https://wang-iceland-2026.netlify.app/*`。
