#!/usr/bin/env python3
"""四腿票掃描器：用 Google Flights 查四段行程總價。

用法：
    python3 scripts/fare_scan.py --once          # 只掃一組，驗證環境
    python3 scripts/fare_scan.py --phase1        # 掃 Phase 1 全部 864 組
    python3 scripts/fare_scan.py --detail 20     # 對最便宜前 20 組補時刻

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
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fare_combos import PHASE1, generate
from fare_store import LocalStore, push_firebase, read_db_url
from fx_rate import fetch_krw_twd, to_twd
from gf_parse import parse_row
from gf_url import build_url

STORE_PATH = Path.home() / "four-leg-fares.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

# 列表載入的輪詢設定：每 2.5 秒檢查一次，最多等 60 秒
POLL_INTERVAL_MS = 2500
POLL_MAX_TRIES = 24

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
        await page.goto(build_url(legs, currency="KRW"),
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


async def scan_batch(combos, store, db_url, rate, fx_at,
                     delay=3.0, concurrency=2):
    """批次快掃。已有結果的跳過，每筆立即落地。"""
    from playwright.async_api import async_playwright

    todo = [c for c in combos if not store.has(c["id"])]
    print(f"待掃 {len(todo)} / 共 {len(combos)} 組"
          f"（已完成 {len(combos) - len(todo)}）")
    if not todo:
        return

    sem = asyncio.Semaphore(concurrency)
    counters = {"done": 0, "ok": 0, "empty_streak": 0, "aborted": False}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="zh-TW", user_agent=UA,
            viewport={"width": 1600, "height": 1400})

        async def worker(combo):
            if counters["aborted"]:
                return
            async with sem:
                result = await quick_scan(ctx, combo["legs"])
                await asyncio.sleep(delay)

            if result["status"] == "ok":
                result["priceTWD"] = to_twd(result["priceKRW"], rate)
                result["fxRate"] = rate
                result["fxAt"] = fx_at
                counters["ok"] += 1
                counters["empty_streak"] = 0
            elif result["status"] == "no_result":
                counters["empty_streak"] += 1

            result["scannedAt"] = datetime.now(timezone.utc).isoformat()
            store.put(combo["id"], result)
            if db_url and result["status"] == "ok":
                try:
                    push_firebase(db_url, combo["id"], result)
                except Exception as e:
                    print(f"  Firebase 寫入失敗：{str(e)[:80]}")

            counters["done"] += 1
            if counters["done"] % 10 == 0:
                print(f"  {counters['done']}/{len(todo)} 完成，"
                      f"{counters['ok']} 組有票")

            if counters["empty_streak"] >= CONSECUTIVE_EMPTY_ABORT:
                counters["aborted"] = True
                print(f"\n!! 連續 {CONSECUTIVE_EMPTY_ABORT} 組查無結果，中止。\n"
                      f"   可能是 tfs 格式失效或被速率限制，"
                      f"請先用 --once 確認鏈路是否還通。")

        await asyncio.gather(*(worker(c) for c in todo))
        await browser.close()

    print(f"\n完成 {counters['done']} 組，{counters['ok']} 組有票")


def main():
    ap = argparse.ArgumentParser(description="四腿票掃描器")
    ap.add_argument("--once", action="store_true", help="只掃一組驗證環境")
    ap.add_argument("--phase1", action="store_true",
                    help="掃 Phase 1：韓國進出 × VIE/MXP，864 組")
    ap.add_argument("--delay", type=float, default=3.0, help="每組間隔秒數")
    ap.add_argument("--concurrency", type=int, default=2, help="並行數")
    args = ap.parse_args()

    if args.once:
        asyncio.run(run_once())
        return

    if args.phase1:
        combos = generate(PHASE1)
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
