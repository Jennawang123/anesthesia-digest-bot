#!/usr/bin/env python3
"""四腿票掃描器：用 Google Flights 查四段行程總價。

用法：
    python3 scripts/fare_scan.py --once          # 只掃一組，驗證環境
    python3 scripts/fare_scan.py --phase1        # 掃 Phase 1 全部 864 組
    python3 scripts/fare_scan.py --phase3 --phase4  # 一次掃多個階段
    python3 scripts/fare_scan.py --detail 20     # 對最便宜前 20 組補時刻
    python3 scripts/fare_scan.py --refresh 50    # 每日重掃最便宜前 50 組

兩段式掃描（依據見 spec 的「完整四段資訊的取得成本」）：
    快掃 約 6 秒／組，只讀第一段列表，取整趟總價
    詳掃 約 48 秒／組，逐段點選補四段時刻與直飛狀態

各段選項的總價相同（同一 fare bucket），所以總價快掃就準確，
詳掃純粹是補時刻欄位。

結果存 ~/four-leg-fares.json，中斷可直接重跑接續。
"""

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fare_combos import (PHASE1, PHASE2, PHASE3, PHASE4, PHASE5,
                         PHASE6, generate)
from fare_store import (LocalStore, merge_detail, merge_refresh,
                        pick_detail_targets, push_firebase,
                        read_db_url)
from fx_rate import fetch_krw_twd, to_twd
from gf_parse import parse_row
from gf_url import build_url

PHASES = {"phase1": PHASE1, "phase2": PHASE2,
          "phase3": PHASE3, "phase4": PHASE4,
          "phase5": PHASE5, "phase6": PHASE6}

STORE_PATH = Path.home() / "four-leg-fares.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

# 列表載入的輪詢設定：每 2.5 秒檢查一次，最多等 60 秒
POLL_INTERVAL_MS = 2500
POLL_MAX_TRIES = 24

def _online(timeout=10):
    """打 Google 的 204 端點確認出得去。"""
    import urllib.request
    try:
        req = urllib.request.Request(
            "https://www.google.com/generate_204", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status in (200, 204)
    except Exception:
        return False


def wait_for_network(probe=_online, tries=15, interval=60, sleep=time.sleep):
    """等網路就緒，最多等 tries × interval。

    launchd 在 09:30 觸發時機器常是剛喚醒、Wi-Fi 還沒連上，直接開跑
    會整批 DNS 失敗——2026-08-20、08-21 兩天的每日重掃都是 50 組
    全滅，log 只留下 nodename nor servname provided。
    """
    for n in range(tries):
        if probe():
            return True
        if n < tries - 1:
            sleep(interval)
    return False


ROWS_JS = """() => [...document.querySelectorAll('li')]
    .map(e => (e.innerText || '').replace(/\\n+/g, ' | '))
    .filter(t => t.includes('整趟行程'))"""


async def read_rows(page):
    """等待並讀取含「整趟行程」的航班列。逾時回傳空清單。"""
    for _ in range(POLL_MAX_TRIES):
        await page.wait_for_timeout(POLL_INTERVAL_MS)
        rows = await page.evaluate(ROWS_JS)
        if rows:
            return rows
    return []


async def quick_scan(context, legs):
    """快掃一組行程，回傳結果 dict。"""
    page = await context.new_page()
    try:
        await page.goto(build_url(legs, currency="KRW", nonstop=True),
                        wait_until="domcontentloaded", timeout=60000)
        rows = await read_rows(page)
        if not rows:
            return {"status": "no_result"}

        parsed = [p for p in (parse_row(r) for r in rows) if p]
        if not parsed:
            return {"status": "no_result"}

        best = min(parsed, key=lambda p: p["price"])
        return {
            "status": "ok",
            "priceKRW": best["price"],
            "carrier": best["carrier"],
            "legs": [
                {"date": d, "from": o, "to": t,
                 **({"depart": best["depart"], "arrive": best["arrive"],
                     "arrivePlusDays": best["arrive_plus_days"],
                     "duration": best["duration"],
                     "nonstop": best["nonstop"], "via": best["via"]}
                    if i == 0 else {})}
                for i, (d, o, t) in enumerate(legs)
            ],
            "detail": "quick",
            "url": build_url(legs, currency="KRW", nonstop=True),
            # 查詢時已對四段下直飛旗標。實測 3/3 詳掃結果皆 allNonstop=True，
            # 故快掃結果雖看不到後三段，仍可據此視為全直飛。
            "nonstopQuery": True,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}
    finally:
        await page.close()


async def run_once():
    """掃一組已知有票的行程，驗證整條鏈路可用。

    這組是使用者 2026-08-18 實際查到的行程，長榮官網報價
    KRW 1,736,600，Google Flights 應報約 1,774,600（差約 2.2%）。
    """
    from playwright.async_api import async_playwright

    legs = [("2026-12-23", "PUS", "TPE"), ("2027-02-26", "TPE", "SEA"),
            ("2027-03-07", "SEA", "TPE"), ("2027-04-20", "TPE", "ICN")]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="zh-TW", user_agent=UA,
            viewport={"width": 1600, "height": 1400})
        result = await quick_scan(ctx, legs)
        await browser.close()

    print(f"status   : {result['status']}")
    if result["status"] == "ok":
        rate, at = fetch_krw_twd()
        twd = to_twd(result["priceKRW"], rate)
        print(f"價格     : ￦{result['priceKRW']:,}  ≈ NT${twd:,}")
        print(f"航空公司 : {result['carrier']}")
        leg1 = result["legs"][0]
        print(f"第一段   : {leg1['depart']}–{leg1['arrive']} "
              f"{'直達' if leg1['nonstop'] else '轉機 ' + str(leg1['via'])}")
        print(f"匯率     : {rate} ({at})")


# 連續這麼多組查無結果就中止：正常情況不可能整片沒票，
# 較可能是 tfs 格式失效或被速率限制。靜默記成「沒票」會讓
# 整批資料變成無聲的錯誤。
CONSECUTIVE_EMPTY_ABORT = 15

# 連續這麼多組查詢失敗也中止。error 會在續跑時重試，不像 no_result
# 那樣污染資料，但斷網後每組都要等 60 秒逾時，白跑幾百組。
# （2026-08-20 實際踩到：掃到一半斷網，209 組連續 ERR_INTERNET_DISCONNECTED
# 還一路跑了幾小時。）
CONSECUTIVE_ERROR_ABORT = 15


async def run_workers(todo, scan, handle, concurrency=2, delay=3.0,
                      empty_abort=CONSECUTIVE_EMPTY_ABORT,
                      error_abort=CONSECUTIVE_ERROR_ABORT,
                      progress_every=10, total=None):
    """並行跑掃描；連續查無結果達門檻即中止，已排隊的組合也一併放棄。

    中止旗標必須在「取得 semaphore 之後」再檢查一次：asyncio.gather
    會一口氣把所有 worker 排進 event loop，它們早在旗標被設起之前
    就通過了進入點的檢查，只擋進入點等於沒擋。
    （2026-08-20 實際踩到：連續 200 組空白仍繼續掃，全被寫成
    no_result，而 no_result 算「已完成」會讓續跑永久跳過。）

    連續查詢失敗（多半是斷網）同樣中止，理由見 CONSECUTIVE_ERROR_ABORT。

    scan(combo) 為 async callable，handle(combo, result) 負責落地。
    """
    sem = asyncio.Semaphore(concurrency)
    c = {"done": 0, "ok": 0, "empty_streak": 0, "error_streak": 0,
         "aborted": False, "skipped": 0}
    total = total if total is not None else len(todo)

    async def worker(combo):
        async with sem:
            if c["aborted"]:
                c["skipped"] += 1
                return
            result = await scan(combo)
            if delay:
                await asyncio.sleep(delay)

        status = result.get("status")
        if status == "ok":
            c["ok"] += 1
            c["empty_streak"] = 0
            c["error_streak"] = 0
        elif status == "no_result":
            c["empty_streak"] += 1
            c["error_streak"] = 0
        elif status == "error":
            c["error_streak"] += 1

        handle(combo, result)
        c["done"] += 1
        if progress_every and c["done"] % progress_every == 0:
            print(f"  {c['done']}/{total} 完成，{c['ok']} 組有票")

        if c["empty_streak"] >= empty_abort and not c["aborted"]:
            c["aborted"] = True
            print(f"\n!! 連續 {empty_abort} 組查無結果，中止。\n"
                  f"   可能是 tfs 格式失效或被速率限制，"
                  f"請先用 --once 確認鏈路是否還通。")
        elif c["error_streak"] >= error_abort and not c["aborted"]:
            c["aborted"] = True
            last = str(result.get("error", ""))[:80]
            print(f"\n!! 連續 {error_abort} 組查詢失敗，中止。\n"
                  f"   最後一則錯誤：{last}\n"
                  f"   多半是網路斷線；連線恢復後直接重跑即可續掃。")

    await asyncio.gather(*(worker(x) for x in todo))
    return c


async def scan_batch(combos, store, db_url, rate, fx_at,
                     delay=3.0, concurrency=2):
    """批次快掃。已有結果的跳過，每筆立即落地。"""
    from playwright.async_api import async_playwright

    todo = [c for c in combos if not store.has(c["id"])]
    print(f"待掃 {len(todo)} / 共 {len(combos)} 組"
          f"（已完成 {len(combos) - len(todo)}）")
    if not todo:
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="zh-TW", user_agent=UA,
            viewport={"width": 1600, "height": 1400})

        def handle(combo, result):
            if result["status"] == "ok":
                result["priceTWD"] = to_twd(result["priceKRW"], rate)
                result["fxRate"] = rate
                result["fxAt"] = fx_at
            result["scannedAt"] = datetime.now(timezone.utc).isoformat()
            store.put(combo["id"], result)
            if db_url and result["status"] == "ok":
                try:
                    push_firebase(db_url, combo["id"], result)
                except Exception as e:
                    print(f"  Firebase 寫入失敗：{str(e)[:80]}")

        counters = await run_workers(
            todo, lambda c: quick_scan(ctx, c["legs"]), handle,
            concurrency=concurrency, delay=delay, total=len(todo))
        await browser.close()

    print(f"\n完成 {counters['done']} 組，{counters['ok']} 組有票")
    if counters["aborted"]:
        print(f"（因連續查無結果中止，{counters['skipped']} 組未掃）")


async def detail_scan(context, legs):
    """逐段點選，補齊四段時刻與直飛狀態。約 48 秒／組。

    每段都選總價最低者。實測各選項總價相同，所以此處選擇不影響
    總價，只影響取得的時刻。
    """
    page = await context.new_page()
    try:
        await page.goto(build_url(legs, currency="KRW", nonstop=True),
                        wait_until="domcontentloaded", timeout=60000)
        collected = []
        for seg in range(len(legs)):
            rows = await read_rows(page)
            if not rows:
                return {"status": "no_result"}
            parsed = [(p, i) for i, p in
                      ((i, parse_row(r)) for i, r in enumerate(rows)) if p]
            if not parsed:
                return {"status": "no_result"}
            best, idx = min(parsed, key=lambda x: x[0]["price"])
            collected.append(best)
            if seg == len(legs) - 1:
                break
            items = page.locator("li").filter(has_text="整趟行程")
            await items.nth(idx).click()
            await page.wait_for_timeout(3000)

        return {
            "status": "ok",
            "priceKRW": collected[0]["price"],
            "carrier": collected[0]["carrier"],
            "legs": [
                {"date": d, "from": o, "to": t,
                 "depart": c["depart"], "arrive": c["arrive"],
                 "arrivePlusDays": c["arrive_plus_days"],
                 "duration": c["duration"],
                 "nonstop": c["nonstop"], "via": c["via"]}
                for (d, o, t), c in zip(legs, collected)
            ],
            "allNonstop": all(c["nonstop"] for c in collected),
            "detail": "full",
            "url": build_url(legs, currency="KRW", nonstop=True),
            # 查詢時已對四段下直飛旗標。實測 3/3 詳掃結果皆 allNonstop=True，
            # 故快掃結果雖看不到後三段，仍可據此視為全直飛。
            "nonstopQuery": True,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}
    finally:
        await page.close()


async def run_detail(top_n, store, db_url, rate, fx_at, delay=3.0):
    """對最便宜的前 N 組執行詳掃。"""
    from playwright.async_api import async_playwright

    targets = pick_detail_targets(store.all_ok(), top_n)
    print(f"最便宜前 {top_n} 組中，{len(targets)} 組尚未詳掃")
    if not targets:
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="zh-TW", user_agent=UA,
            viewport={"width": 1600, "height": 1400})
        for n, (cid, rec) in enumerate(targets, 1):
            legs = [(l["date"], l["from"], l["to"]) for l in rec["legs"]]
            result = await detail_scan(ctx, legs)
            if result["status"] == "ok":
                result["priceTWD"] = to_twd(result["priceKRW"], rate)
                result["fxRate"] = rate
                result["fxAt"] = fx_at
                result["scannedAt"] = datetime.now(timezone.utc).isoformat()
                # 詳掃只負責補時刻，排序用的快掃價與 history 都保留
                merged = merge_detail(store.get(cid), result)
                store.put(cid, merged)
                if db_url:
                    try:
                        push_firebase(db_url, cid, merged)
                    except Exception as e:
                        print(f"  Firebase 寫入失敗：{str(e)[:80]}")
                mark = "全直飛" if result["allNonstop"] else "含轉機"
                print(f"  [{n}/{len(targets)}] ￦{result['priceKRW']:,} {mark}")
            else:
                # 記下失敗次數，屢次打不開的組下次不再擋住後面的
                rec = dict(store.get(cid) or {})
                rec["detailFails"] = rec.get("detailFails", 0) + 1
                store.put(cid, rec)
                print(f"  [{n}/{len(targets)}] {result['status']}"
                      f"（第 {rec['detailFails']} 次失敗）")
            await asyncio.sleep(delay)
        await browser.close()


async def run_refresh(top_n, store, db_url, rate, fx_at,
                      delay=3.0, concurrency=2):
    """重掃最便宜的前 N 組，累積價格歷史。供每日排程使用。"""
    from playwright.async_api import async_playwright

    ok = store.all_ok()
    targets = sorted(ok.items(), key=lambda kv: kv[1]["priceKRW"])[:top_n]
    print(f"重掃最便宜的 {len(targets)} 組")
    if not targets:
        print("尚無資料可重掃，請先執行 --phase1 / --phase2")
        return

    stats = {"up": 0, "down": 0, "same": 0}
    todo = [{"id": cid, "legs": rec["legs"], "priceKRW": rec["priceKRW"]}
            for cid, rec in targets]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="zh-TW", user_agent=UA,
            viewport={"width": 1600, "height": 1400})

        async def scan(combo):
            legs = [(l["date"], l["from"], l["to"]) for l in combo["legs"]]
            return await quick_scan(ctx, legs)

        def handle(combo, result):
            if result["status"] == "ok":
                result["priceTWD"] = to_twd(result["priceKRW"], rate)
                result["fxRate"] = rate
                result["fxAt"] = fx_at
                diff = result["priceKRW"] - combo["priceKRW"]
                stats["up" if diff > 0 else "down" if diff < 0 else "same"] += 1
            result["scannedAt"] = datetime.now(timezone.utc).isoformat()
            # 快掃只有第一段時刻，直接覆蓋會洗掉詳掃結果，故先合併
            merged = merge_refresh(store.get(combo["id"]), result)
            store.put_with_history(combo["id"], merged)
            if db_url and merged["status"] == "ok":
                try:
                    push_firebase(db_url, combo["id"], store.get(combo["id"]))
                except Exception as e:
                    print(f"  Firebase 寫入失敗：{str(e)[:80]}")

        counters = await run_workers(todo, scan, handle,
                                     concurrency=concurrency, delay=delay,
                                     progress_every=0)
        await browser.close()

    fail = counters["done"] - counters["ok"]
    print(f"完成 {counters['done']} 組：漲 {stats['up']}、跌 {stats['down']}、"
          f"平 {stats['same']}、失敗 {fail}")
    if counters["aborted"]:
        print(f"（連續失敗中止，{counters['skipped']} 組未重掃）")


def main():
    ap = argparse.ArgumentParser(description="四腿票掃描器")
    ap.add_argument("--once", action="store_true", help="只掃一組驗證環境")
    ap.add_argument("--phase1", action="store_true",
                    help="掃 Phase 1：韓國進出 × VIE/MXP，864 組")
    ap.add_argument("--phase2", action="store_true",
                    help="掃 Phase 2：韓國進出 × LAX/SFO，864 組")
    ap.add_argument("--phase3", action="store_true",
                    help="掃 Phase 3：泰國 BKK 進出 × 五個長程點，540 組")
    ap.add_argument("--phase4", action="store_true",
                    help="掃 Phase 4：韓國進出 × AMS，432 組")
    ap.add_argument("--phase5", action="store_true",
                    help="掃 Phase 5：韓國進出 × YVR/MUC，864 組")
    ap.add_argument("--phase6", action="store_true",
                    help="掃 Phase 6：泰國 BKK 進出 × YVR/MUC，216 組")
    ap.add_argument("--delay", type=float, default=3.0, help="每組間隔秒數")
    ap.add_argument("--concurrency", type=int, default=2, help="並行數")
    ap.add_argument("--detail", type=int, metavar="N",
                    help="對最便宜的前 N 組補四段時刻")
    ap.add_argument("--refresh", type=int, metavar="N",
                    help="重掃最便宜的前 N 組並累積價格歷史（供每日排程）")
    args = ap.parse_args()

    if args.once:
        asyncio.run(run_once())
        return

    if args.refresh:
        if not wait_for_network():
            print("網路持續不通，這次重掃略過。")
            return
        store = LocalStore(STORE_PATH)
        db_url = read_db_url()
        try:
            rate, fx_at = fetch_krw_twd()
        except Exception as e:
            rate, fx_at = None, ""
            print(f"匯率取得失敗，台幣欄位留空：{str(e)[:80]}")
        asyncio.run(run_refresh(args.refresh, store, db_url, rate, fx_at,
                                delay=args.delay, concurrency=args.concurrency))
        return

    if args.detail:
        store = LocalStore(STORE_PATH)
        db_url = read_db_url()
        try:
            rate, fx_at = fetch_krw_twd()
        except Exception:
            rate, fx_at = None, ""
        asyncio.run(run_detail(args.detail, store, db_url, rate, fx_at,
                               delay=args.delay))
        return

    picked = [k for k in PHASES if getattr(args, k)]
    if picked:
        if not wait_for_network():
            print("網路持續不通，中止。")
            return
        # 可一次指定多個階段，例如 --phase3 --phase4 連續掃完
        combos = [c for k in picked for c in generate(PHASES[k])]
        store = LocalStore(STORE_PATH)
        db_url = read_db_url()
        print(f"結果檔：{STORE_PATH}")
        print(f"Firebase：{'已設定' if db_url else '未設定（僅本機儲存）'}")
        try:
            rate, fx_at = fetch_krw_twd()
            print(f"匯率：KRW→TWD {rate}（{fx_at}）")
        except Exception as e:
            rate, fx_at = None, ""
            print(f"匯率取得失敗，台幣欄位留空：{str(e)[:80]}")
        asyncio.run(scan_batch(combos, store, db_url, rate, fx_at,
                               delay=args.delay, concurrency=args.concurrency))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
