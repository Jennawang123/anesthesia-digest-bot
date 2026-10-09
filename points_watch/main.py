"""點數促銷監測主流程。

用法：
    python3 -m points_watch.main --bootstrap   # 首次：只把現有文章記為已看過，不判讀不推播
    python3 -m points_watch.main --dry-run     # 驗收：照常判讀，訊息印到 stdout，不推播不寫檔
    python3 -m points_watch.main               # 日常執行

同一次執行會先跑買點促銷，再跑國泰世華小樹點轉點加碼（cub_run），最後才是每週心跳。
"""
import argparse
import traceback
from datetime import date
from pathlib import Path

from society_watch import fetch
from society_watch import state as sw_state
from society_watch.notify import split_message

from . import alerts, cub_run, extract, feeds, notify, rating, store
from .line import push_line
from .models import Article, Rated
from .sources import DEFAULT_PAGES, FEEDS, feed_urls, is_candidate

DATA_DIR = Path(__file__).resolve().parent


def _reason(error: Exception) -> str:
    return alerts.reason(
        error, plain=(feeds.FeedError, extract.ExtractError, rating.SuspiciousPrice))


def collect(pages: int) -> tuple[list[Article], list[tuple[str, str]]]:
    """逐 feed 抓取解析。單一 feed 失敗不影響其他 feed。同一篇文章只留一份。"""
    articles: dict[str, Article] = {}
    failures: list[tuple[str, str]] = []
    for feed in FEEDS:
        name = feed["name"]
        try:
            found: list[Article] = []
            for url in feed_urls(feed, pages):
                found.extend(feeds.parse_feed(fetch.get(url), name))
        except Exception as e:
            print(f"  ❌ {name} 抓取失敗：{type(e).__name__}: {e}")
            traceback.print_exc()
            failures.append((name, _reason(e)))
            continue
        if not found:
            print(f"  ⚠️ {name} RSS 回傳 0 篇")
            failures.append((name, "RSS 回傳 0 篇，疑似改版"))
            continue
        print(f"  ✅ {name} {len(found)} 篇")
        for a in found:
            articles.setdefault(a.key, a)
    return list(articles.values()), failures


def _run_buy(bootstrap: bool, dry_run: bool, pages: int,
             today: date) -> tuple[list[tuple[str, str]], dict | None]:
    """買點／買哩程這條線。回傳（失敗清單, 心跳用的統計）；
    bootstrap 與 dry-run 不產生統計，回 None。"""
    seen_path = DATA_DIR / "seen_articles.json"
    promos_path = DATA_DIR / "promos.json"
    baselines_path = DATA_DIR / "baselines.json"
    alerts_path = DATA_DIR / "alert_state.json"

    mode = "bootstrap" if bootstrap else "dry-run" if dry_run else "日常"
    print(f"執行日期：{today}｜模式：{mode}｜每 feed {pages} 頁")

    articles, failures = collect(pages)
    candidates = [a for a in articles if is_candidate(a.title, a.summary)]
    seen = sw_state.load_seen(seen_path)
    print(f"抓到 {len(articles)} 篇，通過關鍵字 {len(candidates)} 篇")

    if bootstrap:
        sw_state.save_seen(seen_path, seen | {a.key for a in candidates})
        print("bootstrap 模式：只記錄已看過的文章，不判讀不推播。")
        return failures, None

    # dry-run 無視 seen，才看得到現有文章會產生什麼訊息
    fresh = candidates if dry_run else [a for a in candidates if a.key not in seen]

    baselines = rating.load_baselines(baselines_path)
    promos = store.load_promos(promos_path)
    judged: set[str] = set()       # 判讀完成（含判否）的文章鍵
    rated: dict[str, Rated] = {}   # 本輪新出現的促銷

    for article in fresh:
        print(f"  判讀：[{article.feed}] {article.title}")
        try:
            promo = extract.extract(article, today)
            if promo is None:
                print("    → 不是買點促銷")
            elif promo.key in promos or store.covered(
                    {**promos, **{k: store.entry(v, today) for k, v in rated.items()}},
                    promo, today):
                print(f"    → 已知促銷 {promo.key}")
            else:
                r = rating.rate(promo, baselines[promo.program])
                rated[promo.key] = r
                print(f"    → {promo.key} {r.cpp:.2f}¢ {r.grade}")
        except Exception as e:
            # 這篇不進 judged → 不記為已看過 → 明天重試
            print(f"    ❌ {type(e).__name__}: {e}")
            traceback.print_exc()
            failures.append((f"{article.feed}／抽取", _reason(e)))
            continue
        judged.add(article.key)

    to_push = [r for r in rated.values() if r.grade in ("green", "yellow")]

    if dry_run:
        print("\n===== dry-run：以下是會推播的內容 =====")
        print(notify.format_promos(to_push) if to_push else "（沒有 🟢／🟡 促銷）")
        if failures:
            print("\n" + notify.format_alert(failures))
        return failures, None

    # 告警先送：之後的推播若拋例外，當天的異常才不會跟著消失
    sent = alerts.send_due(failures, alerts_path, today, push_line)
    if sent:
        print(f"已送出 {sent} 則告警。")

    if to_push:
        for part in split_message(notify.format_promos(to_push)):
            push_line(part)
        print(f"已推播 {len(to_push)} 筆促銷。")
    else:
        print("沒有新的 🟢／🟡 促銷，不推播。")

    # 推播成功才推進狀態。push_line 失敗會拋例外穿出去，這段到不了，
    # 下一輪整批重來——重複優於漏報。
    # 基準排在 promos 之前寫：反過來的話，兩者之間被中斷會留下「促銷已知
    # 但新低沒寫進基準」，下一輪不再評等，那次新低就永遠不會進基準。
    lows: dict[str, float] = {}
    for r in rated.values():
        # 「最高可達」的新低只通知（訊息照標 🏆）、不改基準：限定對象的低價
        # 一旦寫進基準，之後一般人拿得到的促銷就會從 🟢 掉到 🟡。
        if r.new_low and not r.promo.up_to:
            lows[r.promo.program] = min(r.cpp, lows.get(r.promo.program, r.cpp))
    if lows:
        text = baselines_path.read_text(encoding="utf-8")
        for program, cpp in lows.items():
            text = rating.update_best(text, program, cpp)
        sw_state._atomic_write(baselines_path, text)
    for key, r in rated.items():
        promos[key] = store.entry(r, today)
    if rated:
        store.save_promos(promos_path, promos)
    sw_state.save_seen(seen_path, seen | judged)

    # 本輪才第一次推出的促銷不在同一輪再提醒一次（💰 裡已寫截止日）；
    # 它仍未標記 reminded，明天還在期限內就會提醒。
    due_keys = [k for k in store.due_reminders(promos, today) if k not in rated]
    if due_keys:
        push_line(notify.format_reminder([promos[k] for k in due_keys], today))
        for k in due_keys:
            promos[k]["reminded"] = True
        store.save_promos(promos_path, promos)
        print(f"已送出 {len(due_keys)} 筆截止提醒。")

    return failures, {"articles": len(seen | judged), "promos": len(promos)}


def _run_cub(dry_run: bool, today: date) -> tuple[list[tuple[str, str]], dict]:
    """跑國泰世華那條線。它的任何例外都在這裡接住：買點流程已經推播、
    狀態也寫完了，不能被這邊拖下水。"""
    try:
        return cub_run.run(DATA_DIR, today, dry_run, push_line)
    except Exception as e:
        print(f"  ❌ 國泰世華流程中斷：{type(e).__name__}: {e}")
        traceback.print_exc()
        failure = ("國泰世華／流程", alerts.reason(e))
        if not dry_run:
            try:
                alerts.send_due([failure], DATA_DIR / "alert_state.json", today, push_line)
            except Exception as alert_error:
                # 中斷的原因若就是 LINE 推不出去，這裡會再失敗一次。吞掉它：
                # failure 照樣回傳，main() 會以非零狀態結束，Actions 的紅燈就是訊號。
                print(f"  ❌ 國泰世華告警也送不出去：{type(alert_error).__name__}")
        return [failure], {}


def run(bootstrap: bool = False, dry_run: bool = False,
        pages: int = DEFAULT_PAGES, today: date | None = None) -> list[tuple[str, str]]:
    today = today or date.today()
    failures, stats = _run_buy(bootstrap, dry_run, pages, today)
    if bootstrap:
        # bootstrap 只為了不把 RSS 裡的舊文一次推出；國泰世華那條線沒有這個問題
        return failures

    cub_failures, cub_stats = _run_cub(dry_run, today)
    failures = failures + cub_failures
    if dry_run:
        return failures

    # 有任何失敗的那一輪不送「運作正常」，留到該週下一次乾淨的執行
    heartbeat_path = DATA_DIR / "heartbeat.json"
    if not failures and sw_state.should_heartbeat(
            sw_state.load_heartbeat(heartbeat_path), today):
        push_line(notify.format_heartbeat(
            feed_count=len(FEEDS),
            article_count=stats["articles"],
            promo_count=stats["promos"],
            cub_listed=cub_stats.get("listed"),
            cub_matched=cub_stats.get("matched"),
        ))
        sw_state.save_heartbeat(heartbeat_path, sw_state.heartbeat_period(today))
        print("已送出每週心跳。")

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="點數促銷監測與推播")
    parser.add_argument("--bootstrap", action="store_true",
                        help="首次執行：只把現有文章記為已看過，不判讀不推播")
    parser.add_argument("--dry-run", action="store_true",
                        help="照常判讀，訊息印到 stdout；不推播、不寫任何狀態檔")
    parser.add_argument("--pages", type=int, default=DEFAULT_PAGES,
                        help="每個 feed 抓幾頁（dry-run 想回溯多一點時調大）")
    args = parser.parse_args()
    failures = run(bootstrap=args.bootstrap, dry_run=args.dry_run, pages=args.pages)

    # 所有 feed 都掛掉時亮紅燈。告警有 7 天節流，否則第 2～7 天會是
    # 「綠燈、零訊息」，跟「今天沒有促銷」長得一模一樣。
    down = {source for source, _ in failures} & {f["name"] for f in FEEDS}
    if len(down) == len(FEEDS):
        print("❌ 所有 feed 都失敗，以非零狀態結束。")
        raise SystemExit(1)
    # 抽取失敗同理：API key 失效或餘額用盡時每篇都失敗，而失敗的文章
    # 約四天就滑出 feed。workflow 的 commit 步驟是 always()，亮紅燈不影響狀態。
    if any(source.endswith("／抽取") or source.startswith("國泰世華")
           for source, _ in failures):
        print("❌ 有判讀或國泰世華來源失敗，以非零狀態結束。")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
