# 國泰世華小樹點轉點加碼監測（points-watch／CUB）設計

日期：2026-10-09
狀態：**2026-10-09 已上線**，隨 `points-watch.yml` 每日台灣 10:30 執行。實作計畫見 `docs/superpowers/plans/2026-10-09-cub-transfer-bonus-watch.md`。

上線時與本文的差異（以程式碼與測試為準）：`program` 由程式從夥伴名稱判定，不由 Haiku 填；夥伴多了 `start_time`／`end_time`，非整天（00:00／23:59 以外）才顯示；內容是否更新改比百分比而非 `bonus` 措辭；`points_watch` 的所有通知改走獨立 LINE bot（`POINTS_LINE_CHANNEL_ACCESS_TOKEN`／`POINTS_LINE_USER_ID`，未設定時退回原 bot）。
前案：`2026-10-09-points-promo-watch-design.md` §5（當時因無樣本而移出）

## 1. 問題

使用者想在國泰世華推出「小樹點(信用卡)轉換航空里程／飯店積分限時加碼」時收到 LINE 通知。這類活動一年約一至兩次，錯過就要再等一年。

前案原訂「只看長榮與亞洲萬里通、加贈 ≥10% 才推」。2026-10-09 取得今年的實際活動後，該規則被推翻：今年亞萬只有 8%、長榮未參加，照原規則會完全不通知，而活動其實包含 IHG 50%。使用者定案改為：

> **只要出現轉點加碼活動就通知，列出全部夥伴。** 評等燈號只是訊息裡的標示，不是推不推的開關。

明確排除（YAGNI）：

- 換算「每哩成本多少元」——需要假設小樹點一點的價值，因人而異
- 其他銀行的轉點活動
- 盯台灣哩程部落格（留作官方端點失效時的備案，本案不做）
- 聯名卡的其他優惠（門票、行李運送、刷卡金等）

## 2. 資料來源（全部經 2026-10-09 實抓驗證）

| 用途 | URL | 結果 |
|---|---|---|
| 活動清單 | `https://www.cathay-cube.com.tw/cathaybk/personal/event/overview/credit-card.model.list.json` | 200，JSON，313 KB，149 筆 |
| 活動內文 | 活動頁網址把 `.html` 換成 `.model.json` | 200，JSON，約 140–170 KB |

清單端點是瀏覽器載入活動專區時實際呼叫的（以瀏覽器的網路請求紀錄確認），**不是公開 API**，改版風險高，必須有告警覆蓋（§7）。

樣本存於 `tests/fixtures/points_watch/`：`cub_list.json`（清單）、`cub_promo_page.json`（今年的加碼活動頁）、`cub_standing_page.json`（常態兌換比率頁，反例）。

### 2.1 清單結構

```
{"campaigns": [ {"campaignPath": "/content/cub-aem-cs/zh-tw/cathaybk/personal/event/overview/credit-card/travel/202609/miles20251011.html",
                 "campaignProps": {"jcr:title": "...", "campaignTitle": "...", "campaignContent": "...",
                                   "subtitle": "...", "startDate": "2026-09-30T16:00:00.000+00:00",
                                   "endDate": "...", "cq:lastModified": "2026-09-18T08:58:04.436+00:00", ...}} ],
 "currentPagePath": "...", "currentPageProperties": {...}}
```

- 149 筆全部都有 `jcr:title`、`campaignTitle`、`campaignContent`、`cq:lastModified`。`subtitle`、`startDate`、`endDate` 不是每筆都有。
- 日期是 UTC；`2026-09-30T16:00Z` 即台灣時間 10/1 00:00。
- 公開網址＝`https://www.cathay-cube.com.tw` ＋ `campaignPath` 去掉前綴 `/content/cub-aem-cs/zh-tw` 與結尾 `.html`。

### 2.2 活動頁結構

`.model.json` 是巢狀的元件樹。內文在 `:type` 含 `cub-main` 的節點底下，散落於各子元件的 `text`、`title`、`content`、`subTitle`、`description` 字串欄位（含 HTML 標籤與 `&nbsp;`）。把這些欄位依樹的順序接起來、去標籤，今年的加碼頁得到約 3,000 字的純文字，夥伴、加贈幅度、期間、登錄條件俱全；常態頁約 5,000 字且不含「加贈」。

### 2.3 初篩實測

以「（里程｜哩程｜里數｜哩數｜積分）且（轉換｜兌換｜加碼｜加贈）」比對 `jcr:title`＋`campaignTitle`＋`campaignContent`＋`subtitle`，149 筆命中 3 筆：

| 活動 | 是否為轉點加碼 |
|---|---|
| 秋日遊-點數轉換指定航空里程/飯店積分限時加碼 | 是 |
| 小樹點(信用卡)兌換航空里程/飯店積分（常態比率頁） | 否 |
| PChome 24h購物 2026/10 累積加碼活動 | 否 |

初篩只求不漏；是否為限時加碼由 Haiku 判讀內文決定。

## 3. 架構

放在既有的 `points_watch/` 內，與買點監測共用同一支 workflow（`points-watch.yml`）、同一個排程、同一組 secrets。

```
points_watch/
  ├── cub.py          清單 JSON → list[Campaign]；初篩；活動頁 JSON → 純文字（純函式）
  ├── cub_extract.py  Haiku：活動內文 → TransferBonus | None；回應檢查
  ├── cub_store.py    cub_promos.json 讀寫、截止提醒判定
  ├── cub_notify.py   ✈️ 活動訊息、⏰ 提醒訊息的排版
  ├── cub_run.py      這條線的流程
  └── main.py         （修改）在買點流程之後呼叫 cub_run，兩者的失敗互不影響
```

HTTP、LINE 推送、告警節流沿用 `society_watch` 的函式，與買點監測相同。

**兩條線隔離**：`main.run` 先跑完買點流程（含它自己的狀態寫入），再呼叫 CUB 流程；CUB 流程拋出的例外由 `main` 接住並轉成一筆失敗，不可讓買點那邊已完成的工作受影響。心跳維持一則，內容多一行 CUB 的統計。

### 3.1 資料結構

```python
Campaign = {"path": str,            # campaignPath 原值
            "url": str,             # 公開網址
            "title": str,           # jcr:title
            "blurb": str,           # campaignTitle + campaignContent + subtitle
            "modified": str}        # cq:lastModified 原字串
# key = f"{path}|{modified}"

Partner = {"name": str,             # 頁面上的夥伴名稱原文
           "program": str | None,   # "EVA" | "ASIAMILES" | None（其他）
           "bonus": str,            # 加贈內容的一句話描述（例「滿 1 萬里送 800、滿 2 萬里送 1,600」「每次轉換加贈 30%」）
           "percent": int | None,   # 可換算成百分比時填，否則 None
           "start": date | None, "end": date | None,
           "registration": str | None,   # 需登錄時的登錄期間與名額原文摘要；不需登錄為 None
           "cap": str | None}            # 回饋上限；無上限為 None

TransferBonus = {"campaign": Campaign, "partners": list[Partner]}   # partners 至少一筆
```

## 4. 流程

1. 抓清單並解析成 `Campaign`。抓取失敗、不是預期結構、或 `campaigns` 為空 → 記一筆失敗，本輪結束（§7）。
2. 初篩（§2.3）。
3. 濾掉 `cub_seen.json` 已有的鍵（`path|modified`）。銀行事後修改活動頁，`cq:lastModified` 會變，該活動就會重新判讀。
4. 逐筆抓活動頁 `.model.json`、取出純文字、送 Haiku。
   - 回「不是限時加碼」→ 記為已判讀。
   - 回 `TransferBonus` → 與 `cub_promos.json` 中同 `path` 的紀錄比對夥伴清單（名稱＋`bonus`＋起訖日）。沒有紀錄＝新活動；有紀錄且不同＝內容更新；相同＝不推。
   - 抓取或判讀失敗 → 記一筆失敗，**不**記為已判讀，隔天重試。
5. 推 ✈️ 訊息（新活動與內容更新各自一則）。推播成功後才寫 `cub_promos.json` 與 `cub_seen.json`——與既有流程相同的不變量。
6. 截止提醒：對 `cub_promos.json` 的每個活動，把夥伴依 `end` 分組；某個截止日距今 0–3 天且該日尚未提醒過 → 推一則 ⏰，列出那天到期的夥伴，並記下已提醒的日期。

**不做靜默 bootstrap**：第一次執行就會把目前進行中的活動推出來（使用者定案）。初篩後只有 3 筆要判讀，不會洗版。

## 5. 訊息

```
✈️ 國泰世華小樹點轉點加碼
秋日遊-點數轉換指定航空里程/飯店積分限時加碼

⭐ 亞洲萬里通｜8%（⚪ 低於 10%）
  滿 1 萬里送 800、滿 2 萬里送 1,600
  10/1–10/31
  需登錄：10/28 16:00–10/30 23:59，限量 2,000 名
  上限：每正卡戶 1,600 里
・洲際優悅會｜50%
  10/1–11/30
・JAL哩程儲蓄專案｜30%
  10/1–11/30
・法航荷航藍天飛行｜20%
  10/1–11/1

長榮：本次未參加
https://www.cathay-cube.com.tw/cathaybk/personal/event/overview/credit-card/travel/202609/miles20251011
```

- 長榮與亞萬排最前、標 ⭐，並給燈號：`percent` ≥15 🟢、10–14 🟡、<10 ⚪；`percent` 為 None 時不給燈號，只顯示 `bonus`。
- 其他夥伴以「・」列出，依 `percent` 由高到低（None 排最後），不評等。
- 長榮、亞萬中沒出現的那家，在結尾註明「本次未參加」；兩家都沒有就寫「長榮、亞洲萬里通：本次未參加」。
- 內容更新時，第一行改為「✈️ 國泰世華小樹點轉點加碼（內容更新）」。
- `registration`、`cap` 有值才各佔一行。**登錄期間必須顯示**：今年亞萬的登錄窗口是 10/28 16:00 才開，只有 55 小時，比活動期間本身更容易錯過。

```
⏰ 國泰世華轉點加碼即將截止
10/31 截止（剩 3 天）

⭐ 亞洲萬里通｜8%
  需登錄：10/28 16:00–10/30 23:59，限量 2,000 名

https://…
```

## 6. Haiku 抽取

輸入：活動標題＋活動頁純文字（上限 6,000 字）。輸出一個 JSON 物件：`{"is_transfer_bonus": false}` 或 `{"is_transfer_bonus": true, "partners": [...]}`，每個夥伴的欄位如 §3.1。

Prompt 要點：

- 定義：以小樹點(信用卡)轉換航空里程或飯店積分時，**在指定期間額外加贈**。常態兌換比率、刷卡回饋、抽獎、門票與行李優惠都不算。
- `program`：夥伴是長榮航空（無限萬哩遊）填 `EVA`，亞洲萬里通填 `ASIAMILES`，其餘填 null。
- `percent`：頁面寫百分比就照填；寫「滿 X 送 Y」時以 Y÷X 換算並取整（800÷10,000＝8）；無法換算填 null。
- 日期只取日期部分（`YYYY-MM-DD`），忽略時分。
- `registration`、`cap`：以一句話摘出，沒有就 null。

回應檢查（不通過即視為失敗，§7）：不是 JSON、缺 `is_transfer_bonus`、`partners` 為空、`name` 或 `bonus` 為空字串、`program` 不在三個允許值、`percent` 不在 1–300、日期格式錯、`end` 早於 `start`。**`end` 早於今天不算錯**——活動可能進行到一半才被我們看到，個別夥伴已截止是正常的；只是該夥伴不再排入提醒。

## 7. 錯誤處理

以下走既有的 ⚠️ 告警（同來源同原因 7 天一次），來源名稱一律以 `國泰世華` 開頭：

- 清單抓取失敗
- 清單不是 JSON、沒有 `campaigns` 鍵、或 `campaigns` 為空
- 清單有資料但**沒有任何一筆同時具備 `campaignPath` 與 `jcr:title`**（結構改名）
- 活動頁抓取失敗、不是 JSON、或找不到 `cub-main` 節點、或取出的純文字少於 200 字
- Haiku 回應檢查不通過

「初篩命中 0 筆」不是錯誤——活動下架後、常態頁改名後都可能發生，而且無法與真正的「沒有活動」區分。這是已知的盲點：若銀行把轉點加碼改用完全不同的措辭，初篩會漏掉且沒有訊號。緩解方式是初篩刻意寬鬆，並在心跳裡顯示「清單 N 筆、初篩命中 M 筆」，M 長期為 0 時人可以察覺。

CUB 流程的任何失敗都不影響買點流程的推播與狀態。CUB 判讀失敗比照買點，讓 workflow 以非零狀態結束。

## 8. 測試

- `cub.py`：對 `cub_list.json` 驗證解析出 149 筆、初篩恰為 §2.3 那 3 筆、公開網址轉換正確；對兩份活動頁 fixture 驗證純文字含／不含關鍵內容；各種壞結構拋出明確例外
- `cub_extract.py`：回應解析的正反例（含「滿 X 送 Y」、已截止的夥伴、缺欄位、不合理數值）；不打 API
- `cub_store.py`：提醒判定（剩 4／3／0 天、已過期、同日多夥伴合併、已提醒過、無截止日）；夥伴清單的異同比對
- `cub_notify.py`：§5 兩則訊息的完整文字；燈號三個區間與 `percent` 為 None；長榮／亞萬缺一、缺二；內容更新的標題
- `cub_run.py`：新活動推一次、第二輪靜默、`modified` 改變但內容相同不推、內容改變推「內容更新」、判讀失敗隔天重試、推播失敗不寫狀態
- `main.py`：CUB 流程拋例外時買點流程的推播與狀態不受影響；心跳含 CUB 統計

## 9. 上線步驟

1. 本機測試全過。
2. Actions 跑 `dry-run`：應判讀 3 筆、產出 §5 的 ✈️ 訊息。把訊息與官方頁面逐項對照後交使用者確認。**這是檢查點，確認前不正式執行。**
3. 手動跑一次日常模式，使用者確認 LINE 收到 ✈️。
4. 之後隨既有排程每日執行。
