# 麻醉日報異常告警 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 日報 pipeline 停擺或靜默降級時，以 LINE 通知使用者個人；並修掉 9/21 的分類 `TypeError`。

**Architecture:** 新增 `digest_alert.py`，兩支日報腳本把 `(key, reason)` 收集到模組層級的 `FAILURES`，`main()` 在 `finally` 交給 `digest_alert.report()`。節流（同 key 同 reason 7 天一次）與 LINE 推播直接 import `society_watch.state`／`society_watch.notify`，不改動學會監測。狀態存 `daily_data/alert_state.json`，在 Actions 上用 GitHub Contents API 讀寫。

**Tech Stack:** Python 3.11（Actions）／本機 `python3`、`requests`、`pytest`、GitHub Actions、LINE Messaging API。

**Spec:** `docs/superpowers/specs/2026-10-05-digest-alert-design.md`

**通用注意事項**

- macOS 沒有 `python`，一律 `python3`。
- repo 在 iCloud 路徑下，`git` 指令偶爾很慢，逾時就重跑。
- 工作區有使用者未提交的檔案（`.gitignore`、`CLAUDE.md`、`travel-atlas*.html`），**每次 commit 只 `git add` 該 task 列出的檔案**，不可 `git add -A`。
- Actions 會把狀態檔 commit 回 `main`，push 被拒時用 `git pull --no-rebase origin main` 再 push（不用 rebase／stash）。
- commit 訊息結尾加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- **Task 3 結束後必須停下來等使用者驗收，通過才做 Task 4 以後。**

## File Structure

| 檔案 | 動作 | 職責 |
|---|---|---|
| `digest_alert.py` | 新增 | 例外轉 reason、過期判定、組訊息、節流＋推播＋狀態讀寫 |
| `tests/test_digest_alert.py` | 新增 | 上述邏輯的單元測試（不打網路） |
| `daily_push.py` | 修改 | 降級點記錄到 `FAILURES`、`main()` 包一層、`TEST_ALERT` |
| `.github/workflows/daily-push.yml` | 修改 | env 加 `LINE_USER_ID`、`PYTHONUNBUFFERED`、`test_alert` 輸入 |
| `daily_fetch_classify.py` | 修改 | 降級點記錄、`_normalize_classification`、0 篇改非零結束、`main()` 包一層 |
| `tests/test_fetch_classify_normalize.py` | 新增 | 正規化函式的單元測試 |
| `.github/workflows/daily-fetch-classify.yml` | 修改 | env 加 LINE 兩個 secret、`PYTHONUNBUFFERED` |

---

### Task 1: `digest_alert.py` 的純函式（reason／is_stale／format_alert）

**Files:**
- Create: `digest_alert.py`
- Test: `tests/test_digest_alert.py`

- [ ] **Step 1: 寫失敗的測試**

建立 `tests/test_digest_alert.py`：

```python
"""日報異常告警測試。不打網路。"""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import digest_alert  # noqa: E402


# ── reason ────────────────────────────────────────────────────────────────────

def test_連線例外只標類別名():
    r = digest_alert.reason(requests.ConnectionError("DNS 解不出來"))
    assert r == "ConnectionError: DNS 解不出來"


def test_anthropic例外引導去查餘額():
    class FakeAPIError(Exception):
        pass
    FakeAPIError.__module__ = "anthropic._exceptions"
    r = digest_alert.reason(FakeAPIError("credit balance is too low"))
    assert r.startswith("Anthropic API 問題（先查餘額與月上限）FakeAPIError: ")
    assert "credit balance is too low" in r


def test_其他例外標成程式錯誤():
    r = digest_alert.reason(TypeError("'<=' not supported"))
    assert r == "程式錯誤（需改 code）TypeError: '<=' not supported"


def test_SystemExit只取訊息本身():
    r = digest_alert.reason(SystemExit("所有來源合計 0 篇，week.json 未更新"))
    assert r == "所有來源合計 0 篇，week.json 未更新"


def test_訊息截到80字且換行被壓掉():
    r = digest_alert.reason(ValueError("a\nb " + "x" * 200))
    detail = r.split("ValueError: ", 1)[1]
    assert "\n" not in r
    assert detail.startswith("a b ")
    assert len(detail) == 80


# ── is_stale ──────────────────────────────────────────────────────────────────

NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)


def test_七天整不算過期():
    assert digest_alert.is_stale((NOW - timedelta(days=7)).isoformat(), NOW) is False


def test_八天算過期():
    assert digest_alert.is_stale((NOW - timedelta(days=8)).isoformat(), NOW) is True


def test_沒有時區的時間當成UTC():
    naive = (NOW - timedelta(days=8)).replace(tzinfo=None).isoformat()
    assert digest_alert.is_stale(naive, NOW) is True


def test_欄位缺失或格式錯誤視為過期():
    assert digest_alert.is_stale(None, NOW) is True
    assert digest_alert.is_stale("上週一", NOW) is True


# ── format_alert ──────────────────────────────────────────────────────────────

def test_訊息標題含階段且每筆一行():
    text = digest_alert.format_alert("每日推播", [("week.json", "過期"), ("心情小語", "壞了")])
    lines = text.split("\n")
    assert lines[0] == "⚠️ 麻醉日報異常（每日推播）"
    assert "・week.json：過期" in lines
    assert "・心情小語：壞了" in lines
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_digest_alert.py -v`
Expected: 收集階段就 FAIL，`ModuleNotFoundError: No module named 'digest_alert'`

- [ ] **Step 3: 寫最小實作**

建立 `digest_alert.py`：

```python
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
```

（`base64`、`json`、`os`、`date`、`Path`、`notify`、`state` 在 Task 2 才會用到，先 import 進來。）

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest tests/test_digest_alert.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add digest_alert.py tests/test_digest_alert.py
git commit -m "feat(digest): 告警模組的 reason／過期判定／訊息格式

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `digest_alert.report()` 與狀態讀寫

**Files:**
- Modify: `digest_alert.py`（檔尾追加）
- Test: `tests/test_digest_alert.py`（檔尾追加）

- [ ] **Step 1: 寫失敗的測試**

在 `tests/test_digest_alert.py` 檔尾追加：

```python
# ── report ────────────────────────────────────────────────────────────────────

TODAY = date(2026, 10, 13)


class Harness:
    """把 LINE 與狀態讀寫換成記憶體版本。"""

    def __init__(self, monkeypatch, alerts=None):
        self.alerts = alerts or {}
        self.pushed = []
        self.saved = []
        monkeypatch.setattr(digest_alert.notify, "push_line", self.pushed.append)
        monkeypatch.setattr(digest_alert, "_load_state", lambda: (self.alerts, "sha1"))
        monkeypatch.setattr(
            digest_alert, "_save_state",
            lambda alerts, sha: self.saved.append((dict(alerts), sha)),
        )


def test_沒有失敗就什麼都不做(monkeypatch):
    h = Harness(monkeypatch)
    digest_alert.report("每日推播", [], today=TODAY)
    assert h.pushed == [] and h.saved == []


def test_第一次失敗會推播並記錄(monkeypatch):
    h = Harness(monkeypatch)
    digest_alert.report("每日推播", [("心情小語", "壞了")], today=TODAY)
    assert len(h.pushed) == 1
    assert "・心情小語：壞了" in h.pushed[0]
    saved, sha = h.saved[0]
    assert saved == {"心情小語": {"date": "2026-10-13", "reason": "壞了"}}
    assert sha == "sha1"


def test_冷卻期內同原因不重複推(monkeypatch):
    h = Harness(monkeypatch, {"心情小語": {"date": "2026-10-10", "reason": "壞了"}})
    digest_alert.report("每日推播", [("心情小語", "壞了")], today=TODAY)
    assert h.pushed == [] and h.saved == []


def test_冷卻期內換一種原因立刻推(monkeypatch):
    h = Harness(monkeypatch, {"心情小語": {"date": "2026-10-10", "reason": "壞了"}})
    digest_alert.report("每日推播", [("心情小語", "另一種壞法")], today=TODAY)
    assert len(h.pushed) == 1


def test_滿七天後同原因再推(monkeypatch):
    h = Harness(monkeypatch, {"心情小語": {"date": "2026-10-06", "reason": "壞了"}})
    digest_alert.report("每日推播", [("心情小語", "壞了")], today=TODAY)
    assert len(h.pushed) == 1


def test_只推到期的那幾筆(monkeypatch):
    h = Harness(monkeypatch, {"A": {"date": "2026-10-10", "reason": "x"}})
    digest_alert.report("週一抓取", [("A", "x"), ("B", "y")], today=TODAY)
    assert "・B：y" in h.pushed[0]
    assert "・A：x" not in h.pushed[0]


def test_重複的失敗只列一次(monkeypatch):
    h = Harness(monkeypatch)
    digest_alert.report("週一抓取", [("分類", "x"), ("分類", "x")], today=TODAY)
    assert h.pushed[0].count("・分類：x") == 1


def test_推播失敗不外拋且不寫狀態(monkeypatch):
    h = Harness(monkeypatch)

    def boom(text):
        raise requests.HTTPError("401")

    monkeypatch.setattr(digest_alert.notify, "push_line", boom)
    digest_alert.report("每日推播", [("心情小語", "壞了")], today=TODAY)  # 不可拋例外
    assert h.saved == []


def test_狀態讀取失敗時照樣推播(monkeypatch):
    h = Harness(monkeypatch)

    def boom():
        raise requests.ConnectionError("github 掛了")

    monkeypatch.setattr(digest_alert, "_load_state", boom)
    digest_alert.report("每日推播", [("心情小語", "壞了")], today=TODAY)
    assert len(h.pushed) == 1


def test_狀態寫入失敗不外拋(monkeypatch):
    h = Harness(monkeypatch)

    def boom(alerts, sha):
        raise requests.HTTPError("409")

    monkeypatch.setattr(digest_alert, "_save_state", boom)
    digest_alert.report("每日推播", [("心情小語", "壞了")], today=TODAY)  # 不可拋例外
    assert len(h.pushed) == 1


# ── 本機狀態檔（沒有 GITHUB_TOKEN 時）─────────────────────────────────────────

def test_本機模式讀寫磁碟檔(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setattr(digest_alert, "STATE_PATH", str(tmp_path / "alert_state.json"))
    assert digest_alert._load_state() == ({}, None)
    digest_alert._save_state({"A": {"date": "2026-10-13", "reason": "x"}}, None)
    assert digest_alert._load_state() == ({"A": {"date": "2026-10-13", "reason": "x"}}, None)


def test_send_test失敗要外拋(monkeypatch):
    import pytest

    def boom(text):
        raise requests.HTTPError("401")

    monkeypatch.setattr(digest_alert.notify, "push_line", boom)
    with pytest.raises(requests.HTTPError):
        digest_alert.send_test()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_digest_alert.py -v`
Expected: 新增的 12 個 FAIL，`AttributeError: module 'digest_alert' has no attribute '_load_state'`（或 `report`／`send_test`）；Task 1 的 10 個仍 PASS

- [ ] **Step 3: 寫實作**

在 `digest_alert.py` 檔尾追加：

```python
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
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest tests/test_digest_alert.py -v`
Expected: 22 passed

- [ ] **Step 5: 確認沒弄壞學會監測**

Run: `python3 -m pytest tests -q -m "not live"`
Expected: 全數通過，無 failed

- [ ] **Step 6: Commit**

```bash
git add digest_alert.py tests/test_digest_alert.py
git commit -m "feat(digest): 告警的節流、推播與狀態讀寫

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 接進 `daily_push.py` 與 workflow（做完停下來驗收）

**Files:**
- Modify: `daily_push.py`
- Modify: `.github/workflows/daily-push.yml`

`daily_push.py` 在 import 時就讀 `LINE_CHANNEL_ACCESS_TOKEN` 等環境變數，不寫單元測試；以語法檢查＋手動觸發驗收。

- [ ] **Step 1: import 與模組層級狀態**

`daily_push.py`，把

```python
import requests
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
```

改成

```python
import requests
from anthropic import Anthropic

import digest_alert

client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
```

並在 `NCBI_UA = {...}` 那一行之後加：

```python

STAGE = "每日推播"
# 降級但沒中斷的問題記在這裡，main() 結束時交給 digest_alert.report()
FAILURES: list[tuple[str, str]] = []
```

- [ ] **Step 2: 三個降級點各加一行**

`get_daily_quote()` 的 except 區塊，把

```python
        print(f"  ⚠️ 心情小語 API 失敗（{type(e).__name__}: {e}），改用本地語錄")
        return random.choice(QUOTE_FALLBACKS)
```

改成

```python
        print(f"  ⚠️ 心情小語 API 失敗（{type(e).__name__}: {e}），改用本地語錄")
        FAILURES.append(("心情小語", digest_alert.reason(e)))
        return random.choice(QUOTE_FALLBACKS)
```

`attach_fulltext()` 的 PMCID 查詢 except，把

```python
        print(f"  ⚠️ PMCID 查詢失敗（{type(e).__name__}: {e}），本次全部只用摘要")
        return 0
```

改成

```python
        print(f"  ⚠️ PMCID 查詢失敗（{type(e).__name__}: {e}），本次全部只用摘要")
        FAILURES.append(("全文補抓", digest_alert.reason(e)))
        return 0
```

（同函式裡單篇 `_fetch_pmc_body` 的 except **不要加**：實測只有約 1/5 拿得到全文，加了會天天響。）

`format_message()` 的 except，把

```python
        print(f"  ⚠️ 日報格式化 API 失敗（{type(e).__name__}: {e}），改推純文字清單")
        return plain_message(articles, topic, date_str, hot_theme)
```

改成

```python
        print(f"  ⚠️ 日報格式化 API 失敗（{type(e).__name__}: {e}），改推純文字清單")
        FAILURES.append(("日報格式化", digest_alert.reason(e)))
        return plain_message(articles, topic, date_str, hot_theme)
```

- [ ] **Step 3: `main()` 改名為 `run()`，加上過期檢查與「全文補抓整體失敗」記錄**

把 `def main():` 改成 `def run():`。

在 `run()` 裡，把

```python
    articles, hot_theme = load_articles(weekday)
    print(f"文章數：{len(articles)} | 熱點：{hot_theme or '-'}")

    if articles:
        try:
            attach_fulltext(articles)
        except Exception as e:
            print(f"  ⚠️ 全文補抓整體失敗（{type(e).__name__}: {e}），改用摘要")
```

改成

```python
    with open("daily_data/week.json", "r", encoding="utf-8") as f:
        fetched_at = json.load(f).get("fetched_at")
    if digest_alert.is_stale(fetched_at, datetime.now(timezone.utc)):
        print(f"  ⚠️ week.json 過期（fetched_at={fetched_at}），推的是舊資料")
        FAILURES.append(("week.json", digest_alert.STALE_REASON))

    articles, hot_theme = load_articles(weekday)
    print(f"文章數：{len(articles)} | 熱點：{hot_theme or '-'}")

    if articles:
        try:
            attach_fulltext(articles)
        except Exception as e:
            print(f"  ⚠️ 全文補抓整體失敗（{type(e).__name__}: {e}），改用摘要")
            FAILURES.append(("全文補抓", digest_alert.reason(e)))
```

- [ ] **Step 4: 新的 `main()`**

在 `if __name__ == "__main__":` 之前加：

```python
def main():
    if os.environ.get("TEST_ALERT") == "true":
        digest_alert.send_test()
        print("已送出測試告警，不推日報。")
        return

    try:
        run()
    except BaseException as e:
        # 含 SystemExit。記下來後照樣往外拋，保留 Actions 紅燈
        if not isinstance(e, KeyboardInterrupt):
            FAILURES.append((STAGE, digest_alert.reason(e)))
        raise
    finally:
        # 排在日報推送之後：告警失敗不可影響日報。report() 自己不會拋例外
        digest_alert.report(STAGE, FAILURES)


```

- [ ] **Step 5: 語法與 import 檢查**

Run:
```bash
python3 -m py_compile daily_push.py && \
CLAUDE_API_KEY=x LINE_CHANNEL_ACCESS_TOKEN=x LINE_GROUP_ID=x \
python3 -c "import daily_push; print(daily_push.STAGE, daily_push.FAILURES, callable(daily_push.run), callable(daily_push.main))"
```
Expected: `每日推播 [] True True`

- [ ] **Step 6: 改 workflow**

`.github/workflows/daily-push.yml`，把

```yaml
      force_weekday:
        description: '強制指定星期幾 (1=週一 … 5=週五)，留空用當日'
        required: false
        default: ''
```

改成

```yaml
      force_weekday:
        description: '強制指定星期幾 (1=週一 … 5=週五)，留空用當日'
        required: false
        default: ''
      test_alert:
        description: '只送一則測試告警到個人 LINE，不推日報（填 true）'
        required: false
        default: ''
```

把

```yaml
        env:
          CLAUDE_API_KEY: ${{ secrets.CLAUDE_API_KEY }}
          LINE_CHANNEL_ACCESS_TOKEN: ${{ secrets.LINE_CHANNEL_ACCESS_TOKEN }}
          LINE_GROUP_ID: ${{ secrets.LINE_GROUP_ID }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          FORCE_WEEKDAY: ${{ github.event.inputs.force_weekday }}
        run: python daily_push.py
```

改成

```yaml
        env:
          # Actions 的 log 是 pipe，stdout 會 block-buffered 而 stderr 不會，
          # 出事時 traceback 會排到正常輸出前面（9/21 那次就是）
          PYTHONUNBUFFERED: "1"
          CLAUDE_API_KEY: ${{ secrets.CLAUDE_API_KEY }}
          LINE_CHANNEL_ACCESS_TOKEN: ${{ secrets.LINE_CHANNEL_ACCESS_TOKEN }}
          LINE_GROUP_ID: ${{ secrets.LINE_GROUP_ID }}
          # 異常告警的收件人（個人，不是群組）。與學會監測共用同一個 secret
          LINE_USER_ID: ${{ secrets.LINE_USER_ID }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          FORCE_WEEKDAY: ${{ github.event.inputs.force_weekday }}
          TEST_ALERT: ${{ github.event.inputs.test_alert }}
        run: python daily_push.py
```

- [ ] **Step 7: 跑全部測試**

Run: `python3 -m pytest tests -q -m "not live"`
Expected: 全數通過

- [ ] **Step 8: Commit 並 push**

```bash
git add daily_push.py .github/workflows/daily-push.yml
git commit -m "feat(daily-push): 靜默降級與崩潰改為推 LINE 告警

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push || (git pull --no-rebase origin main && git push)
```

- [ ] **Step 9: 觸發測試告警**

Run:
```bash
gh workflow run daily-push.yml -f test_alert=true
sleep 20 && gh run list --workflow daily-push.yml --limit 1
```
等該次執行結束後 `gh run view <id> --log | grep 測試告警`
Expected: 結論 success，log 有 `已送出測試告警，不推日報。`

- [ ] **Step 10: ⏸ 停下來請使用者驗收**

請使用者確認兩件事，**兩件都通過才繼續 Task 4**：

1. 個人 LINE（麻醉日報 bot 的聊天室，不是群組）收到「⚠️ 麻醉日報異常（測試）」。
   沒收到的話：workflow 綠燈但沒訊息＝`LINE_USER_ID` 錯或封鎖了 bot（LINE 回 200 不代表送達）；紅燈＝看 log。
2. 隔天的排程日報照常送到群組（或使用者同意用 `gh workflow run daily-push.yml -f force_weekday=<1-5>` 立刻驗證。注意這會真的推一則日報到群組，並把那批文章記為已推送，要先問）。

---

### Task 4: 分類結果正規化（修 9/21 的 `TypeError`）

**Files:**
- Modify: `daily_fetch_classify.py`（`_call1_batch` 一帶）
- Test: `tests/test_fetch_classify_normalize.py`

- [ ] **Step 1: 寫失敗的測試**

建立 `tests/test_fetch_classify_normalize.py`：

```python
"""分類結果正規化測試。

daily_fetch_classify 在 import 時就建立 Anthropic client，所以先塞假金鑰
（建立 client 不會連線）。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("CLAUDE_API_KEY", "test-key")

import daily_fetch_classify as dfc  # noqa: E402


def test_正常輸入原樣通過():
    assignment, scores = dfc._normalize_classification(
        {"assignments": {"1": [1, 2], "3": [5]}, "scores": {"1": 8, "2": 6, "5": 9}}
    )
    assert assignment == {"1": [1, 2], "2": [], "3": [5], "4": [], "5": []}
    assert scores == {1: 8, 2: 6, 5: 9}


def test_字串索引轉成int():
    """9/21 的事故：Haiku 把索引回成字串，下游拿 int 跟 str 比大小就炸。"""
    assignment, _ = dfc._normalize_classification({"assignments": {"1": ["12", 3]}})
    assert assignment["1"] == [12, 3]


def test_轉不了的索引被丟掉():
    assignment, _ = dfc._normalize_classification(
        {"assignments": {"2": [4, "abc", None, 7]}}
    )
    assert assignment["2"] == [4, 7]


def test_主題值不是list視為空():
    assignment, _ = dfc._normalize_classification({"assignments": {"1": "3", "2": None}})
    assert assignment["1"] == [] and assignment["2"] == []


def test_assignments不是dict時五個主題都給空list():
    assignment, scores = dfc._normalize_classification({"assignments": [1, 2]})
    assert assignment == {k: [] for k in "12345"}
    assert scores == {}


def test_score的key或value轉不了就丟掉那一筆():
    _, scores = dfc._normalize_classification(
        {"scores": {"1": "8", "2": "high", "x": 5, "3": None}}
    )
    assert scores == {1: 8}


def test_正規化後的結果餵給classify不會炸(monkeypatch):
    articles = [{"title": f"t{i}", "journal": "J"} for i in range(1, 4)]
    monkeypatch.setattr(
        dfc, "_call1_classify_and_score",
        lambda arts: dfc._normalize_classification(
            {"assignments": {"1": ["1", "3"]}, "scores": {"1": "9"}}
        ),
    )
    monkeypatch.setattr(dfc, "_call2_hot_themes", lambda c: {k: None for k in "12345"})
    out = dfc.classify_articles(articles)
    assert [a["title"] for a in out["1"]["items"]] == ["t1", "t3"]
    assert out["1"]["items"][0]["score"] == 9
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_fetch_classify_normalize.py -v`
Expected: FAIL，`AttributeError: module 'daily_fetch_classify' has no attribute '_normalize_classification'`

- [ ] **Step 3: 寫實作**

`daily_fetch_classify.py`，在 `def _call1_batch(` 之前加：

```python
def _normalize_classification(parsed: dict) -> tuple[dict[str, list[int]], dict[int, int]]:
    """把模型回的 JSON 整理成下游假設的型別。

    Haiku 偶爾把文章索引回成字串（"12"），classify_articles 拿它跟 int 比大小
    就 TypeError，整週的 week.json 都沒更新（2026-09-21）。轉不了的直接丟掉：
    少一篇文章遠好過整次抓取報廢。
    """
    def to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    dropped = 0

    raw_assign = parsed.get("assignments")
    if not isinstance(raw_assign, dict):
        raw_assign = {}
    assignment: dict[str, list[int]] = {}
    for tid in "12345":
        values = raw_assign.get(tid)
        if not isinstance(values, list):
            values = []
        ints = [to_int(v) for v in values]
        dropped += ints.count(None)
        assignment[tid] = [i for i in ints if i is not None]

    raw_scores = parsed.get("scores")
    if not isinstance(raw_scores, dict):
        raw_scores = {}
    scores: dict[int, int] = {}
    for key, value in raw_scores.items():
        k, v = to_int(key), to_int(value)
        if k is None or v is None:
            dropped += 1
            continue
        scores[k] = v

    if dropped:
        print(f"    ⚠️ 分類結果有 {dropped} 筆型別不對，已略過")
    return assignment, scores


```

然後在 `_call1_batch` 裡，把

```python
    parsed     = json.loads(match.group())
    assignment = parsed.get("assignments", {})
    scores_raw = parsed.get("scores", {})
    scores     = {int(k): int(v) for k, v in scores_raw.items() if str(k).isdigit()}
    return assignment, scores
```

改成

```python
    parsed = json.loads(match.group())
    if not isinstance(parsed, dict):
        parsed = {}
    return _normalize_classification(parsed)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest tests/test_fetch_classify_normalize.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add daily_fetch_classify.py tests/test_fetch_classify_normalize.py
git commit -m "fix(fetch-classify): 模型把索引回成字串時不再整次崩潰

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 接進 `daily_fetch_classify.py` 與 workflow

**Files:**
- Modify: `daily_fetch_classify.py`
- Modify: `.github/workflows/daily-fetch-classify.yml`
- Test: `tests/test_fetch_classify_normalize.py`（追加一個）

- [ ] **Step 1: 寫失敗的測試（分類批次無法解析時要記錄）**

在 `tests/test_fetch_classify_normalize.py` 檔尾追加：

```python
class _FakeResp:
    def __init__(self, text):
        self.content = [type("Block", (), {"text": text})()]


def _fake_client(text):
    create = lambda **kwargs: _FakeResp(text)  # noqa: E731
    return type("Client", (), {"messages": type("Messages", (), {"create": staticmethod(create)})()})()


def test_模型回應沒有JSON時記錄失敗(monkeypatch):
    monkeypatch.setattr(dfc, "FAILURES", [])
    monkeypatch.setattr(dfc, "client", _fake_client("抱歉，我無法處理"))
    assignment, scores = dfc._call1_batch([{"title": "t", "abstract": "a", "journal": "J"}], offset=0)
    assert assignment == {k: [] for k in "12345"} and scores == {}
    assert dfc.FAILURES == [("分類", dfc.UNPARSEABLE_REASON)]


def test_模型回應是壞掉的JSON時記錄失敗而不是崩潰(monkeypatch):
    monkeypatch.setattr(dfc, "FAILURES", [])
    monkeypatch.setattr(dfc, "client", _fake_client('{"assignments": {"1": [1,'  + "}"))
    assignment, scores = dfc._call1_batch([{"title": "t", "abstract": "a", "journal": "J"}], offset=0)
    assert assignment == {k: [] for k in "12345"} and scores == {}
    assert dfc.FAILURES == [("分類", dfc.UNPARSEABLE_REASON)]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_fetch_classify_normalize.py -v`
Expected: 新增 2 個 FAIL（`AttributeError: ... has no attribute 'FAILURES'`），原本 7 個 PASS

- [ ] **Step 3: import 與模組層級狀態**

`daily_fetch_classify.py`，把

```python
import feedparser
import requests
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
```

改成

```python
import feedparser
import requests
from anthropic import Anthropic

import digest_alert

client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
```

在 `MIN_ARTICLES = 20 ...` 那一行之後加：

```python

STAGE = "週一抓取"
# 降級但沒中斷的問題記在這裡，main() 結束時交給 digest_alert.report()
FAILURES: list[tuple[str, str]] = []

# 最近四週的 log 裡正常的期刊最少也有 2 篇，出現 0 的（NEJM 連三週、
# Anesth Analg 30 個 PMID 解析出 0 篇）都是異常
ZERO_REASON = "回 0 篇，疑似 feed 改版或解析失效"
UNPARSEABLE_REASON = "模型回應無法解析，整批文章被略過"
```

- [ ] **Step 4: `_call1_batch` 無法解析時記錄**

把（Task 4 改完後的樣子）

```python
    raw   = resp.content[0].text.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {k: [] for k in "12345"}, {}

    parsed = json.loads(match.group())
    if not isinstance(parsed, dict):
        parsed = {}
    return _normalize_classification(parsed)
```

改成

```python
    raw   = resp.content[0].text.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        parsed = json.loads(match.group()) if match else None
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, dict):
        # 整批（最多 BATCH_SIZE 篇）都沒被分類，不能只是默默少掉
        print(f"    ⚠️ 第 {offset + 1} 篇起的這一批：{UNPARSEABLE_REASON}")
        FAILURES.append(("分類", UNPARSEABLE_REASON))
        return {k: [] for k in "12345"}, {}
    return _normalize_classification(parsed)
```

（只改 `_call1_batch`。`_call2_hot_themes` 裡長得很像的那段不要動：熱點偵測失敗只是少了熱點標題。）

- [ ] **Step 5: 跑測試確認通過**

Run: `python3 -m pytest tests/test_fetch_classify_normalize.py -v`
Expected: 9 passed

- [ ] **Step 6: `main()` 改名為 `run()`，來源層級的記錄**

把 `def main():` 改成 `def run():`。

在 `run()` 的 NCBI 迴圈，把

```python
        except Exception as e:
            # 單一來源掛掉不該讓整週的抓取全毀，記下來繼續跑
            print(f"  ❌ {journal} 抓取失敗（{type(e).__name__}: {e}）")
            failed_sources.append(journal)
            continue
        print(f"  {journal}: {len(arts)}")
        all_articles.extend(arts)
        time.sleep(0.5)
```

改成

```python
        except Exception as e:
            # 單一來源掛掉不該讓整週的抓取全毀，記下來繼續跑
            print(f"  ❌ {journal} 抓取失敗（{type(e).__name__}: {e}）")
            failed_sources.append(journal)
            FAILURES.append((journal, digest_alert.reason(e)))
            continue
        print(f"  {journal}: {len(arts)}")
        if not arts:
            FAILURES.append((journal, ZERO_REASON))
        all_articles.extend(arts)
        time.sleep(0.5)
```

RSS 迴圈，把

```python
        except Exception as e:
            print(f"  ❌ {name} 抓取失敗（{type(e).__name__}: {e}）")
            failed_sources.append(name)
            continue
        print(f"  {name}: {len(arts)}")
        all_articles.extend(arts)
```

改成

```python
        except Exception as e:
            print(f"  ❌ {name} 抓取失敗（{type(e).__name__}: {e}）")
            failed_sources.append(name)
            FAILURES.append((name, digest_alert.reason(e)))
            continue
        print(f"  {name}: {len(arts)}")
        if not arts:
            FAILURES.append((name, ZERO_REASON))
        all_articles.extend(arts)
```

- [ ] **Step 7: 0 篇改成非零結束；低篇數的訊息改成穩定字串**

把

```python
    if not unique:
        print("No articles found. Exiting.")
        return

    # 有來源掛掉且文章數明顯偏低時，不要用殘缺結果覆蓋掉上週的 week.json
    if failed_sources and len(unique) < MIN_ARTICLES:
        raise SystemExit(
            f"❌ 只抓到 {len(unique)} 篇（低於 {MIN_ARTICLES} 篇門檻）且有來源失敗，"
            "不覆蓋 week.json，請稍後重跑 workflow。"
        )
```

改成

```python
    # 以前這裡是 return（綠燈），week.json 停在上週、日報默默推舊文章
    if not unique:
        raise SystemExit("所有來源合計 0 篇，week.json 未更新")

    # 有來源掛掉且文章數明顯偏低時，不要用殘缺結果覆蓋掉上週的 week.json
    if failed_sources and len(unique) < MIN_ARTICLES:
        print(f"❌ 只抓到 {len(unique)} 篇（低於 {MIN_ARTICLES} 篇門檻）且有來源失敗")
        # SystemExit 的訊息會成為告警文字與節流 key，不放每次會變的數字
        raise SystemExit("文章數過低且有來源失敗，week.json 未更新，請稍後重跑 workflow")
```

- [ ] **Step 8: 新的 `main()`**

在檔尾 `if __name__ == "__main__":` 之前加：

```python
def main():
    try:
        run()
    except BaseException as e:
        # 含 SystemExit。記下來後照樣往外拋，保留 Actions 紅燈
        if not isinstance(e, KeyboardInterrupt):
            FAILURES.append((STAGE, digest_alert.reason(e)))
        raise
    finally:
        digest_alert.report(STAGE, FAILURES)


```

- [ ] **Step 9: 語法檢查與全部測試**

Run:
```bash
python3 -m py_compile daily_fetch_classify.py && python3 -m pytest tests -q -m "not live"
```
Expected: 全數通過

- [ ] **Step 10: 改 workflow**

`.github/workflows/daily-fetch-classify.yml`，把

```yaml
        env:
          CLAUDE_API_KEY: ${{ secrets.CLAUDE_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: python daily_fetch_classify.py
```

改成

```yaml
        env:
          # stdout 不加這個會被緩衝，traceback 排到正常輸出前面
          PYTHONUNBUFFERED: "1"
          CLAUDE_API_KEY: ${{ secrets.CLAUDE_API_KEY }}
          # 異常告警用：推給個人，不是日報群組
          LINE_CHANNEL_ACCESS_TOKEN: ${{ secrets.LINE_CHANNEL_ACCESS_TOKEN }}
          LINE_USER_ID: ${{ secrets.LINE_USER_ID }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: python daily_fetch_classify.py
```

- [ ] **Step 11: Commit 並 push**

```bash
git add daily_fetch_classify.py tests/test_fetch_classify_normalize.py .github/workflows/daily-fetch-classify.yml
git commit -m "feat(fetch-classify): 來源失敗、回 0 篇與分類無法解析改為推 LINE 告警

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push || (git pull --no-rebase origin main && git push)
```

- [ ] **Step 12: 手動觸發一次並看結果**

先告知使用者：這會重抓並覆蓋本週 `week.json`（跟週一排程做的事一樣，約花一次 Haiku 分類的費用），取得同意後：

```bash
gh workflow run daily-fetch-classify.yml
sleep 90 && gh run list --workflow daily-fetch-classify.yml --limit 1
gh run view <id> --log | grep -E "回 0 篇|異常告警|冷卻期|告警流程失敗|Unique articles|Saved"
```
Expected: 結論 success、有 `Unique articles:` 與 `Saved →`。若當次有期刊回 0 篇，log 會有 `已送出 N 則異常告警。`，使用者的個人 LINE 會收到「⚠️ 麻醉日報異常（週一抓取）」——這是正確行為，請使用者確認內容看得懂。

---

### Task 6: 更新記憶

**Files:**
- Modify: `/Users/wangyingyu/.claude/projects/-Users-wangyingyu-Library-Mobile-Documents-com-apple-CloudDocs-Jenna-agent/memory/project_anesthesia_digest.md`
- Modify: 同目錄 `MEMORY.md` 的日報那一行

- [ ] **Step 1: 在記憶檔「下次注意事項」之前加一節**

```markdown
## 異常告警（2026-10-05 上線）

`digest_alert.py`：兩支腳本把 `(key, reason)` 收進模組層級 `FAILURES`，`main()` 在 finally 交給 `digest_alert.report()`，推給**使用者個人**（`LINE_USER_ID`，與學會監測共用），不進日報群組。節流沿用 `society_watch.state.should_alert`（同 key 同 reason 7 天一次），狀態在 `daily_data/alert_state.json`（Contents API 寫回）。spec／plan 在 `docs/superpowers/specs|plans/2026-10-05-digest-alert*`。

- 會告警：單一期刊失敗或回 0 篇、分類批次無法解析、全部 0 篇（已改成紅燈）、`week.json` 超過 7.5 天、Sonnet 格式化退回純文字、心情小語退回本地、PMCID 查詢整批失敗、任何崩潰
- 不告警：候選池見底、單篇 PMC 全文抓不到
- 驗證管道：Actions → 每日推送 → Run workflow → `test_alert` 填 `true`
- **兩個 workflow 的排程實際延遲約五小時**（抓取 13–14 點、推播 14–15 點台灣時間），所以過期判定用 7.5 天而不是比對週次
- reason 字串是節流 key，不可放每次會變的數字
- 起因：查 log 發現 NEJM 連三週回 0 篇、9/21 分類 TypeError 讓整週推舊文章，都沒人知道
```

同檔「模型分工」不動（整理模型仍是 `claude-sonnet-5`；2026-10-05 討論過換 Opus 5.5，使用者決定不換）。在「已解決的關鍵問題」表格加一列：

```markdown
| 2026-09-21 分類 `TypeError`（Haiku 把索引回成字串） | `_normalize_classification` 把模型輸出轉型，轉不了的丟掉 |
```

- [ ] **Step 2: 更新 `MEMORY.md` 索引那一行**

把

```markdown
- [麻醉科日報自動化進度](project_anesthesia_digest.md) — 已完整上線：週一抓取分類 + 週一至週五 LINE 日報推送；兩段 Haiku pipeline（分類評分 + 熱點偵測）、防重複、多元性限制均已實作
```

改成

```markdown
- [麻醉科日報自動化進度](project_anesthesia_digest.md) — 已完整上線：週一抓取分類 + 週一至週五 LINE 日報推送；兩段 Haiku pipeline（分類評分 + 熱點偵測）、防重複、多元性限制均已實作；2026-10-05 加 ⚠️ 異常告警（digest_alert.py，推個人 LINE，7 天節流，`test_alert` 可驗證管道）；排程實際延遲約五小時
```

---

## Spec 對照

| Spec 章節 | Task |
|---|---|
| §3 架構、§5 reason、§8 訊息格式 | 1 |
| §6 節流與狀態、§7 `report()` 不外拋 | 2 |
| §4 每日推播判定、§7 流程、§9 `daily-push.yml`、`test_alert` | 3 |
| §4 隨附修正（分類 `TypeError`） | 4 |
| §4 週一抓取判定、0 篇改非零結束、§9 `daily-fetch-classify.yml` | 5 |
| §13 驗收順序 | 3 的 Step 9–10、5 的 Step 12 |
| §13 更新記憶 | 6 |
