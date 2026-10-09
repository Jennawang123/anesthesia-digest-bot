# 點數促銷監測與推播（points-watch）設計

日期：2026-10-09
狀態：設計定案；實作計畫見 `docs/superpowers/plans/2026-10-09-points-promo-watch.md`（RSS 九計畫）。`CUB` 另案。

## 1. 問題

使用者常錯過飯店買點、航空買哩程的促銷期，以及國泰世華轉哩程的加贈活動。需要兩件事：

1. 促銷開始時收到 LINE 通知（解決「沒看到」）
2. 通知裡直接告訴他這次的價格相對於歷史最佳是好是壞（解決「看到了但不知道該不該買」）

通報形式比照 `society_watch/`：有新東西才推、異常告警、每週心跳。

明確排除（YAGNI）：

- 直接監測官網（見 §2.1，被防機器人擋掉）
- IHG、Choice 以外的飯店集團
- 「該買多少點」的個人化試算、兌換價值估算——只判斷價格是否處於歷史低點
- 網頁介面、歷史價格圖表

## 2. 監測範圍

### 2.1 追蹤的計畫（9 個買點＋1 個轉點）

| 代號 | 計畫 | 類型 |
|---|---|---|
| `IHG` | IHG One Rewards | 飯店買點 |
| `CHOICE` | Choice Privileges | 飯店買點 |
| `LIFEMILES` | Avianca LifeMiles | 航空買哩程 |
| `AEROPLAN` | Air Canada Aeroplan | 航空買哩程 |
| `UNITED` | United MileagePlus | 航空買哩程 |
| `ALASKA` | Alaska Atmos Rewards | 航空買哩程 |
| `AA` | American AAdvantage | 航空買哩程 |
| `FLYINGBLUE` | Air France-KLM Flying Blue | 航空買哩程 |
| `VIRGIN` | Virgin Atlantic Flying Club | 航空買哩程 |
| `CUB` | 國泰世華小樹點 → 長榮／亞洲萬里通 | 轉點加贈 |

### 2.2 資料來源（2026-10-09 實測）

| 來源 | 結果 | 決定 |
|---|---|---|
| `ihg.com` 買點頁 | 403 | 不用 |
| `storefront.points.com`（IHG／Choice 實際售點店面） | 403 | 不用 |
| `loyaltylobby.com/feed/` | 200，RSS | **採用** |
| `onemileatatime.com/feed/` | 200，RSS | **採用** |
| `frequentmiler.com/feed/` | 200，RSS；實抓到「Buy IHG Points for as low as 0.5 cents each」 | **採用** |
| `awardtravelfinder.com/buy_points_promotions` | 200，結構未細驗 | 不採用（使用者選擇純 RSS 方案） |
| `cathay-cube.com.tw` 活動總覽 | 200 但只有 React 外殼；同網址加 `.model.json` 可取得靜態 JSON | 見 §5 |

**為何不盯官網**：官方店面由 points.com 代管並有防機器人，GitHub Actions 的機房 IP 抓不到。部落格 RSS 通常在促銷當天發文，標題即含加贈幅度與每點成本（例：「Buy Hilton Honors Points With Best-Ever 120% Bonus, 0.45 Cents Each」）。

**實抓後確認的三個限制**：(1) 每頁只有 14–25 篇（Loyalty Lobby 約兩天份），故每個 feed 抓兩頁（`?paged=2`）；(2) Loyalty Lobby 的連結帶 `?omhide=true`，比對前要去掉 query；(3) OMAAT 每個計畫共用固定網址、每次新促銷只更新發布日，故「看過的文章」的鍵是 `URL|發布日` 而非 URL。

## 3. 架構

沿用 `society_watch` 的形狀：GitHub Actions cron → Python → LINE push → 狀態檔 commit 回 repo。

```
.github/workflows/points-watch.yml     cron '30 2 * * *' = 台灣時間每日 10:30
points_watch/
  ├── sources.py      RSS 清單、各計畫關鍵字、CUB 來源設定
  ├── feeds.py        RSS XML → list[Article]（純解析，不碰網路）
  ├── extract.py      Haiku：Article → Promo（結構化促銷）或 None
  ├── rating.py       Promo + baselines → 每點成本、評等（純函式）
  ├── baselines.json  各計畫原價與歷史最佳每點成本
  ├── store.py        已推過的促銷、待提醒判定（已看過的文章直接用 society_watch.state）
  ├── notify.py       四種訊息的排版
  └── main.py         串接流程
tests/fixtures/points_watch/           實抓的 RSS 與文章樣本
```

**重用而非複製**：HTTP 抓取用 `society_watch.fetch.get`；LINE 推送與分頁用 `society_watch.notify.push_line`／`split_message`；告警節流與心跳用 `society_watch.state` 的 `should_alert`／`record_alert`／`heartbeat_period`／`should_heartbeat`。`points_watch` 只寫自己獨有的邏輯。LINE secrets（`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_USER_ID`）與 `CLAUDE_API_KEY` 沿用現有的，不需新申請。

**模組分界**：`feeds.py` 與 `rating.py` 是純函式，可完全離線測試。`extract.py` 是唯一呼叫 LLM 的地方。

### 3.1 資料結構

```python
Article = {"feed": "loyaltylobby", "title": str, "url": str, "published": date, "summary": str}

Promo = {
  "program": "IHG",          # §2.1 的代號
  "kind": "bonus",           # "bonus"（加贈）| "discount"（折扣）
  "percent": 100,            # 加贈或折扣的百分比（取最高級距）
  "stated_cpp": 0.50,        # 文章寫的每點成本（美分），可為 None
  "end_date": "2026-10-31",  # ISO 日期，可為 None
  "up_to": True,             # 是否為「最高可達」／分級／限定對象
  "url": str,
}
```

## 4. 流程

1. 逐一抓 RSS。單一 feed 失敗不影響其他 feed，記入失敗清單。
2. 以標題關鍵字篩選：必須同時命中「計畫關鍵字」（如 `IHG`、`LifeMiles`）與「購買關鍵字」（`buy`、`purchase`、`sale`）。沒命中的不送 LLM。
3. 濾掉 `seen_articles.json` 已有的文章（鍵為 `URL|發布日`）。
4. 每篇新文章送 Haiku，回傳 `Promo` 或「這不是買點促銷」。輸入只給標題與 RSS 摘要，不另抓全文。
5. 去重鍵＝`program|kind|percent|end_date`。鍵已在 `pushed_promos.json` 的不再推（同一促銷被多家報導、或「last call」舊文重發）。
6. `rating.py` 計算每點成本與評等（§6）。
7. 🟢 與 🟡 排入訊息；🔴 不推，但仍記入 `pushed_promos.json` 以免每天重算。
8. 推 LINE 成功後才寫狀態檔——與 `society_watch` 相同的不變量：磁碟上的狀態只代表已送出的東西，中斷只會重推不會漏報。
9. 檢查待提醒清單：🟢 促銷距 `end_date` 剩 2 天（含）以內且未提醒過，推一則 ⏰。

**Bootstrap**：首次執行用 `--bootstrap`，只把現有文章記入 `seen_articles.json` 不推播，避免上線當天把 RSS 裡十幾篇舊文全推出來。

## 5. 國泰世華轉點加贈（`CUB`）

獨立來源，不經 RSS 流程。評等規則固定：加贈 ≥15% 為 🟢，10–14% 為 🟡，低於 10% 不推。

**不在第一份實作計畫內**，RSS 管線上線驗收後另開計畫。2026-10-09 實抓：`…/credit-card/bonus/point-exchange/airmiles.model.json` 回 200 的靜態 JSON，但該頁目前只有常態兌換比率，無法驗證加贈活動會出現在哪一頁。

抓法依實抓結果三選一，依序嘗試：

1. 從頁面 JS 找出活動列表的 JSON 端點（比照 `society_watch` 的 PAIN 來源）
2. 整頁文字 diff＋Haiku（比照 AIRWAY 來源）
3. 官方抓不到時，改盯台灣哩程／信用卡部落格的 RSS，關鍵字「國泰世華」＋「哩程」＋「加贈」

三者皆不可行則如實回報使用者，`CUB` 從本期移除，不做假裝有在監測的空殼。

## 6. 評等

### 6.1 計算

```
bonus:    cpp = base_cpp / (1 + percent/100)
discount: cpp = base_cpp * (1 - percent/100)
```

`base_cpp` 取自 `baselines.json`。算出的 `cpp` 與文章的 `stated_cpp` 差距超過 10% 時，採用 `stated_cpp` 並在訊息加註「依文章報價」（原價可能已調整，或促銷結構非單純加贈）；`stated_cpp` 為 None 則用算出的值。

| 評等 | 條件 |
|---|---|
| 🟢 值得下手 | `cpp ≤ best_cpp × 1.03` |
| 🟡 普通 | `cpp ≤ best_cpp × 1.15` |
| 🔴 不推 | 其餘 |

`cpp < best_cpp` 時訊息標「🏆 新低」，並把 `baselines.json` 的 `best_cpp` 更新為新值（由 Actions 一併 commit；以單行字串取代改寫，不整檔重排）。

**防呆**：`cpp < best_cpp × 0.70` 視為抽取錯誤，走 ⚠️ 告警、不推播、不更新基準。否則一次抽錯就會把基準永久改壞，之後真正的好價全部變成 🔴。

### 6.2 基準表初始值

| 計畫 | 歷史最佳 | 對應促銷 | 查證 |
|---|---|---|---|
| IHG | 0.50¢ | 100% 加贈 | ✅ OMAAT、Loyalty Lobby；2026 年已出現至少六次 |
| CHOICE | 0.57¢ | 45% 折扣 | ✅ 搜尋結果指 2025-09 首見、2026-07 再現 |
| UNITED | 1.88¢ | 100% 加贈 | ⚠️ 僅見於 2026-09 促銷報導，未確認是否為歷史最佳 |
| LIFEMILES | 1.35¢ | 145% 加贈 | ⚠️ 同上 |
| AEROPLAN | 1.35¢ | 100% 加贈 | ⚠️ 同上 |
| ALASKA | 1.88¢ | 100% 加贈 | ⚠️ OMAAT 2026-10-02；另有「up to 120%」報導，是否公開促銷待查 |
| AA | — | — | ❌ 2026-09 的 2.26¢ 是折扣價，非歷史最佳 |
| FLYINGBLUE | — | — | ❌ |
| VIRGIN | — | — | ❌ |

**⚠️ 與 ❌ 的七家（含 ALASKA）必須在實作計畫的第一個任務逐家查證**（各家歷次促銷報導），填入 `base_cpp` 與 `best_cpp` 後交使用者過目，才能進行後續任務。基準錯誤會讓評等整個失真，這是本系統最重要的一份資料。

**已知特性**：IHG 的 100% 加贈一年出現多次，所以 IHG 的 🟢 會很頻繁——這是正確行為（確實平歷史最佳），代表錯過一次的代價不高。

## 7. 訊息

```
💰 點數促銷
🟢 IHG 買點 100% 加贈
每點 0.50¢（平歷史最佳）
⚠️ 最高可達，需登入確認個人優惠
截止 10/31
https://…

🟡 Alaska 買哩程 70% 加贈
每哩 2.21¢（歷史最佳 1.88¢，貴 18%）
截止 10/20
https://…
```

| 訊息 | 觸發 | 頻率 |
|---|---|---|
| 💰 新促銷 | 有 🟢 或 🟡 | 同日合併一則，🟢 排前面 |
| ⏰ 截止提醒 | 🟢 促銷剩 ≤2 天 | 每個促銷一次 |
| ⚠️ 監測異常 | 見 §8 | 同來源同原因 7 天最多一次 |
| 💓 每週心跳 | 每 ISO 週第一次成功執行 | 每週一則；內容含 RSS 數、累計判讀文章數、累計促銷筆數 |

`up_to` 為 True 時一律加註「最高可達，需登入確認個人優惠」。`end_date` 為 None 時顯示「截止日未註明」，且不排入 ⏰ 提醒。

## 8. 錯誤處理

以下情況走 ⚠️ 告警，不靜默跳過：

- 某個 feed 抓取失敗，或回傳 0 篇文章（RSS 不該是空的）
- Haiku 回傳無法解析
- 抽出的數值不合理：`percent` 不在 1–300、`stated_cpp` 不在 0.1–10、`program` 不在 §2.1、`end_date` 早於今天
- `CUB` 來源抓取失敗

單篇文章抽取失敗時，該文章**不**記入 `seen_articles.json`，隔天重試；其他文章照常處理。

LINE push 回 200 不代表送達（`society_watch` 已知限制），由每週心跳覆蓋。

## 9. 費用

Haiku 只處理通過關鍵字篩選的新文章，輸入為標題＋摘要（數百 token）。九個計畫合計估每週十餘篇，月費用遠低於一美元。與麻醉日報、學會監測共用同一 Anthropic 帳戶（月上限 $5）；撞上限時的症狀是 `extract.py` 全數失敗 → ⚠️ 告警。

## 10. 測試

- `feeds.py`：對實抓的 RSS fixture 驗證解析出的篇數與欄位
- 關鍵字篩選：正例（買點促銷）與反例（信用卡開卡禮、獎勵票特價、Hilton 買點）各取實際標題
- `rating.py`：三種評等的邊界值、bonus／discount 兩種算法、`stated_cpp` 覆寫、新低更新
- 去重：同促銷不同 URL、「last call」重發、同計畫不同截止日
- `extract.py` 的回應解析：合法 JSON、非促銷、殘缺欄位、不合理數值
- 截止提醒：剩 3／2／0 天、已提醒過、`end_date` 為 None
- 狀態寫入順序：推播失敗時狀態檔不變

LLM 呼叫本身以錄下的回應做測試，不在測試中打 API。

## 11. 上線步驟

1. 本機跑測試全過
2. push 後以 `workflow_dispatch` 帶 `bootstrap=true` 執行一次
3. 再手動執行一次一般模式，確認無新文章時不推播、心跳有送達
4. 等第一則真實 💰 出現，對照原文確認數字與評等正確
