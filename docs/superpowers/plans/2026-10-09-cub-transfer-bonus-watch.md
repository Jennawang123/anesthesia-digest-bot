# 國泰世華轉點加碼監測＋點數通知分流 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) 讓 `points_watch` 的所有通知改由一支獨立的 LINE bot 推送，與麻醉日報、學會監測分開聊天室；(2) 每天檢查國泰世華的活動清單，出現小樹點轉哩程／積分的限時加碼時推播全部夥伴的加贈內容，並在各截止日前 3 天提醒。

**Architecture:** 在既有 `points_watch/` 內新增 `cub*.py` 一組模組，作為買點監測之外的第二條線，共用同一支 workflow 與排程。`main.run` 拆成「買點流程 → CUB 流程 → 心跳」三段，CUB 的任何例外由 `main` 接住，不影響買點那邊已完成的推播與狀態。LINE 推送改走 `points_watch/line.py`，優先讀 `POINTS_LINE_*` 兩個 secret，沒設定就退回現有的 bot。

**Tech Stack:** Python 3.11、`requests`、`anthropic`（`claude-haiku-4-5`）、pytest、GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-10-09-cub-transfer-bonus-watch-design.md`

---

## 已實抓驗證的事實（2026-10-09）

1. 清單端點 `https://www.cathay-cube.com.tw/cathaybk/personal/event/overview/credit-card.model.list.json` 回 JSON：`{"campaigns": [{"campaignPath": str, "campaignProps": {...}}], "currentPagePath": ..., "currentPageProperties": ...}`，149 筆。
2. 149 筆的 `campaignProps` 全部都有 `jcr:title`、`campaignTitle`、`campaignContent`、`cq:lastModified`（ISO 字串，例 `2026-09-18T08:58:04.436+00:00`）。`subtitle` 不是每筆都有。
3. `campaignPath` 例：`/content/cub-aem-cs/zh-tw/cathaybk/personal/event/overview/credit-card/travel/202609/miles20251011.html`。公開網址＝`https://www.cathay-cube.com.tw` ＋ 去掉前綴 `/content/cub-aem-cs/zh-tw` 與結尾 `.html`；再加 `.model.json` 就是活動內文的 JSON。
4. 活動頁 JSON 是巢狀元件樹。內文在 `:type` 含 `cub-main` 的節點底下，散落於鍵名為 `text`、`title`、`content`、`subTitle`、`description` 的字串（含 HTML 標籤、`&nbsp;`、`&gt;`）。今年的加碼頁取出約 3,000 字，常態兌換比率頁約 5,000 字且不含「加贈」。
5. 以「（里程｜哩程｜里數｜哩數｜積分）且（轉換｜兌換｜加碼｜加贈）」比對標題＋摘要，149 筆恰命中 3 筆，`jcr:title` 分別為：
   - `秋日遊-點數轉換指定航空里程/飯店積分限時加碼`（是加碼活動）
   - `小樹點(信用卡)兌換航空里程/飯店積分｜國泰世華商業銀行`（常態頁）
   - `PChome 24h購物2026/10_累積加碼活動`（無關）
6. 今年加碼頁的內容：亞洲萬里通 10/1–10/31（滿 1 萬里送 800、滿 2 萬里送 1,600；登錄期間 10/28 16:00–10/30 23:59、限量 2,000 名；每正卡戶上限 1,600 里）、JAL哩程儲蓄專案 30%（10/1–11/30）、洲際優悅會 50%（10/1–11/30）、法航荷航藍天飛行 20%（10/1–11/1）。長榮未參加。

Fixture 已 commit 在 `tests/fixtures/points_watch/`：`cub_list.json`、`cub_promo_page.json`、`cub_standing_page.json`。**不可修改這三個檔。**

## 檔案結構

| 檔案 | 動作 | 職責 |
|---|---|---|
| `points_watch/line.py` | 新增 | 點數類通知的 LINE 推送（新 bot 優先、舊 bot 後備） |
| `points_watch/alerts.py` | 新增 | 例外 → 告警文字；節流後送出告警（買點與 CUB 共用） |
| `points_watch/cub.py` | 新增 | 清單與活動頁解析、初篩（純函式） |
| `points_watch/cub_extract.py` | 新增 | Haiku 抽取與回應檢查 |
| `points_watch/cub_store.py` | 新增 | `cub_promos.json` 讀寫、內容比對、截止提醒判定 |
| `points_watch/cub_notify.py` | 新增 | ✈️ 與 ⏰ 訊息排版（純函式） |
| `points_watch/cub_run.py` | 新增 | CUB 這條線的流程 |
| `points_watch/main.py` | 修改 | 改用 `line`／`alerts`；拆出 `_run_buy`；串接 CUB；心跳 |
| `points_watch/notify.py` | 修改 | 心跳多一行 CUB 統計 |
| `.github/workflows/points-watch.yml` | 修改 | 多傳兩個 secret |

新狀態檔（Actions commit）：`points_watch/cub_seen.json`、`points_watch/cub_promos.json`。

所有指令在 repo 根目錄執行。macOS 沒有 `python`，一律 `python3`。

---

### Task 0（使用者操作，可與 Task 1–8 平行）：建立新的 LINE bot

**這一步只有使用者能做**（建立帳號、發行與貼上金鑰）。Task 10 之前完成即可；沒完成時程式會退回現有的 bot，通知不會中斷。

- [ ] **Step 1: 建立官方帳號並啟用 Messaging API**

到 LINE Official Account Manager（`https://manager.line.biz/`）建立一個新的官方帳號，名稱自訂（例「點數快報」）。進入該帳號的「設定 → Messaging API」，按「啟用 Messaging API」，**provider 選擇麻醉日報那支 bot 所在的同一個 provider**。選同一個 provider，你的 user ID 才會跟現有的相同，可以省掉重新查 ID。

（LINE 的後台介面時有調整；若選單位置不同，目標是「一個啟用了 Messaging API、且掛在原 provider 底下的新 channel」。）

- [ ] **Step 2: 發行 channel access token**

到 LINE Developers Console（`https://developers.line.biz/console/`）→ 該 provider → 新 channel →「Messaging API」分頁 → 最下方「Channel access token (long-lived)」→ Issue。

- [ ] **Step 3: 加好友**

同一頁上方有 QR code，用手機 LINE 掃描加這支新 bot 為好友。**沒加好友的話推播會回成功但收不到。**

- [ ] **Step 4: 把 token 存進 GitHub Secrets**

GitHub repo → Settings → Secrets and variables → Actions → New repository secret：

- Name：`POINTS_LINE_CHANNEL_ACCESS_TOKEN`
- Secret：Step 2 的 token

**不要截圖這個頁面，也不要把 token 貼到任何對話或檔案裡。**

`POINTS_LINE_USER_ID` 不必設：新 channel 與舊 channel 同一個 provider 時 user ID 相同，程式會自動沿用 `LINE_USER_ID`。只有在 Step 1 選了不同 provider 時才需要另外新增 `POINTS_LINE_USER_ID`（值在新 channel 的「Basic settings」分頁最下方「Your user ID」）。

---

### Task 1: LINE 分流與告警共用化

**Files:**
- Create: `points_watch/line.py`、`points_watch/alerts.py`
- Modify: `points_watch/main.py`、`.github/workflows/points-watch.yml`
- Test: `tests/test_points_line.py`、`tests/test_points_alerts.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/test_points_line.py`：

```python
"""點數通知的 LINE 推送：新 bot 優先、舊 bot 後備。"""
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import line  # noqa: E402


class _Resp:
    def __init__(self, status=200):
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(str(self.status))


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "token": headers["Authorization"], "to": json["to"],
                      "text": json["messages"][0]["text"]})
        return _Resp()

    monkeypatch.setattr(line.requests, "post", fake_post)
    for name in ("POINTS_LINE_CHANNEL_ACCESS_TOKEN", "POINTS_LINE_USER_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "old-token")
    monkeypatch.setenv("LINE_USER_ID", "Uold")
    return calls


def test_falls_back_to_existing_bot(sent):
    line.push_line("hi")
    assert sent == [{"url": "https://api.line.me/v2/bot/message/push",
                     "token": "Bearer old-token", "to": "Uold", "text": "hi"}]


def test_new_token_with_shared_user_id(sent, monkeypatch):
    # 新舊 channel 同一個 provider 時 user ID 相同，只需要設新 token
    monkeypatch.setenv("POINTS_LINE_CHANNEL_ACCESS_TOKEN", "new-token")
    line.push_line("hi")
    assert (sent[0]["token"], sent[0]["to"]) == ("Bearer new-token", "Uold")


def test_both_new(sent, monkeypatch):
    monkeypatch.setenv("POINTS_LINE_CHANNEL_ACCESS_TOKEN", "new-token")
    monkeypatch.setenv("POINTS_LINE_USER_ID", "Unew")
    line.push_line("hi")
    assert (sent[0]["token"], sent[0]["to"]) == ("Bearer new-token", "Unew")


def test_empty_secret_counts_as_unset(sent, monkeypatch):
    # GitHub Actions 對不存在的 secret 會傳空字串，不是不傳
    monkeypatch.setenv("POINTS_LINE_CHANNEL_ACCESS_TOKEN", "")
    monkeypatch.setenv("POINTS_LINE_USER_ID", "")
    line.push_line("hi")
    assert (sent[0]["token"], sent[0]["to"]) == ("Bearer old-token", "Uold")


def test_http_error_propagates(monkeypatch, sent):
    monkeypatch.setattr(line.requests, "post", lambda *a, **k: _Resp(500))
    with pytest.raises(requests.HTTPError):
        line.push_line("hi")
```

`tests/test_points_alerts.py`：

```python
"""告警文字與節流送出。"""
import json
import sys
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import alerts  # noqa: E402

TODAY = date(2026, 10, 9)


class _Plain(ValueError):
    pass


def test_reason_plain_types_use_their_message():
    assert alerts.reason(_Plain("RSS 無法解析"), plain=(_Plain,)) == "RSS 無法解析"


def test_reason_network():
    assert alerts.reason(requests.ConnectionError("boom")) == "連線失敗 ConnectionError"


def test_reason_anthropic_points_at_billing():
    err = type("APIStatusError", (Exception,), {"__module__": "anthropic._exceptions"})("x")
    assert alerts.reason(err).startswith("Anthropic API 問題（先查餘額與月上限）")


def test_reason_everything_else_is_a_code_bug():
    assert alerts.reason(KeyError("x")) == "程式錯誤（需改 code）KeyError"


def test_send_due_pushes_once_and_throttles(tmp_path):
    path = tmp_path / "alert_state.json"
    pushed = []
    failures = [("omaat", "連線失敗 ConnectionError")]
    assert alerts.send_due(failures, path, TODAY, pushed.append) == 1
    assert pushed[0].startswith("⚠️ 點數促銷監測異常")
    assert alerts.send_due(failures, path, date(2026, 10, 10), pushed.append) == 0
    assert len(pushed) == 1
    assert alerts.send_due(failures, path, date(2026, 10, 16), pushed.append) == 1


def test_send_due_keys_by_source_and_reason(tmp_path):
    path = tmp_path / "alert_state.json"
    pushed = []
    alerts.send_due([("a／抽取", "原因一"), ("a／抽取", "原因二")], path, TODAY, pushed.append)
    assert set(json.loads(path.read_text(encoding="utf-8"))) == {"a／抽取｜原因一", "a／抽取｜原因二"}
    assert alerts.send_due([("a／抽取", "原因一")], path, date(2026, 10, 10), pushed.append) == 0


def test_send_due_nothing_to_send_does_not_create_file(tmp_path):
    path = tmp_path / "alert_state.json"
    assert alerts.send_due([], path, TODAY, lambda t: None) == 0
    assert not path.exists()
```

- [ ] **Step 2: 確認測試失敗**

Run: `python3 -m pytest tests/test_points_line.py tests/test_points_alerts.py -v`
Expected: 兩個檔都在收集階段 `ImportError`

- [ ] **Step 3: 建立 `points_watch/line.py`**

```python
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
```

- [ ] **Step 4: 建立 `points_watch/alerts.py`**

```python
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
```

- [ ] **Step 5: 修改 `points_watch/main.py`**

(a) import 區塊，把

```python
from society_watch import fetch
from society_watch import state as sw_state
from society_watch.notify import push_line, split_message

from . import extract, feeds, notify, rating, store
```

換成

```python
from society_watch import fetch
from society_watch import state as sw_state
from society_watch.notify import split_message

from . import alerts, extract, feeds, notify, rating, store
from .line import push_line
```

(b) 把整個 `_reason` 函式（從 `def _reason(error: Exception) -> str:` 到它最後一個 `return`）換成

```python
def _reason(error: Exception) -> str:
    return alerts.reason(
        error, plain=(feeds.FeedError, extract.ExtractError, rating.SuspiciousPrice))
```

(c) 刪掉整個 `_alert_key` 函式（`def _alert_key(source: str, reason: str) -> str:` 與它的 `return` 一行，連同前後多出的空行）。

(d) 在 `run` 裡，把從 `    if failures:` 開始、到 `            print(f"已送出 {len(due)} 則告警。")` 為止的整段告警區塊（含上方那行 `# 告警先送：…` 註解）換成

```python
    # 告警先送：之後的推播若拋例外，當天的異常才不會跟著消失
    sent = alerts.send_due(failures, alerts_path, today, push_line)
    if sent:
        print(f"已送出 {sent} 則告警。")
```

`import requests` 在 `main.py` 不再被使用時一併移除（先 `grep -n "requests\." points_watch/main.py` 確認沒有其他用到的地方）。

- [ ] **Step 6: 修改 workflow**

在 `.github/workflows/points-watch.yml` 的 `Run points watch` 步驟，`LINE_USER_ID: ${{ secrets.LINE_USER_ID }}` 那一行下面加兩行（縮排對齊）：

```yaml
          POINTS_LINE_CHANNEL_ACCESS_TOKEN: ${{ secrets.POINTS_LINE_CHANNEL_ACCESS_TOKEN }}
          POINTS_LINE_USER_ID: ${{ secrets.POINTS_LINE_USER_ID }}
```

- [ ] **Step 7: 確認測試通過（含既有測試沒被改壞）**

Run: `python3 -m pytest tests/test_points_*.py tests/test_society_*.py -q`
Expected: 全部通過，0 failed。既有的 `tests/test_points_main.py` 不需要改任何一行——它 monkeypatch 的是 `main.push_line`，這個名稱仍在。

- [ ] **Step 8: Commit**

```bash
git add points_watch/line.py points_watch/alerts.py points_watch/main.py .github/workflows/points-watch.yml tests/test_points_line.py tests/test_points_alerts.py
git commit -m "feat(points-watch): 通知改走獨立 LINE bot（未設定時退回原 bot）；告警邏輯抽成共用"
```

---

### Task 2: 清單與活動頁解析

**Files:**
- Create: `points_watch/cub.py`
- Test: `tests/test_points_cub.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/test_points_cub.py`：

```python
"""國泰世華清單與活動頁解析。對 2026-10-09 實抓樣本。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import cub  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "points_watch"
PROMO_TITLE = "秋日遊-點數轉換指定航空里程/飯店積分限時加碼"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _promo():
    return next(c for c in cub.parse_list(_load("cub_list.json")) if c.title == PROMO_TITLE)


def test_list_count():
    assert len(cub.parse_list(_load("cub_list.json"))) == 149


def test_promo_campaign_fields():
    c = _promo()
    assert c.path == ("/content/cub-aem-cs/zh-tw/cathaybk/personal/event/overview/"
                      "credit-card/travel/202609/miles20251011.html")
    assert c.url == ("https://www.cathay-cube.com.tw/cathaybk/personal/event/overview/"
                     "credit-card/travel/202609/miles20251011")
    assert c.modified == "2026-09-18T08:58:04.436+00:00"
    assert c.key == c.path + "|2026-09-18T08:58:04.436+00:00"
    assert "最高加碼50%回饋無上限" in c.blurb
    assert cub.page_json_url(c) == c.url + ".model.json"


def test_candidates_are_exactly_the_three_known():
    titles = {c.title for c in cub.parse_list(_load("cub_list.json")) if cub.is_candidate(c)}
    assert titles == {
        PROMO_TITLE,
        "小樹點(信用卡)兌換航空里程/飯店積分｜國泰世華商業銀行",
        "PChome 24h購物2026/10_累積加碼活動",
    }


@pytest.mark.parametrize("text, message", [
    ("<!DOCTYPE html><html></html>", "活動清單不是 JSON"),
    ("[]", "活動清單為空或結構改變"),
    ('{"campaigns": []}', "活動清單為空或結構改變"),
    ('{"items": [{"campaignPath": "/a.html"}]}', "活動清單為空或結構改變"),
    # 有資料但欄位全改名：不可回空 list，那會跟「沒有活動」分不出來
    ('{"campaigns": [{"path": "/a.html", "props": {"title": "x"}}]}', "活動清單結構改變"),
])
def test_broken_list_raises(text, message):
    with pytest.raises(cub.CubError, match=message):
        cub.parse_list(text)


def test_items_missing_fields_are_skipped_when_others_are_fine():
    text = json.dumps({"campaigns": [
        {"campaignPath": "/content/cub-aem-cs/zh-tw/x/a.html", "campaignProps": {"jcr:title": "A"}},
        {"campaignPath": "/content/cub-aem-cs/zh-tw/x/b.html", "campaignProps": {}},
        {"campaignProps": {"jcr:title": "C"}},
        "garbage",
    ]})
    got = cub.parse_list(text)
    assert [(c.title, c.url, c.blurb, c.modified) for c in got] == [
        ("A", "https://www.cathay-cube.com.tw/x/a", "", "")]


def test_promo_page_text():
    text = cub.page_text(_load("cub_promo_page.json"))
    assert 2000 < len(text) < 6000
    for needle in ("亞洲萬里通", "JAL哩程儲蓄專案", "洲際優悅會", "法航荷航藍天飛行",
                   "加贈 30%", "登錄限量2,000名", "2026年10月28日16:00"):
        assert needle in text
    assert "<" not in text and "&nbsp;" not in text and "\xa0" not in text


def test_standing_page_text_has_no_bonus():
    text = cub.page_text(_load("cub_standing_page.json"))
    assert len(text) > 2000
    assert "加贈" not in text


@pytest.mark.parametrize("text, message", [
    ("<html>", "活動頁不是 JSON"),
    ('{"title": "x"}', "活動頁找不到內文"),
    ('{":items": {"m": {":type": "a/cub-main/v1/cub-main", "text": "太短"}}}', "活動頁內文過短"),
])
def test_broken_page_raises(text, message):
    with pytest.raises(cub.CubError, match=message):
        cub.page_text(text)
```

- [ ] **Step 2: 確認測試失敗**

Run: `python3 -m pytest tests/test_points_cub.py -v`
Expected: FAIL，`ImportError: cannot import name 'cub'`

- [ ] **Step 3: 實作**

`points_watch/cub.py`：

```python
"""國泰世華活動清單與活動頁的解析。純函式，不碰網路。

清單端點是活動專區的前端在載入時呼叫的，不是公開 API。改版時這裡的每個
失敗都必須是明確的例外——回空 list 會跟「今年沒辦活動」長得一樣。
"""
import html
import json
import re
from dataclasses import dataclass

LIST_URL = ("https://www.cathay-cube.com.tw/cathaybk/personal/event/overview/"
            "credit-card.model.list.json")
SITE = "https://www.cathay-cube.com.tw"
_CONTENT_PREFIX = "/content/cub-aem-cs/zh-tw"

MIN_PAGE_CHARS = 200
# 活動頁元件樹裡會放人看得到的文字的鍵名（2026-10-09 實測）
_TEXT_KEYS = ("text", "title", "content", "subTitle", "description")

# 初篩只求不漏：149 筆命中 3 筆，其中 1 筆是真的，其餘交給 Haiku 判否
_TOPIC = re.compile("里程|哩程|里數|哩數|積分")
_ACTION = re.compile("轉換|兌換|加碼|加贈")

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


class CubError(ValueError):
    """國泰世華這條線的資料異常。訊息會進告警與節流鍵，必須短而穩定。"""


@dataclass(frozen=True)
class Campaign:
    path: str       # campaignPath 原值
    url: str        # 公開網址
    title: str      # jcr:title
    blurb: str      # campaignTitle + campaignContent + subtitle
    modified: str   # cq:lastModified 原字串

    @property
    def key(self) -> str:
        """「判讀過」的鍵。含最後修改時間：銀行事後改了活動內容就會重新判讀。"""
        return f"{self.path}|{self.modified}"


def _clean(text: str) -> str:
    plain = html.unescape(_TAG.sub(" ", text)).replace("\xa0", " ")
    return _SPACE.sub(" ", plain).strip()


def public_url(path: str) -> str:
    if path.startswith(_CONTENT_PREFIX):
        path = path[len(_CONTENT_PREFIX):]
    if path.endswith(".html"):
        path = path[:-len(".html")]
    return SITE + path


def page_json_url(campaign: Campaign) -> str:
    return campaign.url + ".model.json"


def parse_list(text: str) -> list[Campaign]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise CubError("活動清單不是 JSON") from e
    items = data.get("campaigns") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise CubError("活動清單為空或結構改變")

    campaigns = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("campaignPath")
        props = item.get("campaignProps")
        if not isinstance(path, str) or not isinstance(props, dict):
            continue
        title = props.get("jcr:title")
        if not isinstance(title, str) or not title.strip():
            continue
        blurb = " ".join(
            _clean(props[k]) for k in ("campaignTitle", "campaignContent", "subtitle")
            if isinstance(props.get(k), str)
        )
        modified = props.get("cq:lastModified")
        campaigns.append(Campaign(
            path=path, url=public_url(path), title=_clean(title), blurb=blurb,
            modified=modified if isinstance(modified, str) else "",
        ))
    if not campaigns:
        raise CubError("活動清單結構改變")
    return campaigns


def is_candidate(campaign: Campaign) -> bool:
    blob = f"{campaign.title} {campaign.blurb}"
    return bool(_TOPIC.search(blob) and _ACTION.search(blob))


def _find_main(node):
    if isinstance(node, dict):
        if "cub-main" in str(node.get(":type", "")):
            return node
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        found = _find_main(child)
        if found is not None:
            return found
    return None


def _strings(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _TEXT_KEYS and isinstance(value, str):
                if value.strip():
                    yield _clean(value)
            else:
                yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def page_text(text: str) -> str:
    """活動頁的 .model.json → 內文純文字（依元件樹順序串接）。"""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise CubError("活動頁不是 JSON") from e
    main = _find_main(data)
    if main is None:
        raise CubError("活動頁找不到內文")
    plain = " ".join(s for s in _strings(main) if s)
    if len(plain) < MIN_PAGE_CHARS:
        raise CubError("活動頁內文過短")
    return plain
```

- [ ] **Step 4: 確認測試通過**

Run: `python3 -m pytest tests/test_points_cub.py -v`
Expected: 14 passed

若 `test_promo_page_text` 的某個 needle 不在取出的文字裡，**以 fixture 為準**：用 `python3 -c "from points_watch import cub; print(cub.page_text(open('tests/fixtures/points_watch/cub_promo_page.json', encoding='utf-8').read()))"` 看實際文字，把 needle 改成 fixture 裡確實存在的寫法（例如空白位置不同），並在回報中列出改了哪些。不可為了通過而刪掉該項檢查。

- [ ] **Step 5: Commit**

```bash
git add points_watch/cub.py tests/test_points_cub.py
git commit -m "feat(points-watch): 國泰世華活動清單與活動頁解析"
```

---

### Task 3: 促銷狀態、內容比對與截止提醒

**Files:**
- Create: `points_watch/cub_store.py`
- Test: `tests/test_points_cub_store.py`

夥伴在這一層之後一律以 dict 表示（就是存進 JSON 的樣子），排版與提醒都吃 dict。

- [ ] **Step 1: 寫失敗的測試**

`tests/test_points_cub_store.py`：

```python
"""cub_promos.json 讀寫、夥伴內容比對、截止提醒判定。"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import cub_store  # noqa: E402

TODAY = date(2026, 10, 9)


def _p(name="亞洲萬里通", end="2026-10-31", bonus="滿 2 萬里送 1,600", **over):
    d = {"name": name, "program": None, "bonus": bonus, "percent": 8,
         "start": "2026-10-01", "end": end, "registration": None, "cap": None}
    d.update(over)
    return d


def _entry(partners, reminded=()):
    return {"title": "T", "url": "https://x.test/a", "partners": partners,
            "first_seen": "2026-10-09", "reminded": list(reminded)}


def test_roundtrip(tmp_path):
    path = tmp_path / "cub_promos.json"
    promos = {"/p.html": cub_store.entry("T", "https://x.test/a", [_p()], TODAY)}
    cub_store.save(path, promos)
    assert cub_store.load(path) == promos
    assert promos["/p.html"]["first_seen"] == "2026-10-09"
    assert promos["/p.html"]["reminded"] == []
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_load_missing(tmp_path):
    assert cub_store.load(tmp_path / "nope.json") == {}


def test_same_content_ignores_order_and_cosmetic_fields():
    a = [_p("亞洲萬里通"), _p("JAL", end="2026-11-30")]
    b = [_p("JAL", end="2026-11-30", cap="無"), _p("亞洲萬里通", registration="要登錄")]
    assert cub_store.same_content(a, b)


@pytest.mark.parametrize("change", [
    {"bonus": "加贈 15%"}, {"end": "2026-11-15"}, {"start": "2026-10-05"}, {"name": "長榮航空"},
])
def test_content_differs(change):
    assert not cub_store.same_content([_p()], [_p(**change)])


def test_content_differs_when_partner_added():
    assert not cub_store.same_content([_p()], [_p(), _p("長榮航空")])


def test_same_content_tolerates_missing_dates():
    assert cub_store.same_content([_p(end=None)], [_p(end=None)])


@pytest.mark.parametrize("today, expect", [
    (date(2026, 10, 27), []),                 # 剩 4 天
    (date(2026, 10, 28), ["2026-10-31"]),     # 剩 3 天
    (date(2026, 10, 31), ["2026-10-31"]),     # 當天
    (date(2026, 11, 1), []),                  # 已過
])
def test_due_by_days_left(today, expect):
    groups = cub_store.due_groups(_entry([_p()]), today)
    assert [end.isoformat() for end, _ in groups] == expect


def test_partners_ending_same_day_are_grouped():
    e = _entry([_p("JAL", end="2026-11-30"), _p("洲際優悅會", end="2026-11-30"), _p()])
    groups = cub_store.due_groups(e, date(2026, 11, 28))
    assert len(groups) == 1
    assert [p["name"] for p in groups[0][1]] == ["JAL", "洲際優悅會"]


def test_two_end_dates_both_due_come_out_in_date_order():
    e = _entry([_p("藍天飛行", end="2026-11-01"), _p()])
    groups = cub_store.due_groups(e, date(2026, 10, 30))
    assert [end.isoformat() for end, _ in groups] == ["2026-10-31", "2026-11-01"]


def test_already_reminded_date_is_skipped():
    assert cub_store.due_groups(_entry([_p()], reminded=["2026-10-31"]), date(2026, 10, 29)) == []


def test_partner_without_end_date_never_reminds():
    assert cub_store.due_groups(_entry([_p(end=None)]), date(2026, 10, 29)) == []


def test_corrupt_entry_does_not_raise():
    # 這個檔 commit 進 public repo、可能被手改
    for bad in ("string", {}, {"partners": "x"}, {"partners": [{"end": "nope"}, "junk"]}):
        assert cub_store.due_groups(bad, TODAY) == []
```

- [ ] **Step 2: 確認測試失敗**

Run: `python3 -m pytest tests/test_points_cub_store.py -v`
Expected: FAIL，`ImportError: cannot import name 'cub_store'`

- [ ] **Step 3: 實作**

`points_watch/cub_store.py`：

```python
"""國泰世華轉點加碼的狀態（cub_promos.json）、內容比對、截止提醒判定。

檔案結構：{campaignPath: {"title", "url", "partners": [夥伴 dict],
                          "first_seen": ISO 日期, "reminded": [已提醒過的截止日]}}
"""
import json
from datetime import date
from pathlib import Path

from society_watch.state import _atomic_write

# 比買點的 2 天多一天：亞洲萬里通的轉換入帳要 3–14 個工作天，
# 而且登錄窗口可能只在截止前幾天才開（2026 年是 10/28–10/30）。
REMIND_DAYS = 3


def load(path: Path) -> dict[str, dict]:
    if not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def save(path: Path, promos: dict[str, dict]) -> None:
    _atomic_write(
        path, json.dumps(promos, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def entry(title: str, url: str, partners: list[dict], today: date,
          reminded: list[str] | None = None) -> dict:
    return {"title": title, "url": url, "partners": partners,
            "first_seen": today.isoformat(), "reminded": list(reminded or [])}


def _signature(partners: list[dict]) -> list[tuple[str, ...]]:
    # 只比「會改變使用者決定」的欄位。registration／cap 是 Haiku 摘出的一句話，
    # 兩次判讀的措辭可能不同，放進來會把同一份內容誤判成有更新。
    return sorted(
        tuple(str(p.get(k)) for k in ("name", "bonus", "start", "end"))
        for p in partners if isinstance(p, dict)
    )


def same_content(a: list[dict], b: list[dict]) -> bool:
    return _signature(a) == _signature(b)


def due_groups(entry_: dict, today: date) -> list[tuple[date, list[dict]]]:
    """回傳該提醒的（截止日, 那天到期的夥伴）清單，依日期排序。壞資料跳過不拋。"""
    if not isinstance(entry_, dict) or not isinstance(entry_.get("partners"), list):
        return []
    reminded = entry_.get("reminded")
    reminded = set(reminded) if isinstance(reminded, list) else set()

    by_end: dict[date, list[dict]] = {}
    for p in entry_["partners"]:
        if not isinstance(p, dict):
            continue
        try:
            end = date.fromisoformat(p.get("end") or "")
        except (TypeError, ValueError):
            continue
        if end.isoformat() in reminded or not 0 <= (end - today).days <= REMIND_DAYS:
            continue
        by_end.setdefault(end, []).append(p)
    return sorted(by_end.items())
```

- [ ] **Step 4: 確認測試通過**

Run: `python3 -m pytest tests/test_points_cub_store.py -v`
Expected: 18 passed

- [ ] **Step 5: Commit**

```bash
git add points_watch/cub_store.py tests/test_points_cub_store.py
git commit -m "feat(points-watch): 國泰世華加碼的狀態、內容比對與截止提醒判定"
```

---

### Task 4: 訊息排版

**Files:**
- Create: `points_watch/cub_notify.py`
- Test: `tests/test_points_cub_notify.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/test_points_cub_notify.py`：

```python
"""✈️ 活動訊息與 ⏰ 提醒訊息的排版。"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import cub_notify  # noqa: E402

TITLE = "秋日遊-點數轉換指定航空里程/飯店積分限時加碼"
URL = "https://www.cathay-cube.com.tw/cathaybk/personal/event/overview/credit-card/travel/202609/miles20251011"


def _p(name, percent, bonus, start="2026-10-01", end="2026-11-30", program=None,
       registration=None, cap=None):
    return {"name": name, "program": program, "bonus": bonus, "percent": percent,
            "start": start, "end": end, "registration": registration, "cap": cap}


ASIA = _p("亞洲萬里通", 8, "滿 1 萬里送 800、滿 2 萬里送 1,600", end="2026-10-31",
          program="ASIAMILES", registration="10/28 16:00–10/30 23:59，限量 2,000 名",
          cap="每正卡戶 1,600 里")
JAL = _p("JAL哩程儲蓄專案", 30, "每次轉換加贈 30%")
IHG = _p("洲際優悅會", 50, "每次轉換加贈 50%")
FB = _p("法航荷航藍天飛行", 20, "每次轉換加贈 20%", end="2026-11-01")


def test_full_campaign_message():
    # 傳入順序刻意打亂：排版要自己把亞萬排最前、其餘依幅度由高到低
    assert cub_notify.format_campaign(TITLE, URL, [JAL, FB, ASIA, IHG]) == "\n".join([
        "✈️ 國泰世華小樹點轉點加碼",
        TITLE,
        "",
        "⭐ 亞洲萬里通｜8%（⚪ 低於 10%）",
        "  滿 1 萬里送 800、滿 2 萬里送 1,600",
        "  10/1–10/31",
        "  需登錄：10/28 16:00–10/30 23:59，限量 2,000 名",
        "  上限：每正卡戶 1,600 里",
        "・洲際優悅會｜50%",
        "  10/1–11/30",
        "・JAL哩程儲蓄專案｜30%",
        "  10/1–11/30",
        "・法航荷航藍天飛行｜20%",
        "  10/1–11/1",
        "",
        "長榮：本次未參加",
        URL,
    ])


def test_updated_header():
    text = cub_notify.format_campaign(TITLE, URL, [IHG], updated=True)
    assert text.splitlines()[0] == "✈️ 國泰世華小樹點轉點加碼（內容更新）"


@pytest.mark.parametrize("percent, lamp", [
    (15, "🟢 15% 以上"), (20, "🟢 15% 以上"),
    (10, "🟡 10–14%"), (14, "🟡 10–14%"),
    (9, "⚪ 低於 10%"),
])
def test_lamp_for_starred(percent, lamp):
    eva = _p("長榮航空 無限萬哩遊", percent, f"每次轉換加贈 {percent}%", program="EVA")
    assert f"⭐ 長榮航空 無限萬哩遊｜{percent}%（{lamp}）" in cub_notify.format_campaign(TITLE, URL, [eva])


def test_starred_without_percent_has_no_lamp_and_shows_bonus():
    eva = _p("長榮航空", None, "加贈貴賓室券一張", program="EVA")
    lines = cub_notify.format_campaign(TITLE, URL, [eva]).splitlines()
    assert "⭐ 長榮航空" in lines
    assert "  加贈貴賓室券一張" in lines


def test_eva_sorted_before_asia_miles_and_no_footer_when_both_present():
    eva = _p("長榮航空", 15, "每次轉換加贈 15%", program="EVA")
    text = cub_notify.format_campaign(TITLE, URL, [IHG, ASIA, eva])
    assert text.index("⭐ 長榮航空") < text.index("⭐ 亞洲萬里通") < text.index("・洲際優悅會")
    assert "本次未參加" not in text


def test_footer_when_neither_present():
    assert "長榮、亞洲萬里通：本次未參加" in cub_notify.format_campaign(TITLE, URL, [IHG])


def test_footer_when_only_eva_present():
    eva = _p("長榮航空", 15, "每次轉換加贈 15%", program="EVA")
    assert "亞洲萬里通：本次未參加" in cub_notify.format_campaign(TITLE, URL, [eva])


def test_others_without_percent_go_last_and_show_bonus():
    odd = _p("某飯店", None, "滿額贈早餐券")
    lines = cub_notify.format_campaign(TITLE, URL, [odd, JAL]).splitlines()
    assert lines.index("・JAL哩程儲蓄專案｜30%") < lines.index("・某飯店")
    assert "  滿額贈早餐券" in lines


@pytest.mark.parametrize("start, end, shown", [
    ("2026-10-01", "2026-11-30", "  10/1–11/30"),
    (None, "2026-11-30", "  至 11/30"),
    ("2026-10-01", None, "  10/1 起"),
    (None, None, "  期間未註明"),
    ("garbage", "2026-11-30", "  至 11/30"),
])
def test_period_line(start, end, shown):
    p = _p("JAL", 30, "每次轉換加贈 30%", start=start, end=end)
    assert shown in cub_notify.format_campaign(TITLE, URL, [p]).splitlines()


def test_reminder():
    text = cub_notify.format_reminder(TITLE, URL, date(2026, 10, 31), [ASIA], date(2026, 10, 28))
    assert text == "\n".join([
        "⏰ 國泰世華轉點加碼即將截止",
        "10/31 截止（剩 3 天）",
        "",
        "⭐ 亞洲萬里通｜8%",
        "  滿 1 萬里送 800、滿 2 萬里送 1,600",
        "  需登錄：10/28 16:00–10/30 23:59，限量 2,000 名",
        "",
        URL,
    ])


def test_reminder_last_day_and_plain_partners():
    text = cub_notify.format_reminder(TITLE, URL, date(2026, 11, 30), [JAL, IHG], date(2026, 11, 30))
    assert "11/30 截止（今天截止）" in text
    assert "・洲際優悅會｜50%" in text and "・JAL哩程儲蓄專案｜30%" in text
    assert "需登錄" not in text
```

- [ ] **Step 2: 確認測試失敗**

Run: `python3 -m pytest tests/test_points_cub_notify.py -v`
Expected: FAIL，`ImportError: cannot import name 'cub_notify'`

- [ ] **Step 3: 實作**

`points_watch/cub_notify.py`：

```python
"""國泰世華轉點加碼的 LINE 訊息排版。純函式；夥伴一律是 cub_store 存的 dict。"""
from datetime import date

# 使用者原本想追的兩家：固定排最前、標 ⭐、給燈號。其餘夥伴只列事實不評等——
# 要評等就得假設小樹點一點值多少錢，那因人而異。
_STARRED = {"EVA": "長榮", "ASIAMILES": "亞洲萬里通"}
_STAR_ORDER = list(_STARRED)


def _lamp(percent: int) -> str:
    if percent >= 15:
        return "🟢 15% 以上"
    if percent >= 10:
        return "🟡 10–14%"
    return "⚪ 低於 10%"


def _md(text) -> str | None:
    try:
        d = date.fromisoformat(text or "")
    except (TypeError, ValueError):
        return None
    return f"{d.month}/{d.day}"


def _period(p: dict) -> str:
    start, end = _md(p.get("start")), _md(p.get("end"))
    if start and end:
        return f"{start}–{end}"
    if end:
        return f"至 {end}"
    if start:
        return f"{start} 起"
    return "期間未註明"


def _ordered(partners: list[dict]) -> list[dict]:
    def rank(p: dict):
        program = p.get("program")
        if program in _STARRED:
            return (0, _STAR_ORDER.index(program), 0)
        percent = p.get("percent")
        return (1, 0, -percent) if isinstance(percent, int) else (2, 0, 0)
    return sorted(partners, key=rank)    # 穩定排序：同分維持傳入順序


def _head(p: dict, with_lamp: bool) -> str:
    starred = p.get("program") in _STARRED
    line = f"{'⭐' if starred else '・'}{' ' if starred else ''}{p['name']}"
    percent = p.get("percent")
    if isinstance(percent, int):
        line += f"｜{percent}%"
        if starred and with_lamp:
            line += f"（{_lamp(percent)}）"
    return line


def _needs_bonus_line(p: dict) -> bool:
    # 「每次轉換加贈 30%」已經被標題行的「｜30%」說完了；
    # 「滿 1 萬里送 800」這種階梯式的才需要另起一行。
    percent = p.get("percent")
    return not (isinstance(percent, int) and f"{percent}%" in p["bonus"])


def _block(p: dict, with_lamp: bool, with_period: bool, with_cap: bool) -> list[str]:
    lines = [_head(p, with_lamp)]
    if _needs_bonus_line(p):
        lines.append(f"  {p['bonus']}")
    if with_period:
        lines.append(f"  {_period(p)}")
    if p.get("registration"):
        lines.append(f"  需登錄：{p['registration']}")
    if with_cap and p.get("cap"):
        lines.append(f"  上限：{p['cap']}")
    return lines


def format_campaign(title: str, url: str, partners: list[dict], updated: bool = False) -> str:
    lines = ["✈️ 國泰世華小樹點轉點加碼" + ("（內容更新）" if updated else ""), title, ""]
    for p in _ordered(partners):
        lines.extend(_block(p, with_lamp=True, with_period=True, with_cap=True))

    present = {p.get("program") for p in partners}
    missing = [label for code, label in _STARRED.items() if code not in present]
    lines.append("")
    if missing:
        lines.append(f"{'、'.join(missing)}：本次未參加")
    lines.append(url)
    return "\n".join(lines)


def format_reminder(title: str, url: str, end: date, partners: list[dict], today: date) -> str:
    left = (end - today).days
    when = "今天截止" if left == 0 else f"剩 {left} 天"
    lines = ["⏰ 國泰世華轉點加碼即將截止", f"{end.month}/{end.day} 截止（{when}）", ""]
    for p in _ordered(partners):
        lines.extend(_block(p, with_lamp=False, with_period=False, with_cap=False))
    lines.extend(["", url])
    return "\n".join(lines)
```

`format_reminder` 的 `title` 參數目前不顯示（訊息已夠短），保留是為了呼叫端介面與 `format_campaign` 一致。

- [ ] **Step 4: 確認測試通過**

Run: `python3 -m pytest tests/test_points_cub_notify.py -v`
Expected: 19 passed

- [ ] **Step 5: Commit**

```bash
git add points_watch/cub_notify.py tests/test_points_cub_notify.py
git commit -m "feat(points-watch): 國泰世華加碼與截止提醒的訊息排版"
```

---

### Task 5: Haiku 抽取

**Files:**
- Create: `points_watch/cub_extract.py`
- Test: `tests/test_points_cub_extract.py`

與 spec §3.1／§6 的一處差異：`program`（長榮／亞萬／其他）**不由 Haiku 填，改由程式從夥伴名稱判定**。這是確定性的字串比對，交給模型只會多一個出錯點（買點那邊就發生過模型回名稱而非代號）。

- [ ] **Step 1: 寫失敗的測試**

`tests/test_points_cub_extract.py`：

```python
"""國泰世華加碼的 Haiku 抽取。只測 prompt 組裝與回應解析，不打 API。"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import cub_extract  # noqa: E402
from points_watch.cub import Campaign, CubError  # noqa: E402

TODAY = date(2026, 10, 9)
CAMPAIGN = Campaign(path="/p.html", url="https://x.test/p", title="秋日遊轉點加碼",
                    blurb="最高加碼50%", modified="m1")
ASIA = {"name": "亞洲萬里通", "bonus": "滿 1 萬里送 800、滿 2 萬里送 1,600", "percent": 8,
        "start": "2026-10-01", "end": "2026-10-31",
        "registration": "10/28 16:00–10/30 23:59，限量 2,000 名", "cap": "每正卡戶 1,600 里"}
JAL = {"name": "JAL哩程儲蓄專案", "bonus": "每次轉換加贈 30%", "percent": 30,
       "start": "2026-10-01", "end": "2026-11-30", "registration": None, "cap": None}


def _parse(payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return cub_extract.parse_response(raw)


def _ok(*partners):
    return {"is_transfer_bonus": True, "partners": list(partners)}


def test_prompt_contains_title_text_and_today():
    prompt = cub_extract.build_prompt(CAMPAIGN, "活動內文在這裡", TODAY)
    assert "秋日遊轉點加碼" in prompt and "活動內文在這裡" in prompt and "2026-10-09" in prompt


def test_prompt_truncates_long_text():
    # 用一個 prompt 範本裡不會出現的字來數
    prompt = cub_extract.build_prompt(CAMPAIGN, "龘" * 20000, TODAY)
    assert prompt.count("龘") == cub_extract.TEXT_MAX


def test_not_a_transfer_bonus():
    assert _parse({"is_transfer_bonus": False}) is None


def test_two_partners():
    asia, jal = _parse(_ok(ASIA, JAL))
    assert (asia.name, asia.program, asia.percent) == ("亞洲萬里通", "ASIAMILES", 8)
    assert (asia.start, asia.end) == (date(2026, 10, 1), date(2026, 10, 31))
    assert asia.registration == "10/28 16:00–10/30 23:59，限量 2,000 名"
    assert asia.cap == "每正卡戶 1,600 里"
    assert (jal.program, jal.registration, jal.cap) == (None, None, None)


@pytest.mark.parametrize("name, program", [
    ("長榮航空", "EVA"), ("長榮航空 無限萬哩遊", "EVA"), ("EVA Air", "EVA"),
    ("亞洲萬里通", "ASIAMILES"), ("Asia Miles", "ASIAMILES"),
    ("洲際優悅會", None), ("法航荷航藍天飛行", None), ("PREVAIL Hotels", None),
])
def test_program_is_derived_from_name(name, program):
    assert _parse(_ok({**JAL, "name": name}))[0].program == program


def test_json_wrapped_in_fence():
    assert _parse("```json\n" + json.dumps(_ok(JAL), ensure_ascii=False) + "\n```")[0].name == "JAL哩程儲蓄專案"


def test_already_ended_partner_is_fine():
    # 活動進行到一半才被看到，個別夥伴已截止是正常的
    assert _parse(_ok({**JAL, "end": "2026-10-05"}))[0].end == date(2026, 10, 5)


def test_nulls_and_empty_strings_for_optional_fields():
    p = _parse(_ok({**JAL, "percent": None, "start": None, "end": None,
                    "registration": "", "cap": "  "}))[0]
    assert (p.percent, p.start, p.end, p.registration, p.cap) == (None, None, None, None, None)


@pytest.mark.parametrize("bad", [
    "抱歉，我無法判斷。",
    "{oops}",
    {"partners": [JAL]},                          # 缺 is_transfer_bonus
    {"is_transfer_bonus": True},                  # 缺 partners
    {"is_transfer_bonus": True, "partners": []},
    {"is_transfer_bonus": True, "partners": ["JAL"]},
    _ok({**JAL, "name": ""}),
    _ok({**JAL, "name": None}),
    _ok({**JAL, "bonus": " "}),
    _ok({**JAL, "percent": 0}),
    _ok({**JAL, "percent": 301}),
    _ok({**JAL, "percent": "30%"}),
    _ok({**JAL, "percent": True}),
    _ok({**JAL, "percent": 12.5}),
    _ok({**JAL, "end": "11/30"}),
    _ok({**JAL, "start": "2026-12-01", "end": "2026-11-30"}),
    _ok({**JAL, "registration": 5}),
])
def test_bad_response_raises(bad):
    # None 的語意是「模型判定不是加碼活動」。回應壞掉必須拋例外，
    # 兩者混在一起的話模型回垃圾會被當成「沒事」而整年漏報。
    with pytest.raises(CubError):
        _parse(bad)
```

- [ ] **Step 2: 確認測試失敗**

Run: `python3 -m pytest tests/test_points_cub_extract.py -v`
Expected: FAIL，`ImportError: cannot import name 'cub_extract'`

- [ ] **Step 3: 實作**

`points_watch/cub_extract.py`：

```python
"""Haiku 把國泰世華活動頁的內文抽成各夥伴的加贈內容。

回傳 None＝模型判定不是轉點加碼（正常，活動記為已判讀）。
拋 CubError＝回應壞掉或數值不合理（異常，不記為已判讀、隔天重試、送告警）。
"""
import json
import os
import re
from dataclasses import dataclass
from datetime import date

from anthropic import Anthropic

from society_watch.llm import MODEL

from .cub import Campaign, CubError

TEXT_MAX = 6000   # 2026 年的加碼頁約 3,000 字

PROMPT_TEMPLATE = """你是信用卡點數活動的資料抽取器。以下是國泰世華銀行一個活動頁的標題與內文。

判斷它是否為「小樹點(信用卡)轉換航空里程或飯店積分的限時加碼活動」——也就是在指定期間內轉換，
會比平常多拿到里程或積分。以下都不算（回 is_transfer_bonus=false）：
- 只列出常態兌換比率、沒有期間限定的額外加贈
- 刷卡消費回饋、累積消費加碼、抽獎、門票或行李運送優惠

今天是 {today}。
標題：{title}
內文：{text}

只輸出一個 JSON 物件，不要任何其他文字。
不是 → {{"is_transfer_bonus": false}}
是 → {{"is_transfer_bonus": true, "partners": [{{"name": "...", "bonus": "...", "percent": 0,
"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "registration": null, "cap": null}}]}}

每個有額外加贈的航空或飯店夥伴各一筆，欄位規則：
- name：頁面上的夥伴名稱，原文照抄（例「亞洲萬里通」「洲際優悅會」）。
- bonus：加贈內容，一句話，20 字以內（例「每次轉換加贈 30%」「滿 1 萬里送 800、滿 2 萬里送 1,600」）。
- percent：加贈百分比，整數。頁面寫百分比就照填；寫「滿 X 送 Y」時用 Y÷X×100 取整（滿 10,000 送 800 → 8）；無法換算填 null。
- start、end：該夥伴自己的加贈期間，只取日期不要時分；頁面沒寫填 null。
- registration：需要事先登錄時，寫出登錄期間與名額，一句話（例「10/28 16:00–10/30 23:59，限量 2,000 名」）；不需登錄填 null。
- cap：回饋上限，一句話（例「每正卡戶 1,600 里」）；寫明無上限或沒提到都填 null。
同一頁的抽獎活動不是夥伴，不要列。"""

_EVA = re.compile(r"長榮|\bEVA\b", re.I)
_ASIA = re.compile(r"亞洲萬里通|asia\s*miles", re.I)


@dataclass(frozen=True)
class Partner:
    name: str
    bonus: str
    percent: int | None
    start: date | None
    end: date | None
    registration: str | None
    cap: str | None

    @property
    def program(self) -> str | None:
        """長榮／亞萬／其他。由名稱判定，不問模型。"""
        if _EVA.search(self.name):
            return "EVA"
        if _ASIA.search(self.name):
            return "ASIAMILES"
        return None

    def as_dict(self) -> dict:
        return {
            "name": self.name, "program": self.program, "bonus": self.bonus,
            "percent": self.percent,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "registration": self.registration, "cap": self.cap,
        }


def build_prompt(campaign: Campaign, text: str, today: date) -> str:
    return PROMPT_TEMPLATE.format(
        today=today.isoformat(), title=campaign.title, text=text[:TEXT_MAX])


def _required(value, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CubError(f"加碼判讀：{what} 空白")
    return value.strip()


def _optional(value, what: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CubError(f"加碼判讀：{what} 不是文字")
    return value.strip() or None


def _day(value, what: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as e:
        raise CubError(f"加碼判讀：{what} 日期格式錯誤") from e


def _percent(value) -> int | None:
    if value is None:
        return None
    # bool 是 int 的子類別，要先排除
    if isinstance(value, bool) or not isinstance(value, int):
        raise CubError("加碼判讀：percent 不是整數")
    if not 1 <= value <= 300:
        raise CubError("加碼判讀：percent 超出合理範圍")
    return value


def _partner(item) -> Partner:
    if not isinstance(item, dict):
        raise CubError("加碼判讀：夥伴不是物件")
    start, end = _day(item.get("start"), "start"), _day(item.get("end"), "end")
    if start and end and end < start:
        raise CubError("加碼判讀：end 早於 start")
    return Partner(
        name=_required(item.get("name"), "name"),
        bonus=_required(item.get("bonus"), "bonus"),
        percent=_percent(item.get("percent")),
        start=start, end=end,
        registration=_optional(item.get("registration"), "registration"),
        cap=_optional(item.get("cap"), "cap"),
    )


def parse_response(raw: str) -> list[Partner] | None:
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise CubError("加碼判讀：Haiku 回應不含 JSON")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise CubError("加碼判讀：Haiku 回應無法解析為 JSON") from e
    if not isinstance(data, dict) or not isinstance(data.get("is_transfer_bonus"), bool):
        raise CubError("加碼判讀：缺少 is_transfer_bonus")
    if not data["is_transfer_bonus"]:
        return None
    partners = data.get("partners")
    if not isinstance(partners, list) or not partners:
        raise CubError("加碼判讀：partners 為空")
    return [_partner(item) for item in partners]


def extract(campaign: Campaign, text: str, today: date) -> list[Partner] | None:
    client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": build_prompt(campaign, text, today)}],
    )
    reply = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
    try:
        return parse_response(reply)
    except CubError:
        # 原始回應只印在 log，不放進例外訊息（訊息是告警節流鍵，必須穩定）
        print(f"    Haiku 原始回應：{reply!r}")
        raise
```

- [ ] **Step 4: 確認測試通過**

Run: `python3 -m pytest tests/test_points_cub_extract.py -v`
Expected: 32 passed

- [ ] **Step 5: Commit**

```bash
git add points_watch/cub_extract.py tests/test_points_cub_extract.py
git commit -m "feat(points-watch): 國泰世華加碼的 Haiku 抽取與回應檢查"
```

---

### Task 6: CUB 流程

**Files:**
- Create: `points_watch/cub_run.py`
- Test: `tests/test_points_cub_run.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/test_points_cub_run.py`：

```python
"""國泰世華這條線的流程。網路與 Haiku 以假函式取代，狀態寫到 tmp_path。"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import cub, cub_run  # noqa: E402
from points_watch.cub_extract import Partner  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "points_watch"
LIST_TEXT = (FIXTURES / "cub_list.json").read_text(encoding="utf-8")
PAGE_TEXT = (FIXTURES / "cub_promo_page.json").read_text(encoding="utf-8")
TODAY = date(2026, 10, 9)
PROMO_PATH = ("/content/cub-aem-cs/zh-tw/cathaybk/personal/event/overview/"
              "credit-card/travel/202609/miles20251011.html")
PROMO_MODIFIED = "2026-09-18T08:58:04.436+00:00"

ASIA = Partner(name="亞洲萬里通", bonus="滿 2 萬里送 1,600", percent=8,
               start=date(2026, 10, 1), end=date(2026, 10, 31),
               registration="10/28 16:00–10/30 23:59，限量 2,000 名", cap="每正卡戶 1,600 里")
IHG = Partner(name="洲際優悅會", bonus="每次轉換加贈 50%", percent=50,
              start=date(2026, 10, 1), end=date(2026, 11, 30), registration=None, cap=None)
EVA = Partner(name="長榮航空", bonus="每次轉換加贈 15%", percent=15,
              start=date(2026, 10, 20), end=date(2026, 11, 30), registration=None, cap=None)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """預設：清單回實抓樣本；三個候選頁都回加碼頁的 JSON；
    Haiku 只對標題含「秋日遊」的那筆回兩個夥伴，其餘判否。"""
    box = {"pushed": [], "list": LIST_TEXT, "partners": [ASIA, IHG], "judged": [],
           "fetch_error": None, "extract_error": None, "dir": tmp_path}

    def fake_get(url, **kw):
        if url == cub.LIST_URL:
            if isinstance(box["list"], Exception):
                raise box["list"]
            return box["list"]
        if box["fetch_error"]:
            raise box["fetch_error"]
        return PAGE_TEXT

    def fake_extract(campaign, text, today):
        box["judged"].append(campaign.title)
        if box["extract_error"]:
            raise box["extract_error"]
        return list(box["partners"]) if "秋日遊" in campaign.title else None

    monkeypatch.setattr(cub_run.fetch, "get", fake_get)
    monkeypatch.setattr(cub_run.cub_extract, "extract", fake_extract)
    return box


def _run(env, today=TODAY, dry_run=False):
    return cub_run.run(env["dir"], today, dry_run, env["pushed"].append)


def _json(env, name):
    return json.loads((env["dir"] / name).read_text(encoding="utf-8"))


def test_new_campaign_pushed_once_and_recorded(env):
    failures, stats = _run(env)
    assert failures == []
    assert stats == {"listed": 149, "matched": 3}
    assert len(env["judged"]) == 3
    assert len(env["pushed"]) == 1
    msg = env["pushed"][0]
    assert msg.startswith("✈️ 國泰世華小樹點轉點加碼\n秋日遊-點數轉換指定航空里程/飯店積分限時加碼")
    assert "⭐ 亞洲萬里通｜8%（⚪ 低於 10%）" in msg and "・洲際優悅會｜50%" in msg
    assert "長榮：本次未參加" in msg
    promos = _json(env, "cub_promos.json")
    assert list(promos) == [PROMO_PATH]
    assert [p["name"] for p in promos[PROMO_PATH]["partners"]] == ["亞洲萬里通", "洲際優悅會"]
    assert len(_json(env, "cub_seen.json")["seen"]) == 3


def test_second_run_is_silent_and_does_not_rejudge(env):
    _run(env)
    env["pushed"].clear(), env["judged"].clear()
    failures, _ = _run(env, date(2026, 10, 10))
    assert (failures, env["pushed"], env["judged"]) == ([], [], [])


def test_page_edited_but_same_partners_is_rejudged_not_repushed(env):
    _run(env)
    env["pushed"].clear(), env["judged"].clear()
    env["list"] = LIST_TEXT.replace(PROMO_MODIFIED, "2026-10-10T01:00:00.000+00:00")
    assert PROMO_MODIFIED not in env["list"]
    _run(env, date(2026, 10, 10))
    assert env["judged"] == ["秋日遊-點數轉換指定航空里程/飯店積分限時加碼"]
    assert env["pushed"] == []


def test_partner_added_later_pushes_an_update_and_keeps_reminder_history(env):
    _run(env)
    promos = _json(env, "cub_promos.json")
    promos[PROMO_PATH]["reminded"] = ["2026-10-31"]
    (env["dir"] / "cub_promos.json").write_text(json.dumps(promos, ensure_ascii=False), encoding="utf-8")
    env["pushed"].clear()
    env["list"] = LIST_TEXT.replace(PROMO_MODIFIED, "2026-10-12T01:00:00.000+00:00")
    env["partners"] = [ASIA, IHG, EVA]
    _run(env, date(2026, 10, 12))
    assert len(env["pushed"]) == 1
    assert env["pushed"][0].startswith("✈️ 國泰世華小樹點轉點加碼（內容更新）")
    assert "⭐ 長榮航空｜15%（🟢 15% 以上）" in env["pushed"][0]
    after = _json(env, "cub_promos.json")[PROMO_PATH]
    assert len(after["partners"]) == 3
    assert after["reminded"] == ["2026-10-31"]
    assert after["first_seen"] == "2026-10-09"


def test_list_fetch_failure_is_reported_not_raised(env):
    env["list"] = requests.ConnectionError("x")
    failures, stats = _run(env)
    assert failures == [("國泰世華／清單", "連線失敗 ConnectionError")]
    assert stats == {"listed": 0, "matched": 0}
    assert env["pushed"][0].startswith("⚠️ 點數促銷監測異常")


def test_list_structure_change_is_reported(env):
    env["list"] = '{"campaigns": []}'
    failures, _ = _run(env)
    assert failures == [("國泰世華／清單", "活動清單為空或結構改變")]


def test_judge_failure_alerts_and_retries_next_day(env):
    env["extract_error"] = cub.CubError("加碼判讀：Haiku 回應不含 JSON")
    failures, _ = _run(env)
    assert set(failures) == {("國泰世華／判讀", "加碼判讀：Haiku 回應不含 JSON")}
    alerts_sent = [m for m in env["pushed"] if m.startswith("⚠️")]
    assert len(alerts_sent) == 1
    assert alerts_sent[0].count("國泰世華／判讀") == 1     # 三篇同原因只列一行
    # 沒有任何新判讀結果就不寫檔，避免每天產生一個內容不變的 commit
    assert not (env["dir"] / "cub_seen.json").exists()
    env["extract_error"] = None
    env["pushed"].clear(), env["judged"].clear()
    _run(env, date(2026, 10, 10))
    assert len(env["judged"]) == 3
    assert len([m for m in env["pushed"] if m.startswith("✈️")]) == 1


def test_page_fetch_failure_is_a_judge_failure(env):
    env["fetch_error"] = requests.Timeout("x")
    failures, _ = _run(env)
    assert set(failures) == {("國泰世華／判讀", "連線失敗 Timeout")}
    assert env["judged"] == []


def test_push_failure_leaves_state_untouched(env):
    def boom(text):
        raise requests.HTTPError("500")
    with pytest.raises(requests.HTTPError):
        cub_run.run(env["dir"], TODAY, False, boom)
    assert not (env["dir"] / "cub_promos.json").exists()
    assert not (env["dir"] / "cub_seen.json").exists()


def test_dry_run_prints_and_writes_nothing(env, capsys):
    failures, stats = _run(env, dry_run=True)
    assert (failures, stats) == ([], {"listed": 149, "matched": 3})
    assert env["pushed"] == []
    assert "⭐ 亞洲萬里通｜8%" in capsys.readouterr().out
    assert list(env["dir"].iterdir()) == []


def test_dry_run_ignores_seen(env, capsys):
    _run(env)
    env["judged"].clear()
    _run(env, dry_run=True)
    assert len(env["judged"]) == 3


def test_reminder_three_days_before_each_end_date_once(env):
    _run(env)                                   # 亞萬 10/31、IHG 11/30
    env["pushed"].clear()
    _run(env, date(2026, 10, 27))
    assert env["pushed"] == []
    _run(env, date(2026, 10, 28))
    assert len(env["pushed"]) == 1
    assert env["pushed"][0].startswith("⏰ 國泰世華轉點加碼即將截止\n10/31 截止（剩 3 天）")
    assert "亞洲萬里通" in env["pushed"][0] and "洲際優悅會" not in env["pushed"][0]
    env["pushed"].clear()
    _run(env, date(2026, 10, 29))
    assert env["pushed"] == []
    _run(env, date(2026, 11, 27))
    assert len(env["pushed"]) == 1 and "洲際優悅會" in env["pushed"][0]
    assert _json(env, "cub_promos.json")[PROMO_PATH]["reminded"] == ["2026-10-31", "2026-11-30"]


def test_no_reminder_in_the_run_that_first_announces(env):
    _run(env, date(2026, 10, 29))               # 首見時亞萬只剩 2 天
    assert [m[:1] for m in env["pushed"]] == ["✈"]
    env["pushed"].clear()
    _run(env, date(2026, 10, 30))
    assert len(env["pushed"]) == 1 and env["pushed"][0].startswith("⏰")
```

- [ ] **Step 2: 確認測試失敗**

Run: `python3 -m pytest tests/test_points_cub_run.py -v`
Expected: FAIL，`ImportError: cannot import name 'cub_run'`

- [ ] **Step 3: 實作**

`points_watch/cub_run.py`：

```python
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

    if dry_run:
        print("\n===== dry-run：國泰世華會推播的內容 =====")
        print("\n\n".join(messages) if messages else "（沒有轉點加碼活動）")
        if failures:
            print("\n（失敗）" + "；".join(f"{s}：{r}" for s, r in failures))
        return failures, stats

    # 告警先送：之後的推播若拋例外，當天的異常才不會跟著消失
    # 去重後再送：三篇活動頁以同一個原因失敗時，告警只需要一行
    sent = alerts.send_due(list(dict.fromkeys(failures)), alerts_path, today, push)
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
        if path in pending:
            # 本輪才推出 ✈️ 的活動不在同一輪再提醒一次；明天仍在期限內會提醒
            continue
        for end, partners in cub_store.due_groups(entry, today):
            push(cub_notify.format_reminder(
                entry.get("title", ""), entry.get("url", ""), end, partners, today))
            entry.setdefault("reminded", []).append(end.isoformat())
            cub_store.save(promos_path, promos)
            print(f"已送出國泰世華截止提醒（{end}）。")

    return failures, stats
```

- [ ] **Step 4: 確認測試通過**

Run: `python3 -m pytest tests/test_points_cub_run.py -v`
Expected: 13 passed

- [ ] **Step 5: 確認沒有把狀態檔寫進 repo**

```bash
ls points_watch/ | grep -E "^cub_(seen|promos)\.json$" && echo "LEAK" || echo "clean"
```

Expected: `clean`

- [ ] **Step 6: Commit**

```bash
git add points_watch/cub_run.py tests/test_points_cub_run.py
git commit -m "feat(points-watch): 國泰世華轉點加碼的監測流程"
```

---

### Task 7: 併入主流程與心跳

**Files:**
- Modify: `points_watch/main.py`、`points_watch/notify.py`
- Modify: `tests/test_points_main.py`、`tests/test_points_notify.py`

- [ ] **Step 1: 先改測試（會失敗）**

(a) `tests/test_points_main.py` 的 `env` fixture 裡，在 `monkeypatch.setattr(main, "push_line", box["pushed"].append)` 這一行**下面**加：

```python
    # 國泰世華那條線預設關掉：fake_get 對任何網址都回 RSS，會被它當成壞掉的清單
    box["cub"] = lambda data_dir, today, dry_run, push: ([], {"listed": 0, "matched": 0})
    monkeypatch.setattr(main.cub_run, "run", lambda *a, **k: box["cub"](*a, **k))
```

(b) 在 `tests/test_points_main.py` 檔尾加：

```python


# ── 國泰世華那條線的串接 ──

def test_cub_runs_after_buy_flow_with_same_dir_and_push(env):
    seen = {}

    def fake_cub(data_dir, today, dry_run, push):
        seen.update(dir=data_dir, today=today, dry_run=dry_run,
                    buy_state_written=(data_dir / "seen_articles.json").exists())
        push("✈️ 假的加碼訊息")
        return [], {"listed": 149, "matched": 3}
    env["cub"] = fake_cub
    main.run(today=TODAY)
    assert seen == {"dir": env["dir"], "today": TODAY, "dry_run": False, "buy_state_written": True}
    assert "✈️ 假的加碼訊息" in env["pushed"]


def test_cub_crash_does_not_affect_buy_flow(env):
    def boom(*a, **k):
        raise RuntimeError("cub exploded")
    env["cub"] = boom
    failures = main.run(today=TODAY)
    assert failures == [("國泰世華／流程", "程式錯誤（需改 code）RuntimeError")]
    assert any(m.startswith("💰") for m in env["pushed"])
    assert "IHG|bonus|100|2026-10-31" in _json(env, "promos.json")
    assert any(m.startswith("⚠️") and "國泰世華／流程" in m for m in env["pushed"])
    assert not [m for m in env["pushed"] if m.startswith("💓")]


def test_cub_failures_are_returned_and_block_heartbeat(env):
    env["cub"] = lambda *a, **k: ([("國泰世華／清單", "活動清單為空或結構改變")],
                                  {"listed": 0, "matched": 0})
    failures = main.run(today=TODAY)
    assert ("國泰世華／清單", "活動清單為空或結構改變") in failures
    assert not [m for m in env["pushed"] if m.startswith("💓")]


def test_heartbeat_reports_cub_stats(env):
    env["cub"] = lambda *a, **k: ([], {"listed": 149, "matched": 3})
    main.run(today=TODAY)
    beat = next(m for m in env["pushed"] if m.startswith("💓"))
    assert "・國泰世華：清單 149 筆、初篩命中 3 筆" in beat


def test_bootstrap_skips_cub(env):
    called = []
    env["cub"] = lambda *a, **k: called.append(1) or ([], {})
    main.run(bootstrap=True, today=TODAY)
    assert called == []


def test_dry_run_passes_flag_to_cub_and_sends_nothing(env):
    flags = []
    env["cub"] = lambda data_dir, today, dry_run, push: (flags.append(dry_run), ([], {}))[1]
    main.run(dry_run=True, today=TODAY)
    assert flags == [True]
    assert env["pushed"] == []


def test_cli_exits_nonzero_on_cub_failure(env, monkeypatch):
    env["cub"] = lambda *a, **k: ([("國泰世華／判讀", "加碼判讀：partners 為空")], {})
    monkeypatch.setattr(sys, "argv", ["points_watch"])
    with pytest.raises(SystemExit) as e:
        main.main()
    assert e.value.code == 1
```

(c) 在 `tests/test_points_notify.py` 檔尾加：

```python


def test_heartbeat_with_cub_line():
    text = notify.format_heartbeat(feed_count=3, article_count=42, promo_count=7,
                                   cub_listed=149, cub_matched=3)
    assert "・國泰世華：清單 149 筆、初篩命中 3 筆" in text.splitlines()


def test_heartbeat_without_cub_stats_has_no_cub_line():
    assert "國泰世華" not in notify.format_heartbeat(feed_count=3, article_count=42, promo_count=7)
```

- [ ] **Step 2: 確認新測試失敗**

Run: `python3 -m pytest tests/test_points_main.py tests/test_points_notify.py -q`
Expected: `AttributeError: module 'points_watch.main' has no attribute 'cub_run'`（fixture 階段），notify 的新測試 `TypeError: format_heartbeat() got an unexpected keyword argument 'cub_listed'`

- [ ] **Step 3: 修改 `points_watch/notify.py`**

把整個 `format_heartbeat` 函式換成：

```python
def format_heartbeat(feed_count: int, article_count: int, promo_count: int,
                     cub_listed: int | None = None, cub_matched: int | None = None) -> str:
    lines = [
        "💓 點數促銷監測運作正常",
        "",
        f"・監測來源：{feed_count} 個 RSS",
        f"・已判讀文章：{article_count} 篇",
        f"・已記錄促銷：{promo_count} 筆",
    ]
    if cub_listed is not None:
        # 初篩命中數長期為 0 是唯一看得出「銀行改了措辭、初篩漏掉」的地方
        lines.append(f"・國泰世華：清單 {cub_listed} 筆、初篩命中 {cub_matched} 筆")
    lines.extend([
        "",
        "（每週一則。若某一週沒收到，表示監測可能已停擺，請查看 GitHub Actions。）",
    ])
    return "\n".join(lines)
```

- [ ] **Step 4: 修改 `points_watch/main.py`**

(a) import：把 `from . import alerts, extract, feeds, notify, rating, store` 換成

```python
from . import alerts, cub_run, extract, feeds, notify, rating, store
```

(b) 把買點流程改名並調整簽名。把

```python
def run(bootstrap: bool = False, dry_run: bool = False,
        pages: int = DEFAULT_PAGES, today: date | None = None) -> list[tuple[str, str]]:
    today = today or date.today()
    seen_path = DATA_DIR / "seen_articles.json"
```

換成

```python
def _run_buy(bootstrap: bool, dry_run: bool, pages: int,
             today: date) -> tuple[list[tuple[str, str]], dict | None]:
    """買點／買哩程這條線。回傳（失敗清單, 心跳用的統計）；
    bootstrap 與 dry-run 不產生統計，回 None。"""
    seen_path = DATA_DIR / "seen_articles.json"
```

(c) 同一函式內刪掉這一行（心跳搬到外層後用不到）：

```python
    heartbeat_path = DATA_DIR / "heartbeat.json"
```

(d) bootstrap 分支的 `return failures` 改成 `return failures, None`；dry-run 分支（`if dry_run:` 區塊結尾）的 `return failures` 也改成 `return failures, None`。

(e) 把函式結尾從 `    # 有任何失敗的那一輪不送「運作正常」…` 這行註解開始、到 `    return failures` 為止（整個心跳區塊加最後的 return）換成

```python
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
            alerts.send_due([failure], DATA_DIR / "alert_state.json", today, push_line)
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
```

(f) `main()` 裡，把

```python
    if any(source.endswith("／抽取") for source, _ in failures):
        print("❌ 有文章判讀失敗，以非零狀態結束。")
        raise SystemExit(1)
```

換成

```python
    if any(source.endswith("／抽取") or source.startswith("國泰世華")
           for source, _ in failures):
        print("❌ 有判讀或國泰世華來源失敗，以非零狀態結束。")
        raise SystemExit(1)
```

(g) 檔案最上方 docstring 的用法說明下面加一行：

```
同一次執行會先跑買點促銷，再跑國泰世華小樹點轉點加碼（cub_run），最後才是每週心跳。
```

- [ ] **Step 5: 確認全部測試通過**

Run: `python3 -m pytest tests/test_points_*.py tests/test_society_*.py -q`
Expected: 全部通過，0 failed

- [ ] **Step 6: 確認沒有把狀態檔寫進 repo**

```bash
git status --short points_watch/
```

Expected：只有 `main.py`、`notify.py` 兩個 `M`，沒有新出現的 `.json`。

- [ ] **Step 7: Commit 並 push**

```bash
git add points_watch/main.py points_watch/notify.py tests/test_points_main.py tests/test_points_notify.py
git commit -m "feat(points-watch): 國泰世華轉點加碼併入主流程與每週心跳"
git push || (git pull --no-rebase --no-edit origin main && git push)
```

工作區有使用者未提交的檔案，撞到遠端的狀態 commit 時用 merge，不要 rebase 或 stash。

---

### Task 8: dry-run 驗收（使用者檢查點）

**Files:** 無

**CLAUDE.md「先做一個單位停下來驗收」的檢查點。使用者確認前不做 Task 9。**

- [ ] **Step 1: 在 Actions 跑 dry-run**

```bash
gh workflow run points-watch.yml -f mode=dry-run -f pages=2
sleep 10
ID=$(gh run list --workflow=points-watch.yml --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$ID" --exit-status; echo "exit=$?"
gh run view "$ID" --log | grep "Run points watch" | sed -E 's/^.*Z //' | sed -n '/執行日期/,$p'
```

Expected：`國泰世華清單 149 筆左右，初篩命中 3 筆`；三筆各有 `→` 結果，其中「秋日遊」為「新活動，4 個夥伴」，另兩筆「不是轉點加碼」；`===== dry-run：國泰世華會推播的內容 =====` 之後是一則完整的 ✈️ 訊息。

- [ ] **Step 2: 與官方頁面逐項對照**

開啟 `https://www.cathay-cube.com.tw/cathaybk/personal/event/overview/credit-card/travel/202609/miles20251011`，對 ✈️ 訊息裡每個夥伴核對：名稱、加贈幅度、起訖日、登錄期間與名額、上限。預期值見本計畫開頭「已實抓驗證的事實」第 6 點。整理成對照表。

- [ ] **Step 3: 回報使用者並等待確認**

貼出完整的 ✈️ 訊息與對照表。若抽取有誤，修正 `cub_extract.PROMPT_TEMPLATE` 後重跑本任務；若初篩漏掉或誤放，修正 `cub.py` 的 `_TOPIC`／`_ACTION` 並補測試。**使用者確認後才繼續。**

---

### Task 9: 上線

**Files:** 無程式變更

- [ ] **Step 1: 確認新 bot 是否就緒**

詢問使用者 Task 0 是否完成（`POINTS_LINE_CHANNEL_ACCESS_TOKEN` 已存入 GitHub Secrets、已加新 bot 為好友）。

- 已完成 → 繼續 Step 2，✈️ 會落在新聊天室。
- 尚未完成 → 告知使用者：現在執行的話 ✈️ 會推到原本的聊天室。由使用者決定要先等、還是先上線之後再切換。

- [ ] **Step 2: 手動跑一次日常模式**

```bash
gh workflow run points-watch.yml -f mode=normal -f pages=2
sleep 10
ID=$(gh run list --workflow=points-watch.yml --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$ID" --exit-status; echo "exit=$?"
gh run view "$ID" --log | grep -E "Run points watch|Commit state" | sed -E 's/^.*Z //' | grep -E "✅|❌|判讀|→|推播|告警|提醒|心跳|main -> main"
git pull --no-rebase --no-edit origin main
python3 -c "import json; d=json.load(open('points_watch/cub_promos.json')); print(list(d)); print(len(json.load(open('points_watch/cub_seen.json'))['seen']))"
```

Expected：run 成功；`cub_promos.json` 有一個鍵（秋日遊那頁的路徑）；`cub_seen.json` 有 3 筆。

- [ ] **Step 3: 請使用者確認 LINE**

請使用者確認：(1) 收到 ✈️ 訊息；(2) 它出現在哪一個聊天室（新 bot 或原 bot），是否符合預期。LINE 回 200 不代表送達，只能靠人看。若設了新 token 卻什麼都沒收到，最可能是沒加新 bot 為好友，或新 channel 建在不同 provider（此時需另設 `POINTS_LINE_USER_ID`）。

- [ ] **Step 4: 更新規格狀態與記憶**

- `docs/superpowers/specs/2026-10-09-cub-transfer-bonus-watch-design.md` 第 4 行狀態改為「2026-10-09 已上線」，並在 §3.1 註明 `program` 改由程式從名稱判定。
- `docs/superpowers/specs/2026-10-09-points-promo-watch-design.md` 狀態行的「`CUB` 待另案」改為「`CUB` 見 `2026-10-09-cub-transfer-bonus-watch-design.md`（已上線）」。
- 更新記憶檔 `project_points_watch.md` 與 `MEMORY.md` 的索引行：國泰世華已上線（清單端點、初篩盲點、`path|lastModified` 鍵、各截止日前 3 天提醒）；點數通知走獨立 bot（`POINTS_LINE_*`，未設定時退回原 bot）。

```bash
git add docs/superpowers/specs/
git commit -m "docs: 國泰世華轉點加碼監測上線，更新規格狀態"
git push || (git pull --no-rebase --no-edit origin main && git push)
```

---

## Self-Review 紀錄

**Spec 覆蓋：** §2 資料來源→Task 2；§3 架構與兩條線隔離→Task 6、7；§3.1 資料結構→Task 2（Campaign）、5（Partner）、3（存檔格式）；§4 流程 1–6→Task 6；§5 兩則訊息→Task 4；§6 抽取與回應檢查→Task 5；§7 錯誤處理→Task 2（CubError）、5、6、7（`main` 接住例外、非零結束）；§7 心跳顯示初篩命中數→Task 7；§8 測試→各任務；§9 上線→Task 8、9。通知分流（使用者 2026-10-09 追加）→Task 0、1。

**與 spec 的差異：** `program` 由程式從名稱判定而非 Haiku 填（Task 5 說明，Task 9 回寫 spec）；模組多了 `line.py`、`alerts.py`（分流與共用告警）。

**型別一致性：** `cub_run.run(data_dir, today, dry_run, push) -> (failures, stats)` 在 Task 6 定義、Task 7 的 `_run_cub` 與測試 fixture 以相同簽名呼叫；`Partner.as_dict()`（Task 5）產生的鍵與 `cub_store`（Task 3）、`cub_notify`（Task 4）讀取的鍵相同：`name, program, bonus, percent, start, end, registration, cap`；`cub_store.entry(title, url, partners, today, reminded=None)` 在 Task 3 定義、Task 6 呼叫。
