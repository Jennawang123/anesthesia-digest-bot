#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""檢查一組 Firebase 設定是「真的靠匿名登入讀到資料」還是「規則開著誰都讀得到」。

trip 系列的每支 app（iceland / us / couple / family）在鎖安全性規則之前都該跑一次。
規則沒鎖的時候，貼錯 API Key、忘了啟用匿名登入，畫面上完全看不出來——照樣讀得到，
因為根本沒人檢查。等規則一鎖才發現打不開，那時已經很難聯想到原因。
這支腳本在「還沒鎖」的狀態下就先證明「鎖了之後仍讀得到」。

用法：
    python3 scripts/check_firebase_auth.py ~/us-trip-firebase.txt

憑證從家目錄的文字檔讀，不從命令列傳（歷史紀錄會留下）。檔案格式：
    url=https://xxx-default-rtdb.asia-southeast1.firebasedatabase.app
    apikey=AIza...

⚠️ 輸出含專案名稱與資料庫主機名，規則鎖上之前那等於通行證，別截圖貼出去。

四個檢查分別在問：
    1. 不帶任何憑證讀得到嗎        → 讀得到就代表規則對全世界開放
    2. 這把 key 換得到匿名帳號嗎    → key 有效嗎、匿名登入啟用了嗎
    3. key 的專案 == 資料庫的專案？ → 這才是「能不能共用 key」的答案
    4. 帶著憑證讀得到嗎            → 規則鎖上之後 app 走的正是這條路
"""
import base64, json, os, sys, urllib.request, urllib.error

def read_cfg(path):
    url = key = ''
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        print('✗ 找不到 %s' % path)
        print('  請建立這個檔案，兩行：')
        print('      url=https://xxx-default-rtdb.asia-southeast1.firebasedatabase.app')
        print('      apikey=AIza...')
        sys.exit(1)
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            k, v = line.split('=', 1)
            k = k.strip().lower().replace('_', '')
            if k in ('url', 'dburl', 'databaseurl'): url = v.strip()
            elif k in ('apikey', 'key'): key = v.strip()
        elif line.startswith('http'): url = line
        elif line.startswith('AIza'): key = line
    return url.rstrip('/'), key

def get(u):
    try:
        with urllib.request.urlopen(u, timeout=20) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)

def post(u, payload):
    req = urllib.request.Request(u, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}
    except Exception as e:
        return 0, {'error': {'message': str(e)}}

def jwt_claims(tok):
    p = tok.split('.')[1]
    p += '=' * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))

def main():
    if len(sys.argv) < 2:
        print('用法：python3 scripts/check_firebase_auth.py <設定檔路徑>')
        print('例：  python3 scripts/check_firebase_auth.py ~/us-trip-firebase.txt')
        sys.exit(1)
    path = sys.argv[1]
    url, key = read_cfg(path)
    if not url:
        print('✗ 檔案裡找不到資料庫網址'); sys.exit(1)
    host = url.split('//', 1)[-1].split('/')[0]
    db_project = host.split('.')[0].replace('-default-rtdb', '')
    print('資料庫  :', host)
    print('專案推測:', db_project)
    print('API Key :', ('已填，' + key[:6] + '…' + key[-4:]) if key else '（空的）')
    print('-' * 58)

    verdict = []

    # 1) 完全不帶憑證去讀 —— 讀得到就代表規則對全世界開放
    st, body = get(url + '/config.json')
    if st == 200 and body.strip() not in ('null', ''):
        print('1. 未登入直接讀 /config     → 200，讀得到資料')
        print('   ⚠️  規則目前對「任何人」開放，網址知道就能讀寫')
        rules_open = True
    elif st == 200:
        print('1. 未登入直接讀 /config     → 200，但是空的（資料庫還沒有資料）')
        rules_open = True
    elif st in (401, 403):
        print('1. 未登入直接讀 /config     → %d Permission denied ✅ 規則已鎖' % st)
        rules_open = False
    else:
        print('1. 未登入直接讀 /config     → %s %s' % (st, body[:120])); rules_open = None

    if not key:
        print('\n✗ 沒有填 API Key。app 的 ensureAuth() 會直接跳過登入，')
        print('  現在能用完全是因為規則開著——規則一鎖就全部讀不到。')
        sys.exit(2)

    # 2) 拿這把 key 去要一個匿名帳號 —— 驗證 key 有效且專案已啟用匿名登入
    st, d = post('https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=' + key,
                 {'returnSecureToken': True})
    if st != 200:
        msg = d.get('error', {}).get('message', str(d)[:120])
        print('2. 用 API Key 匿名登入      → 失敗：%s' % msg)
        # 三種失敗長得很像，但要做的事完全不同，別混在一起講
        if 'CONFIGURATION_NOT_FOUND' in msg:
            print('   → key 本身有效（無效的 key 會回 "API key not valid"，訊息不一樣），')
            print('     但這個專案從來沒開過 Authentication。')
            print('     Firebase Console → Authentication → 開始使用 → Sign-in method → 啟用「匿名」')
        elif 'ADMIN_ONLY_OPERATION' in msg:
            print('   → Authentication 開了，但「匿名」這個登入方式沒啟用。')
            print('     Firebase Console → Authentication → Sign-in method → 匿名 → 啟用')
        elif 'API key not valid' in msg:
            print('   → 這把 API Key 無效，八成是貼漏字元或複製到別的東西')
        sys.exit(3)
    tok = d['idToken']
    claims = jwt_claims(tok)
    tok_project = claims.get('aud') or claims.get('firebase', {}).get('tenant') or '?'
    print('2. 用 API Key 匿名登入      → 成功，uid=%s' % claims.get('user_id', '?')[:10] + '…')
    print('   這把 key 屬於專案       → %s' % tok_project)

    # 3) key 與資料庫是不是同一個專案 —— 這是「能不能共用 key」的真正答案
    same = tok_project == db_project
    print('3. key 與資料庫同一專案？   → %s' % ('✅ 是' if same else '✗ 不是！key=%s，資料庫=%s' % (tok_project, db_project)))
    if not same:
        verdict.append('API Key 與資料庫不屬於同一個 Firebase 專案。現在若還能用，純粹是規則開著；規則一鎖就會全部 permission denied。')

    # 4) 帶著登入憑證去讀 —— 規則鎖了之後 app 走的就是這條路
    st, body = get(url + '/config.json?auth=' + tok)
    if st == 200:
        print('4. 帶登入憑證讀 /config     → 200 ✅ 資料庫接受這個專案的憑證')
    else:
        print('4. 帶登入憑證讀 /config     → %d %s' % (st, body[:120]))
        verdict.append('帶著憑證仍讀不到，規則鎖起來之後 app 會打不開。')

    print('-' * 58)
    if verdict:
        print('結論：✗ 有問題')
        for v in verdict: print('  ·', v)
    elif rules_open:
        print('結論：✅ 設定正確，但規則還沒鎖（現在誰都讀得到）。')
        print('     可以安心去 Console 發布 auth != null 的規則了——')
        print('     上面第 4 步已經證明鎖上之後這台仍讀得到。')
    else:
        print('結論：✅ 規則已鎖，且匿名登入確實讀得到。這就是正確狀態。')

main()
