# 麻醉科日報異常告警 — 設計

日期：2026-10-05

## 1. 目的

日報 pipeline（`daily_fetch_classify.py` 週一抓取分類、`daily_push.py` 週一至週五推播）
故障時，以 LINE 通知使用者個人。比照 `society_watch` 的 ⚠️ 監測異常機制。

範圍是「停擺＋靜默降級」。候選池見底（當日無文章、最高分低於門檻只推精簡清單）
屬於內容品質而非故障，不告警。日報每個工作天都會到群組，本身就是心跳，不另做心跳。

## 2. 動機：最近四週 Actions log 裡實際發生、但沒有任何通知的事

| 日期 | 事件 | 當時的訊號 |
|---|---|---|
| 09-14、09-21、09-28 | NEJM RSS 連續三週回 0 篇 | 無（綠燈） |
| 09-21 | 分類階段 `TypeError`（Haiku 把索引回成字串），`week.json` 整週沒更新，日報推了一週舊文章 | 只有 Actions 紅燈 |
| 10-05 | Anesth Analg 查到 30 個 PMID，解析後 0 篇 | 無（綠燈） |

## 3. 架構

新增根目錄模組 `digest_alert.py`，兩支日報腳本只負責收集失敗，其餘交給它：

```
daily_fetch_classify.py ─┐
                         ├─ failures: list[(key, reason)] ─→ digest_alert.report(stage, failures)
daily_push.py ───────────┘                                      │
                                                                ├─ society_watch.state.should_alert / record_alert（節流）
                                                                ├─ society_watch.notify.push_line（推給 LINE_USER_ID）
                                                                └─ daily_data/alert_state.json（Contents API 寫回）
```

- 節流與推播直接 import `society_watch.state`、`society_watch.notify`，不複製、不改動
  學會監測。這兩個模組只依賴 `requests` 與標準函式庫，日報 workflow 不需加裝套件
  （寫計畫時要實際 import 驗證）。
- `digest_alert.py` 自己的函式：
  - `reason(error) -> str`：例外轉告警文字，見 §5
  - `is_stale(fetched_at, now) -> bool`：`week.json` 過期判定
  - `format_alert(stage, failures) -> str`：組訊息
  - `report(stage, failures) -> None`：節流、推播、寫狀態；**任何例外都只印 log 不外拋**
- 不 import `society_watch.main._reason`：那會連帶載入 `extract`（需要 bs4）。

## 4. 判定條件

### 週一抓取（`daily_fetch_classify.py`）

| 觸發條件 | key | reason |
|---|---|---|
| 單一期刊抓取拋例外 | 期刊名 | `reason(e)` |
| 期刊回 0 篇且無例外 | 期刊名 | `回 0 篇，疑似 feed 改版或解析失效` |
| 分類批次回應找不到 JSON（現在整批靜默丟掉） | `分類` | `模型回應無法解析，整批文章被略過` |
| 全部來源合計 0 篇 | `週一抓取` | `所有來源合計 0 篇，week.json 未更新` |
| 低於 `MIN_ARTICLES` 且有來源失敗 | `週一抓取` | `文章數過低，week.json 未更新` |
| 其他未處理例外（分類、上傳） | `週一抓取` | `reason(e)` |

行為變更：全部 0 篇目前是 `return`（綠燈），改為非零結束。

「回 0 篇」套用於全部 15 個來源。最近四週的 log 裡，正常的期刊最少也有 2 篇，
出現 0 的兩例（NEJM、Anesth Analg）都是異常，沒有觀察到合理的 0。

### 每日推播（`daily_push.py`）

| 觸發條件 | key | reason |
|---|---|---|
| `week.json` 的 `fetched_at` 距今超過 7.5 天，或欄位缺失／無法解析 | `week.json` | `已 N 天未更新，週一抓取可能失敗` |
| Sonnet 格式化失敗，退回純文字清單 | `日報格式化` | `reason(e)` |
| 心情小語 API 失敗，退回本地語錄 | `心情小語` | `reason(e)` |
| PMCID 查詢整批失敗 | `全文補抓` | `reason(e)` |
| 其他未處理例外（讀檔、LINE 推播、`sent_articles` 寫入） | `每日推播` | `reason(e)` |

- 過期判定用 `fetched_at` 天數而非比對週次：兩個 workflow 的排程實際都延遲約五小時
  （抓取 13:11–14:11、推播 14:00–15:00 台灣時間），週一推播與抓取的先後只差三四十分鐘，
  比對週次會在抓取稍慢的週一誤報。7.5 天的門檻在週一不會響，週二起才響。
- 單篇 PMC 全文抓不到不告警（實測本來只有約 1/5 拿得到）。
- 週末不推播的提早 return 不經過告警流程。

## 5. reason 字串

同時是節流 key，必須短而穩定，不含每次會變的數字（天數 N 例外，見 §6）。

| 例外類型 | 格式 |
|---|---|
| `requests.RequestException` | `{類別名}: {訊息前 80 字}` |
| 模組名以 `anthropic` 開頭 | `Anthropic API 問題（先查餘額與月上限）{類別名}: {訊息前 80 字}` |
| `SystemExit` | 其訊息前 80 字 |
| 其他 | `程式錯誤（需改 code）{類別名}: {訊息前 80 字}` |

## 6. 節流與狀態

- 沿用 `society_watch.state.should_alert`：同 key 同 reason 7 天最多一次，
  換一種 reason 立刻再報；狀態檔壞掉一律 fail-open。
- `week.json` 過期的 reason 會帶天數，為避免每天都被視為新 reason，
  節流用的 reason 固定為 `已超過 7 天未更新，週一抓取可能失敗`，天數只放在訊息內文。
- 狀態檔 `daily_data/alert_state.json`，格式與學會監測的 `alert_state.json` 相同。
  在 Actions 上用 GitHub Contents API 讀寫（與 `sent_articles.json` 同一條路）；
  本機執行只寫本機檔。
- 讀狀態也走 Contents API 而非磁碟：抓取 workflow 沒有 `git pull` 步驟，
  checkout 之後別的 workflow 寫入的狀態在磁碟上看不到。

## 7. 流程

兩支腳本的 `main()` 改成：

```python
def main():
    failures = []
    try:
        run(failures)
    except BaseException as e:      # 含 SystemExit
        failures.append((STAGE, digest_alert.reason(e)))
        raise                        # 保留 Actions 紅燈
    finally:
        digest_alert.report(STAGE, failures)
```

- 原本 `main()` 的內容搬進 `run(failures)`，各降級點在既有的 `except`／`print`
  旁邊加一行 `failures.append(...)`。
- 日報先推給群組，告警在 `finally` 後送：告警失敗不影響日報。
- `KeyboardInterrupt` 不記為失敗。

## 8. 訊息格式

收件人：使用者個人（`LINE_USER_ID`，與學會監測共用）。不送進日報群組。

```
⚠️ 麻醉日報異常（每日推播）

・日報格式化：Anthropic API 問題（先查餘額與月上限）...
・week.json：已 9 天未更新，週一抓取可能失敗

詳情見 GitHub Actions log。
```

## 9. Workflow 變更

- `daily-fetch-classify.yml`、`daily-push.yml` 的 env 各加 `LINE_USER_ID`；
  抓取 workflow 另加 `LINE_CHANNEL_ACCESS_TOKEN`（目前沒有）。
- 兩個 workflow 加 `PYTHONUNBUFFERED: "1"`（9/21 的 log 裡 traceback 排在正常輸出前面，
  就是 stdout 被緩衝造成的）。
- `daily-push.yml` 加 `workflow_dispatch` 輸入 `test_alert`：填 `true` 時只送一則
  測試告警後結束，不推日報、不經節流、不寫狀態。

## 10. 已知限制

- `LINE_CHANNEL_ACCESS_TOKEN` 失效時告警也送不出去，只剩 Actions 紅燈。
- LINE 回 200 不代表送達。`test_alert` 是唯一能確認收得到的方法，部署後必須跑一次。
- checkout、pip install 等 Python 啟動前的失敗抓不到（GitHub 會寄信）。
- 排程本身沒被觸發時不會有告警；此時日報沒到群組即是訊號。

## 11. 不在範圍內

- 修掉 9/21 那個 `TypeError` 本身（`classify_articles` 對模型回傳的索引沒轉型）。
  本設計只保證它再發生時會收到告警。
- 日報整理模型維持 `claude-sonnet-5`。
- `weekly_digest.py`（已停用）。

## 12. 測試

`tests/test_digest_alert.py`，不打網路：

- `reason()`：四類例外各一，訊息截斷至 80 字、換行被壓掉
- `is_stale()`：7 天整不過期、8 天過期、欄位缺失與格式錯誤視為過期
- `report()`：空 failures 不推播；冷卻期內不重複推；換 reason 立刻推；
  推播拋例外時不外拋且不寫狀態；狀態讀取失敗時 fail-open 照推
- `format_alert()`：標題含階段名、每筆一行

兩支日報腳本在 import 時就會讀環境變數並建立 Anthropic client，不直接 import 測試；
可測邏輯都放在 `digest_alert.py`。

## 13. 實作順序與驗收

1. `digest_alert.py`＋測試
2. 接進 `daily_push.py` 與 `daily-push.yml` → **停下來驗收**：
   使用者手動觸發 `test_alert=true`，確認 LINE 收到；再用 `force_weekday` 跑一次確認日報照常
3. 驗收通過後接進 `daily_fetch_classify.py` 與 `daily-fetch-classify.yml`，手動觸發一次確認
4. 更新記憶 `project_anesthesia_digest.md`
