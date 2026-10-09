"""例外 → 告警文字，以及節流後送出告警。買點與國泰世華兩條線共用。"""
from datetime import date
from pathlib import Path
from typing import Callable

import requests

from society_watch import state as sw_state

from . import notify


def reason(error: Exception, plain: tuple[type, ...] = ()) -> str:
    """把例外轉成告警文字。這串同時是節流鍵的一部分，必須短而穩定。

    plain 是「訊息本身就是給人看的原因」的例外型別（例如 FeedError），
    直接用它的訊息。
    """
    if plain and isinstance(error, plain):
        return str(error)
    if isinstance(error, requests.RequestException):
        return f"連線失敗 {type(error).__name__}"
    if (type(error).__module__ or "").startswith("anthropic"):
        return f"Anthropic API 問題（先查餘額與月上限）{type(error).__name__}"
    return f"程式錯誤（需改 code）{type(error).__name__}"


def _key(source: str, why: str) -> str:
    # 節流鍵含原因：同一來源以兩種原因失敗時，若鍵只有來源，後寫的會蓋掉
    # 先寫的，隔天兩個原因輪流被當成「換了壞法」而天天告警。
    return f"{source}｜{why}"


def send_due(failures: list[tuple[str, str]], path: Path, today: date,
             push: Callable[[str], None]) -> int:
    """送出不在冷卻期內的告警，回傳送出的筆數。推播成功後才記錄冷卻。"""
    if not failures:
        return 0
    state = sw_state.load_alerts(path)
    due = [f for f in failures if sw_state.should_alert(state, _key(*f), today, f[1])]
    if not due:
        return 0
    push(notify.format_alert(due))
    for source, why in due:
        sw_state.record_alert(state, _key(source, why), today, why)
    sw_state.save_alerts(path, state)
    return len(due)
