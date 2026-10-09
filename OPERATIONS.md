# 維運說明（自動推播系統）

這份文件給「接手的人」看：包含誰維護、出事找誰、怎麼判斷壞在哪、怎麼手動補救。
涵蓋 repo 內三套排程系統：麻醉科日報、學會活動監測、點數促銷監測。

- **維護人**：王英瑜（GitHub [@Jennawang123](https://github.com/Jennawang123)）
- **回報窗口**：在本 repo 開 issue → <https://github.com/Jennawang123/anesthesia-digest-bot/issues>
- **版本**：以 git commit 為準，無額外版號；本文件有變更一併 commit
- **憑證**：全部放 GitHub Secrets，repo 內不得出現任何金鑰、token、使用者 ID 或群組 ID 的值

---

## 一、麻醉科日報

| 項目 | 內容 |
|---|---|
| 觸發 | `.github/workflows/daily-fetch-classify.yml`：每週一 08:45 台灣時間（cron `45 0 * * 1`）<br>`.github/workflows/daily-push.yml`：週一至週五 09:05 台灣時間（cron `5 1 * * 1-5`） |
| 程式 | `daily_fetch_classify.py`（抓取、分類評分、熱點偵測）→ `daily_push.py`（當日選文、格式化、推 LINE 群組） |
| 資料來源 | PubMed E-utilities（依 ISSN 查六本期刊）＋ BJA 的 ScienceDirect RSS ＋ NEJM／JAMA 官方 RSS |
| 狀態檔 | `daily_data/week.json`（當週分類結果，由 GitHub Contents API 寫入，不走 git push）<br>`daily_data/sent_articles.json`（已推播文章，防止跨日重複） |
| 需要的 Secrets（名稱） | `CLAUDE_API_KEY`、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_GROUP_ID` |
| 驗收條件 | 工作日 09:05 之後 LINE 群組收到當日主題日報；3 至 5 篇；同一篇不重複出現；每本期刊最多 2 篇；訊息未被截斷（過長會自動分則接力） |
| 手動補救 | Actions →「麻醉科日報 - 每日推送」→ Run workflow，`force_weekday` 填 1 至 5 指定主題；若 `week.json` 是舊的，先跑「週一抓取分類」 |

**壞掉先查哪裡（依序）**

1. **Actions 執行紀錄**：Actions 頁看最近一次是紅燈還是根本沒觸發。
2. **Anthropic 餘額與月上限**：AI 功能突然全壞，先看這裡再看程式碼。帳戶設有每月上限，餘額用盡與撞到月上限的症狀相同，在 Anthropic Console 的 Billing 頁可以分辨。
3. **LINE 推播**：LINE 回應 HTTP 200 不代表訊息真的送達（被封鎖或 ID 錯一樣回 200）。Actions 綠燈但手機沒收到，要往這個方向查。
4. **沒有失敗通知**：這套目前不會主動告警，發現方式是「某天沒收到日報」。

---

## 二、學會活動監測

| 項目 | 內容 |
|---|---|
| 觸發 | `.github/workflows/society-watch.yml`：每天 10:00 台灣時間（cron `0 2 * * *`，Actions 排程常延遲數十分鐘） |
| 程式 | `python3 -m society_watch.main`（`--bootstrap` 為首次執行模式：只建狀態檔、不推播） |
| 資料來源 | 6 個學會＋1 個年會共 8 個設定，逐站設定在 `society_watch/sources.py`；其中呼吸道處理醫學會是整頁文字比對＋LLM 抽取，是唯一會花 API 額度的來源 |
| 狀態檔 | `society_watch/seen.json`（已通知項目，只增不減）、`snapshot_airway.txt`、`alert_state.json`（告警節流）、`heartbeat.json`（心跳週次）。四個都由 Actions 自動 commit 回 repo |
| 需要的 Secrets（名稱） | `CLAUDE_API_KEY`、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_USER_ID`（取自日報那支 bot 的 channel；userId 綁 channel，不同 bot 不通用） |
| 驗收條件 | 每週收到一則 💓 心跳；有新活動的當天收到 🔔；某站壞掉時收到 ⚠️（同站同一種壞法 7 天最多一次）；離線測試全數通過：`python3 -m pytest tests/ -k society -m "not live"` |
| 手動補救 | Actions →「學會活動監測」→ Run workflow，`首次執行` 留空即為日常模式；新增來源後第一次執行會把該站現有公告一次推出，屬預期行為 |

**壞掉先查哪裡（依序）**

1. **某一週沒收到心跳 = 整條線停擺**，先看 Actions 有沒有執行。
2. 收到 ⚠️ 異常：訊息會寫明是哪一站、哪一種壞法（連不上、解析出 0 筆、疑似改版）。多半是對方網站改版，要改 `society_watch/extract.py` 對應的 parser，並用 `tests/fixtures/society_watch/` 下的實抓樣本重跑測試。
3. 本機跑不動 AIRWAY 那站是正常的（這台電腦的網路連不到該 CDN），bootstrap 與實抓一律在 Actions 上跑。

---

## 三、點數促銷監測

一支 workflow 跑兩條線：先買點／買哩程促銷，再國泰世華小樹點轉點加碼，最後才是每週心跳。兩條線互相隔離，一邊壞掉不影響另一邊。

| 項目 | 內容 |
|---|---|
| 觸發 | `.github/workflows/points-watch.yml`：每天 10:30 台灣時間（cron `30 2 * * *`） |
| 程式 | `python3 -m points_watch.main`。`--dry-run`：照常抓取與判讀，訊息印到 log，不推播、不寫狀態、無視已看過的紀錄；`--bootstrap`：只把 RSS 現有文章記為已看過；`--pages N`：每個 RSS 抓幾頁（預設 2） |
| 資料來源（買點） | Loyalty Lobby、One Mile at a Time、Frequent Miler 三個 RSS（`points_watch/sources.py`）。追蹤 IHG、Choice、LifeMiles、Aeroplan、United、Alaska、AAdvantage、Flying Blue、Virgin Atlantic。官網（ihg.com、storefront.points.com）會擋，不用 |
| 資料來源（國泰世華） | 活動清單 `…/event/overview/credit-card.model.list.json`；活動頁網址加 `.model.json` 取內文。**不是公開 API**，銀行改版就會壞 |
| 評等基準 | `points_watch/baselines.json`：各計畫原價與近兩年公開促銷最佳價（不是史上最低，也不含限定對象的價格）。**一個計畫一行，手改時維持這個版面**，程式靠它做單行取代 |
| 狀態檔 | `points_watch/` 下的 `seen_articles.json`、`promos.json`、`cub_seen.json`、`cub_promos.json`、`alert_state.json`、`heartbeat.json`，以及會被自動下修的 `baselines.json`。都由 Actions commit 回 repo |
| 需要的 Secrets（名稱） | `CLAUDE_API_KEY`、`POINTS_LINE_CHANNEL_ACCESS_TOKEN`（獨立的 LINE 官方帳號，與日報、學會監測分開聊天室）。`POINTS_LINE_USER_ID` 只有在新舊 channel 不同 provider 時才需要；兩者沒設定時各自退回 `LINE_CHANNEL_ACCESS_TOKEN`／`LINE_USER_ID` |
| 驗收條件 | 每週一則 💓（含「國泰世華：清單 N 筆、初篩命中 M 筆」）；有 🟢／🟡 促銷時收到 💰；國泰世華有轉點加碼時收到 ✈️；截止前收到 ⏰；離線測試全數通過：`python3 -m pytest tests/test_points_*.py` |
| 手動補救 | Actions →「點數促銷監測」→ Run workflow，`mode` 選 `normal`／`dry-run`／`bootstrap` |

**壞掉先查哪裡（依序）**

1. **某一週沒收到心跳 = 停擺或該週每次執行都有失敗**（有失敗的那一輪刻意不送「運作正常」）。先看 Actions。
2. **Actions 紅燈**：文章或活動頁判讀失敗時會刻意亮紅燈。最常見是 Anthropic 餘額用盡或撞月上限，先看帳單再看程式。log 裡的「Haiku 原始回應」會印出模型實際回了什麼。
3. **心跳的初篩命中數變成 0**：國泰世華那條線靠「里程／積分」加「轉換／加碼」等字眼初篩，銀行換措辭就會漏掉而且**不會有告警**，這一行是唯一的線索。
4. **改了 prompt、關鍵字或基準之後**，先用 `dry-run` 看 log 裡會推出什麼，對過原文再正式執行。上線前兩條線都靠這一步抓到過誤判（獎勵票特價被當成買哩程、同一檔促銷推兩次）。
5. **LINE 回 200 但沒收到**：沒加新 bot 為好友，或 user ID 屬於另一個 provider。

**新增 LINE bot 的做法（2026-10 起）**：Messaging API channel 不能再從 LINE Developers Console 直接建立。要先在 LINE Official Account Manager 建官方帳號，再到「設定 → Messaging API」啟用並選 provider；選與既有 bot 相同的 provider，user ID 才會相同。

---

## 四、共同注意事項

- **狀態檔由 Actions commit 回 repo**，所以本機 push 常被拒。拉回來時用 merge，不要 rebase、不要 stash，以免動到工作區裡未提交的其他檔案。
- **這是 public repo**。寫程式、spec、plan、commit 訊息時，正式環境的設定值（資料庫網址、Firebase 網址、token）都算敏感內容，一律走 Secrets 或 `.env`。
- **`weekly-digest.yml`（麻醉科週報）排程已停用**，只保留手動觸發，原因寫在該檔案開頭的註解裡。它會消耗 API 額度，不要隨手重新啟用排程。
- 要跑本地測試一律用 `python3`（macOS 沒有 `python` 指令）。
- **`points_watch` 直接 import `society_watch` 的函式**（`fetch.get`、`state` 的告警節流與心跳、`notify.split_message`、`llm.MODEL`）。改這些函式的簽名或行為前，兩邊的測試都要跑：`python3 -m pytest tests/test_points_*.py tests/test_society_*.py`。
- **多支 workflow 會同時把狀態 commit 回同一個 repo**。排程雖錯開，但 Actions 常延遲，仍可能同時執行；每支都寫了「push 失敗就拉最新再推一次」，且各自只動自己資料夾的檔案。新增 workflow 時要照做。
- **容量與額度（2026-10-09 實測）**：repo 約 11 MB；public repo 的 Actions 不計分鐘數。若改成 private，免費額度是每月 2,000 分鐘，目前用量約每月 150 分鐘。
