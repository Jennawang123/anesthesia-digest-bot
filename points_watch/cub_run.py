"""國泰世華小樹點轉點加碼這條線的流程。

由 main.run 在買點流程之後呼叫。這裡拋出的例外由 main 接住，
不會影響買點那邊已完成的推播與狀態。
"""
import traceback
from datetime import date
from pathlib import Path
from typing import Callable

from society_watch import fetch
from society_watch import state as sw_state
from society_watch.notify import split_message

from . import alerts, cub, cub_extract, cub_notify, cub_store

LIST_SOURCE = "國泰世華／清單"
JUDGE_SOURCE = "國泰世華／判讀"


def _reason(error: Exception) -> str:
    return alerts.reason(error, plain=(cub.CubError,))


def run(data_dir: Path, today: date, dry_run: bool,
        push: Callable[[str], None]) -> tuple[list[tuple[str, str]], dict]:
    """回傳（失敗清單, {"listed": 清單筆數, "matched": 初篩命中數}）。"""
    seen_path = data_dir / "cub_seen.json"
    promos_path = data_dir / "cub_promos.json"
    alerts_path = data_dir / "alert_state.json"

    failures: list[tuple[str, str]] = []
    stats = {"listed": 0, "matched": 0}
    candidates: list[cub.Campaign] = []
    try:
        campaigns = cub.parse_list(fetch.get(cub.LIST_URL))
        candidates = [c for c in campaigns if cub.is_candidate(c)]
        stats = {"listed": len(campaigns), "matched": len(candidates)}
        print(f"  ✅ 國泰世華清單 {len(campaigns)} 筆，初篩命中 {len(candidates)} 筆")
    except Exception as e:
        print(f"  ❌ 國泰世華清單失敗：{type(e).__name__}: {e}")
        traceback.print_exc()
        failures.append((LIST_SOURCE, _reason(e)))

    seen = sw_state.load_seen(seen_path)
    promos = cub_store.load(promos_path)
    # dry-run 無視 seen，才看得到現有活動會產生什麼訊息
    fresh = candidates if dry_run else [c for c in candidates if c.key not in seen]

    judged: set[str] = set()
    messages: list[str] = []
    pending: dict[str, dict] = {}
    announced: set[str] = set()    # 本輪第一次推出的新活動（不含內容更新）

    for campaign in fresh:
        print(f"  判讀：[國泰世華] {campaign.title}")
        try:
            text = cub.page_text(fetch.get(cub.page_json_url(campaign)))
            partners = cub_extract.extract(campaign, text, today)
        except Exception as e:
            # 不進 judged → 不記為已判讀 → 明天重試
            print(f"    ❌ {type(e).__name__}: {e}")
            traceback.print_exc()
            failures.append((JUDGE_SOURCE, _reason(e)))
            continue
        judged.add(campaign.key)
        if partners is None:
            print("    → 不是轉點加碼")
            continue

        dicts = [p.as_dict() for p in partners]
        old = promos.get(campaign.path)
        if not dry_run and isinstance(old, dict) and cub_store.same_content(
                old.get("partners") or [], dicts):
            print("    → 內容與已推播的相同")
            continue
        updated = isinstance(old, dict) and not dry_run
        print(f"    → {'內容更新' if updated else '新活動'}，{len(dicts)} 個夥伴")
        messages.append(cub_notify.format_campaign(
            campaign.title, campaign.url, dicts, updated=updated))
        fresh_entry = cub_store.entry(
            campaign.title, campaign.url, dicts, today,
            reminded=old.get("reminded") if updated else None)
        if updated and isinstance(old.get("first_seen"), str):
            fresh_entry["first_seen"] = old["first_seen"]
        pending[campaign.path] = fresh_entry
        if not updated:
            announced.add(campaign.path)

    if dry_run:
        print("\n===== dry-run：國泰世華會推播的內容 =====")
        print("\n\n".join(messages) if messages else "（沒有轉點加碼活動）")
        if failures:
            print("\n（失敗）" + "；".join(f"{s}：{r}" for s, r in failures))
        return list(dict.fromkeys(failures)), stats

    # 三篇活動頁以同一個原因失敗時只算一筆：告警一行、回傳給 main 的也是一筆
    failures = list(dict.fromkeys(failures))

    # 告警先送：之後的推播若拋例外，當天的異常才不會跟著消失
    sent = alerts.send_due(failures, alerts_path, today, push)
    if sent:
        print(f"已送出 {sent} 則國泰世華告警。")

    for message in messages:
        for part in split_message(message):
            push(part)

    # 推播成功才推進狀態。push 失敗會拋例外穿出去，這段到不了，
    # 下一輪重新判讀重新推——重複優於漏報。
    if pending:
        promos.update(pending)
        cub_store.save(promos_path, promos)
    if judged - seen:
        sw_state.save_seen(seen_path, seen | judged)

    for path, entry in promos.items():
        if path in announced:
            # 本輪才第一次推出 ✈️ 的活動不在同一輪再提醒一次；明天仍在期限內會提醒。
            # 只排除「新活動」：內容更新（例如中途加入長榮）不該吃掉其他夥伴的截止提醒。
            continue
        for end, partners in cub_store.due_groups(entry, today):
            push(cub_notify.format_reminder(
                entry.get("title", ""), entry.get("url", ""), end, partners, today))
            # 這個檔可能被手改壞；reminded 不是 list 時重建，否則提醒送出卻記不下來，
            # 會變成每天重複提醒
            if not isinstance(entry.get("reminded"), list):
                entry["reminded"] = []
            entry["reminded"].append(end.isoformat())
            cub_store.save(promos_path, promos)
            print(f"已送出國泰世華截止提醒（{end}）。")

    return failures, stats
