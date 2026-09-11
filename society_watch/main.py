"""學會活動監測主流程。

用法：
    python3 -m society_watch.main --bootstrap   # 首次執行：只寫狀態檔，不推播
    python3 -m society_watch.main               # 日常執行
"""
import argparse
import sys
import traceback

import requests
from datetime import date
from pathlib import Path

from . import extract, fetch, llm, notify, state
from .models import Event
from .sources import SOURCES, pain_urls

DATA_DIR = Path(__file__).resolve().parent

PARSERS = {
    "tsa": lambda html, cfg: extract.parse_tsa(html),
    "tscva": lambda html, cfg: extract.parse_tscva(html),
    "rapm": lambda html, cfg: extract.parse_rapm(html, kind=cfg["kind"]),
    "pain": lambda html, cfg: extract.parse_pain(html),
    "tweccm": lambda html, cfg: extract.parse_tweccm(html),
}


def _reason(error: Exception) -> str:
    """把例外轉成告警文字。

    這串同時是 should_alert 的節流 key，所以要短而穩定——訊息每輪不同的話
    7 天冷卻會失效變成天天吵。

    另外要把「網站的問題」與「我們的程式壞了」分開講：parser 的 TypeError／
    KeyError 也會走到這裡，跟斷線長得一樣，但它不會自己好。人看到
    「程式錯誤」才知道要去改 code，而不是等站方修好。
    """
    detail = str(error).replace("\n", " ")[:80]
    if isinstance(error, requests.RequestException):
        return f"{type(error).__name__}: {detail}"
    # Anthropic SDK 的例外要單獨標示：餘額用盡與額度上限都長這樣，
    # 若跟 parser 的 TypeError 一起標成「程式錯誤」，會把人引導去查程式碼，
    # 但實際上該先看帳單餘額。
    if (type(error).__module__ or "").startswith("anthropic"):
        return f"Anthropic API 問題（先查餘額與月上限）{type(error).__name__}: {detail}"
    return f"程式錯誤（需改 code）{type(error).__name__}: {detail}"


def snapshot_path(source: str) -> Path:
    """文字來源的快照檔路徑。

    讀（collect_text_source）與寫（run.advance_state）共用這一個函式。
    兩處各自組檔名的話，改了其中一處就會變成「永遠讀不到上一輪的快照」→
    每輪整頁都算新增 → 撞 MAX_NEW_LINES 天天告警。
    """
    return DATA_DIR / f"snapshot_{source.lower()}.txt"


def collect_text_source(cfg: dict) -> tuple[list[Event], list[str], str | None]:
    """無結構頁面的通用處理：整頁純文字與上次快照 diff，新增段落交給 Haiku。

    回傳（事件, 本次全文行, 失敗原因）。只有 diff 出現新增行時才呼叫 Haiku。

    注意 llm.classify() 在「回應無法解析」與「新增量異常」時會拋
    LLMResponseError，由 collect() 的 except 接住 → 記成該站失敗 →
    告警 + 不更新快照 + 下輪重試。若改成回空 list，模型回垃圾就會偽裝成
    「今天沒有活動」，快照照樣前進而永久漏報。
    """
    source = cfg["source"]
    html = fetch.get(cfg["url"])
    lines = extract.page_lines(html)

    previous = state.load_snapshot(snapshot_path(source))
    if previous and len(lines) < len(previous) * 0.5:
        return [], lines, f"純文字行數自 {len(previous)} 暴跌至 {len(lines)}，疑似改版"

    if not previous:
        # 首次執行：只建立快照，不送 LLM（整頁都會是「新增」，既貴又無意義）
        return [], lines, None

    new_lines = extract.page_new_lines(lines, previous)
    return llm.classify(new_lines, source, cfg["label"], cfg["url"]), lines, None


def collect(today: date) -> tuple[list[Event], list[tuple[str, str]], dict[str, list[str]]]:
    """逐站抓取與解析。單站失敗不影響其他站。

    回傳（事件, 失敗清單, {來源代號: 該來源本次全文行}）。第三個值只收錄
    **本輪成功的文字來源**；失敗的來源一律不放進去，呼叫端就不會推進它的
    快照——快照是文字來源對「什麼是新的」的唯一記憶，其他站每輪重抓完整
    列表可自我修復，只有它沒有第二份備援。

    這裡不再用 cfg["source"] == "AIRWAY" 之類的名稱判斷來分派，改看
    cfg["parser"]，而且 cfg 是直接傳進 collect_text_source 的、沒有第二次
    查表，因此不會重演「兩處用不同 key 判斷同一件事」那種自相矛盾的訊號。
    """
    events: list[Event] = []
    failures: list[tuple[str, str]] = []
    snapshots: dict[str, list[str]] = {}

    for cfg in SOURCES:
        source = cfg["source"]
        # 同一個 source 可能有多筆設定（RAPM 的學會活動／友會活動、
        # TWECCM 的其他公告／首頁）。告警 key 若只用 source，其中一筆失敗
        # 會吃掉另一筆的 7 天冷卻期，真故障會被另一個故障的節流紀錄遮住。
        alert_key = f"{source}／{cfg['kind']}" if cfg.get("kind") else source

        if cfg["parser"] == "text":
            try:
                found, lines, text_error = collect_text_source(cfg)
            except Exception as e:
                print(f"  ❌ {alert_key} 抓取失敗：{type(e).__name__}: {e}")
                traceback.print_exc()
                failures.append((alert_key, _reason(e)))
                continue
            if text_error:
                print(f"  ⚠️ {alert_key} {text_error}")
                failures.append((alert_key, text_error))
                continue
            # 只有走到這一行才登記快照。上面兩條 continue 都刻意不登記，
            # 那正是「失敗的來源不推進快照」這個保證的實作位置。
            # 文字來源解析出 0 筆是常態（沒有新增行），不可比照列表站
            # 當成「疑似改版」。
            snapshots[source] = lines
            events.extend(found)
            print(f"  ✅ {alert_key} {len(found)} 筆")
            continue

        urls = pain_urls(today) if cfg["parser"] == "pain" else [cfg["url"]]
        try:
            found: list[Event] = []
            for url in urls:
                found.extend(PARSERS[cfg["parser"]](fetch.get(url), cfg))
        except Exception as e:
            print(f"  ❌ {alert_key} 抓取失敗：{type(e).__name__}: {e}")
            traceback.print_exc()   # 程式自身的 bug 要在 Actions log 留下行號
            failures.append((alert_key, _reason(e)))
            continue

        # found 是該站所有 URL 的累加結果。PAIN 的明年度清單正常為空，
        # 但今年＋明年全空就確實異常，故此處統一判斷即可。
        if not found:
            failures.append((alert_key, "解析出 0 筆，疑似改版"))
            print(f"  ⚠️ {alert_key} 解析出 0 筆，疑似改版")
            continue

        print(f"  ✅ {alert_key} {len(found)} 筆")
        events.extend(found)

    return events, failures, snapshots


def run(bootstrap: bool = False, today: date | None = None) -> list[tuple[str, str]]:
    today = today or date.today()
    seen_path = DATA_DIR / "seen.json"
    alerts_path = DATA_DIR / "alert_state.json"
    heartbeat_path = DATA_DIR / "heartbeat.json"

    print(f"執行日期：{today}｜模式：{'bootstrap' if bootstrap else '日常'}")
    events, failures, snapshots = collect(today)

    seen = state.load_seen(seen_path)
    fresh = state.filter_new(events, seen)
    print(f"抓到 {len(events)} 筆，其中新項目 {len(fresh)} 筆")

    def advance_state() -> None:
        """把狀態推進到「已通知」。只在推播成功後呼叫。

        snapshots 只含本輪成功的文字來源，所以失敗的那個不會被推進；
        逐來源寫出而非只寫一份，兩個文字來源的記憶才彼此獨立。
        """
        state.save_seen(seen_path, seen | {e.key for e in events})
        for source, lines in snapshots.items():
            state.save_snapshot(snapshot_path(source), lines)

    if bootstrap:
        advance_state()
        print("bootstrap 模式：只寫狀態檔，不推播。")
        if failures:
            names = "、".join(source for source, _ in failures)
            print(
                f"⚠️ {names} 本次失敗，未種進狀態檔。"
                "修好後請再跑一次 bootstrap，否則下次成功時會把該站現存項目一次推出。"
            )
        return failures

    # 告警先送：事件推播若拋例外，當天的異常告警才不會跟著一起消失
    if failures:
        alerts = state.load_alerts(alerts_path)
        due = [f for f in failures if state.should_alert(alerts, f[0], today, f[1])]
        if due:
            notify.push_line(notify.format_alert(due))
            for source, reason in due:
                state.record_alert(alerts, source, today, reason)
            state.save_alerts(alerts_path, alerts)
            print(f"已送出 {len(due)} 則告警。")
        else:
            print("有失敗但都在告警冷卻期內，不重複告警。")

    if fresh:
        for part in notify.split_message(notify.format_message(fresh)):
            notify.push_line(part)
        print(f"已推播 {len(fresh)} 則。")
    else:
        print("沒有新項目，不推播。")

    # 推播成功才推進狀態。push_line 內的 raise_for_status 會讓失敗穿出去，
    # 於是這行到不了，下一輪重推——重複優於漏報。
    advance_state()

    # 月度心跳排在這之後，語意是「一個完整週期跑完了」。
    # 它存在的理由見 §10：LINE 回 200 不代表送達，userId 填錯或使用者封鎖
    # 官方帳號時整條線會靜默死亡而毫無訊號。心跳建立可預期的節奏，
    # 讓「沒收到」本身成為訊號。心跳自己失敗不影響漏報保證。
    last_beat = state.load_heartbeat(heartbeat_path)
    if state.should_heartbeat(last_beat, today):
        notify.push_line(notify.format_heartbeat(
            source_count=len(SOURCES),
            seen_count=len(seen | {e.key for e in events}),
            fresh_count=len(fresh),
        ))
        state.save_heartbeat(heartbeat_path, today.strftime("%Y-%m"))
        print("已送出月度心跳。")

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="學會活動監測與推播")
    parser.add_argument(
        "--bootstrap", action="store_true",
        help="首次執行：只建立狀態檔，不推播（避免把現存約 50 則一次推出）",
    )
    args = parser.parse_args()
    failures = run(bootstrap=args.bootstrap)

    # 全站皆失敗時以非零狀態結束。否則 collect() 把每站的例外都吃進 failures、
    # 告警又是同站同壞法 7 天一次，於是第 2～7 天會是「完全綠燈、零訊息」，
    # 跟「今天真的沒有新活動」在 Actions 摘要頁上長得一模一樣。
    if len(failures) >= len(SOURCES):
        print("❌ 所有來源都失敗，以非零狀態結束讓 Actions 亮紅燈。")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
