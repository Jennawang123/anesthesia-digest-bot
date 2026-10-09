"""點數類通知（買點促銷、國泰世華轉點）專用的 LINE 推送。

使用者要把這類通知與麻醉日報、學會監測分到不同的聊天室，所以走另一支 bot：
優先讀 POINTS_LINE_*，沒設定就退回既有的 LINE_*——新 bot 還沒建好之前
通知不會中斷。

兩個變數各自獨立後備：新舊 channel 掛在同一個 provider 時 user ID 相同，
只設 POINTS_LINE_CHANNEL_ACCESS_TOKEN 就夠了。

用 `or` 而不是 dict.get 的預設值：GitHub Actions 對不存在的 secret
傳的是空字串，不是不傳。
"""
import os

import requests


def _env(primary: str, fallback: str) -> str:
    return os.environ.get(primary) or os.environ[fallback]


def push_line(text: str) -> None:
    """推播一則訊息。失敗必須拋例外：呼叫端靠它決定要不要推進狀態。

    LINE 回 200 不代表送達（封鎖、沒加好友、user ID 屬於別的 provider
    都可能回 200），這由每週心跳覆蓋。
    """
    token = _env("POINTS_LINE_CHANNEL_ACCESS_TOKEN", "LINE_CHANNEL_ACCESS_TOKEN")
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "to": _env("POINTS_LINE_USER_ID", "LINE_USER_ID"),
            "messages": [{"type": "text", "text": text}],
        },
        timeout=30,
    )
    resp.raise_for_status()
