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


TESTS = {
    'selftest': test_selftest,
    'ro_state': test_ro_state,
    'blocks_writes': test_blocks_writes,
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
