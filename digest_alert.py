"""麻醉日報異常告警。

兩支日報腳本把 (key, reason) 收集起來交給 report()；節流與 LINE 推播沿用
society_watch。設計見 docs/superpowers/specs/2026-10-05-digest-alert-design.md。
"""
import base64
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from society_watch import notify, state

STATE_PATH = "daily_data/alert_state.json"

# 兩個 workflow 的排程實際都延遲約五小時，週一推播與抓取的先後只差三四十分鐘。
# 7.5 天讓週一（上次抓取約 7.0 天前）不會響，週二起才響。
STALE_AFTER = timedelta(days=7, hours=12)

# 刻意不帶實際天數：reason 是節流 key，帶天數的話每天都是新 reason，
# 7 天冷卻會失效變成天天告警。
STALE_REASON = "已超過 7 天未更新，週一抓取可能失敗"


def reason(error: BaseException) -> str:
    """把例外轉成告警文字。

    這串同時是 should_alert 的節流 key，所以要短而穩定。
    分三類是為了讓人看到訊息就知道該去哪裡查：站方／帳單／程式碼。
    """
    detail = " ".join(str(error).split())[:80]
    if isinstance(error, SystemExit):
        return detail
    name = type(error).__name__
    if isinstance(error, requests.RequestException):
        return f"{name}: {detail}"
    # 餘額用盡與撞月上限都長這樣，標成「程式錯誤」會把人引導去翻 code
    if (type(error).__module__ or "").startswith("anthropic"):
        return f"Anthropic API 問題（先查餘額與月上限）{name}: {detail}"
    return f"程式錯誤（需改 code）{name}: {detail}"


def is_stale(fetched_at, now: datetime) -> bool:
    """week.json 是否過期。欄位缺失或壞掉一律當過期（fail-open）。"""
    try:
        fetched = datetime.fromisoformat(fetched_at)
    except (TypeError, ValueError):
        return True
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return now - fetched > STALE_AFTER


def format_alert(stage: str, failures: list[tuple[str, str]]) -> str:
    lines = [f"⚠️ 麻醉日報異常（{stage}）", ""]
    lines.extend(f"・{key}：{why}" for key, why in failures)
    lines.append("")
    lines.append("詳情見 GitHub Actions log。")
    return "\n".join(lines)


def _api() -> tuple[str, dict] | None:
    """Actions 上回傳 (Contents API 網址, headers)；本機沒有 token 時回 None。"""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        return None
    return (
        f"https://api.github.com/repos/{repo}/contents/{STATE_PATH}",
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def _load_state() -> tuple[dict, str | None]:
    """回傳 (告警紀錄, 檔案 sha)。

    Actions 上讀 Contents API 而非磁碟：抓取 workflow 沒有 git pull，
    checkout 之後別的 workflow 寫入的狀態在磁碟上看不到。
    """
    api = _api()
    if api is None:
        return state.load_alerts(Path(STATE_PATH)), None
    url, headers = api
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code == 404:
        return {}, None
    resp.raise_for_status()
    body = resp.json()
    data = json.loads(base64.b64decode(body["content"]).decode("utf-8"))
    return (data if isinstance(data, dict) else {}), body.get("sha")


def _save_state(alerts: dict, sha: str | None) -> None:
    api = _api()
    if api is None:
        state.save_alerts(Path(STATE_PATH), alerts)
        return
    url, headers = api
    text = json.dumps(alerts, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    payload: dict = {
        "message": "chore: update digest alert state [skip ci]",
        "content": base64.b64encode(text.encode("utf-8")).decode(),
        "committer": {
            "name": "github-actions[bot]",
            "email": "github-actions[bot]@users.noreply.github.com",
        },
    }
    if sha:
        payload["sha"] = sha
    requests.put(url, headers=headers, json=payload, timeout=30).raise_for_status()


def report(stage: str, failures: list[tuple[str, str]], today: date | None = None) -> None:
    """節流後把失敗推給使用者個人。

    ⚠️ 這個函式不可拋例外：它跑在日報腳本的 finally 裡，拋出去會蓋掉
    原本的例外，也會讓「日報已送達但告警失敗」變成紅燈。
    """
    if not failures:
        return
    try:
        today = today or date.today()
        failures = list(dict.fromkeys(failures))
        try:
            alerts, sha = _load_state()
        except Exception as e:
            # fail-open：讀不到紀錄就當成沒告警過，寧可多吵一次
            print(f"  ⚠️ 告警狀態讀取失敗（{type(e).__name__}: {e}），視為全部該告警")
            alerts, sha = {}, None
        due = [f for f in failures if state.should_alert(alerts, f[0], today, f[1])]
        if not due:
            print("有異常但都在告警冷卻期內，不重複告警。")
            return
        notify.push_line(format_alert(stage, due))
        print(f"已送出 {len(due)} 則異常告警。")
        # 推播成功才記錄，否則下次就被冷卻期吃掉而永遠沒送出去
        for key, why in due:
            state.record_alert(alerts, key, today, why)
        _save_state(alerts, sha)
    except Exception as e:
        print(f"  ⚠️ 告警流程失敗（{type(e).__name__}: {e}），不影響日報本身")


def send_test() -> None:
    """手動驗收用。LINE 回 200 不代表送達，只有人眼確認收到才算數。

    刻意不吞例外：測試告警送不出去就該讓 workflow 亮紅燈。
    """
    notify.push_line(
        "⚠️ 麻醉日報異常（測試）\n\n這是手動觸發的測試告警，收到代表告警管道正常。"
    )
