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
    # apiKey 留空時 app 會補上寫死的真實 key：擋掉 Firebase 登入端點，避免在真實專案建立匿名帳號
    for pat in ('https://identitytoolkit.googleapis.com/**', 'https://securetoken.googleapis.com/**'):
        ctx.route(pat, lambda route: route.abort())
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


def test_default_cfg(browser):
    # 會用真實網址與 key 開 app：擋掉 Service Worker 與 Firebase SDK，SDK 載不進來就不會連線
    ctx = browser.new_context(service_workers='block')
    ctx.route('https://www.gstatic.com/firebasejs/**', lambda route: route.abort())
    page = ctx.new_page()
    page.goto(BASE)
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


TESTS = {
    'selftest': test_selftest,
    'ro_state': test_ro_state,
    'blocks_writes': test_blocks_writes,
    'background_silent': test_background_silent,
    'sw_offline': test_sw_offline,
    'auth_offline': test_auth_offline,
    'default_cfg': test_default_cfg,
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
