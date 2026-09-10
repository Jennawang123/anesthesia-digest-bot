# 學會活動監測與推播（society-watch）設計

日期：2026-09-10
狀態：設計定案，待寫實作計畫

## 1. 問題

使用者是麻醉科住院醫師，會錯過學會活動與 workshop。經確認，錯過的**唯一原因是「根本沒看到公告」**——不是看到了卻忘記報名截止。

因此系統的職責被限縮為單一件事：

> 定期輪詢五個學會的活動／公告頁，判斷「這一則我通知過了嗎」，沒通知過就推播。

明確排除（YAGNI）：

- 報名截止倒數提醒
- 依麻醉積分／主題篩選
- 活動日期正規化、排序、行事曆匯出
- 網頁介面

## 2. 監測來源（全部經 2026-09-10 實抓驗證）

| 代號 | 學會 | 抓取 URL | 渲染 | 實抓筆數 |
|---|---|---|---|---|
| `TSA` | 台灣麻醉醫學會 | `https://www.anesth.org.tw/events/index.asp` | 靜態 SSR | 15 |
| `TSCVA` | 台灣心臟胸腔暨血管麻醉醫學會 | `https://congress.tscva.org.tw/news` | 靜態 SSR | 6 |
| `RAPM` | 台灣區域麻醉暨疼痛醫學會 | `https://rapm.org.tw/news-list/2`（學會活動）<br>`https://rapm.org.tw/news-list/5`（友會活動） | 靜態 SSR | 16 / 11 |
| `PAIN` | 台灣疼痛醫學會 | `https://pain.org.tw/index.php/educlass_page/educlass_page1_content/33/1/8/0?yy=<年>` | AJAX fragment | 10（2026 年） |
| `AIRWAY` | 台灣呼吸道處理醫學會 | `https://www.tsamairway.org.tw/最新資訊` | Wix SSR | 無「則」概念 |

### 2.1 來源決策紀錄

- **TSCVA 抓 `/news` 而非使用者提供的首頁 `https://congress.tscva.org.tw/`。** 首頁的最新消息只是摘要，`/news` 是完整列表，且兩者都帶 UUID 連結。
- **RAPM `/news-list/` 的數字是分類不是分頁**：`2`=學會活動、`4`=活動花絮（事後照片，不監測）、`5`=友會活動（納入，別的學會辦的課對使用者命中率高）。
- **PAIN 走的是內部 AJAX endpoint，非公開 API。** 該路徑是從頁面 JS 的 `$("#main_content").load(...)` 挖出來的，實測免 cookie、免 session 可直接抓。改版風險高於其他四站，必須有告警覆蓋（見 §6）。

## 3. 架構

沿用既有 `daily_fetch_classify.py` / `daily_push.py` 的形狀：GitHub Actions cron → Python → LINE push → 狀態檔 commit 回 repo。

不採用 launchd（筆電未開就不跑，且 `scripts/backup_db.py` 有靜默失敗三週前科），不採用 Render（免費 750 小時已被 `jenna-finance` 佔滿）。

```
.github/workflows/society-watch.yml    cron '0 2 * * *' = 台灣時間每日 10:00
society_watch/
  ├── sources.py      來源設定表：每站 url / parser / 分類標籤
  ├── fetch.py        HTTP：UA、timeout、retry×3、逐站錯誤隔離
  ├── extract.py      五個 parser：HTML → list[Event]
  ├── state.py        seen.json 讀寫、bootstrap 模式
  └── notify.py       LINE 推播、4800 字拆分、失敗告警與節流
tests/fixtures/society_watch/          2026-09-10 實抓樣本（見 §8）
```

**模組分界**：`extract.py` 的每個 parser 只做「HTML → Event list」，不碰網路、不碰狀態、不碰通知，因此可對著離線 fixture 完整測試。

### 3.1 Event 資料結構

```python
{
  "source": "TSA",          # 來源代號
  "uid": "3105",            # 站方穩定 ID
  "title": "...",
  "date_text": "115/11/08", # 原樣字串，不正規化
  "url": "https://...",
  "kind": "鎮靜活動",        # 站方分類，無則為 None
  "minor": False,           # True = 降級到「其他公告」區（見 §5）
}
```

`date_text` **刻意保持原樣不正規化**。五站格式各異（民國年 `115/11/08`、ISO `2026-08-26`、標題內嵌 `＠November 1`、中文 `2026 八月 23`），而系統既不排序也不比較日期，只是原樣顯示給使用者看。不轉換就沒有把民國 115 年誤判成 2015 年的機會。

## 4. 抽取層（逐站策略）

### 4.1 TSA — 硬解析

- 容器：`.event-item`
- `uid`：`a.e-link` 的 `href="content.asp?ID=3105&EduType=4"` → `3105`
- `title`：`h4.e-title`
- `date_text`：`.e-date` 文字（跨日活動含 `.e-date-end`，例 `115/09/26 ~ 115/09/27`）
- `kind`：`.e-type`（實抓值：`鎮靜活動`、`年會工作坊`、`麻醉年會活動/報名`）
- 附加：`.e-place`（地點）納入通知
- `url`：`https://www.anesth.org.tw/events/content.asp?ID=<uid>&EduType=<n>`
- 無分頁，15 筆滾動視窗，含已過期活動（實抓範圍 115/09/06～115/11/08）

### 4.2 TSCVA — 硬解析

- 容器：`a.news_card`
- `uid`：`href="/news/e9003f5d-1793-4fc4-babe-d031dd36b18b"` 的 UUID
- `title`：`p.news_card_title`
- `date_text`：`time.news_card_time` 的 `datetime` 屬性（已是 ISO，例 `2026-09-01`），**為公告日非活動日**

> ⚠️ `/news` 列表頁與首頁用的是**不同的 class**。首頁是 `a.index_news--item` / `._date` / `._title`，
> `/news` 是 `a.news_card` / `time.news_card_time` / `p.news_card_title`。此處以 `/news` 為準，
> 已對 fixture 實測抽出 6 筆。
- 該站會自行在標題加 `[即將辦理活動]` 前綴，可當作活動判斷的免費訊號

### 4.3 RAPM — 硬解析

- 容器：`.service_item`
- `uid`：`.service_title a` 的 `href="https://rapm.org.tw/news-detail/32"` → `32`
- `title`：`.service_title a` 文字（含大量空白與 `<!--[if BLOCK]-->` 註解，需 normalize whitespace）
- `date_text`：`.service_date`，**為公告日非活動日**；活動日只存在於標題（例 `疼痛擂台 8：真實病人工作坊-全脊守護，從頸到骶 ＠November 1`）或海報 jpg 上，不嘗試抽取
- `kind`：依來源 URL 標為 `學會活動`（`/news-list/2`）或 `友會活動`（`/news-list/5`）
- 兩個分類共用同一組全域 `news-detail/{id}` 編號（實測 list 2 為 id 1–32、list 5 為 id 21–23，無重疊），因此 `uid` 不需再依分類加前綴

### 4.4 PAIN — 硬解析（含跨年處理）

- 容器：表格 `<tr>`
- `uid`：`onclick="cal_listview_click_func('3142')"` → `3142`
- `title`：`span.text-info.font-weight-bold`
- `date_text`：日期欄三個 span 組合（`2026` / `八月` / `23`）
- `url`：**該站「詳細」是 onclick 而非 href，無逐則網址**，通知一律連到列表頁 `https://pain.org.tw/index.php/educlass_page/index/33/1/8/34`
- 列表本身還含 `課程時間`、`主辦單位`、`允許學分`、`早鳥時間`、`報名時間` 等欄位；本版不使用（已 YAGNI 掉截止倒數）

**跨年漏報防護（必要）**：該列表是「年份 × 分類」scoped，預設只回當年。實抓 2026 年 10 筆全部已過期（最新 8/23，抓取日 9/10），代表明年度活動一旦公告**不會出現在預設頁面**。因此每次執行必須抓 **今年 + 明年** 兩次（`?yy=2027` 實測有效，目前回空表但機制正常），兩份結果合併去重。

### 4.5 AIRWAY — 文字 diff + LLM 抽取

Wix 站，SSR 有吐出可見文字（實抓 124 行），但**完全無結構**：整頁是一片連續富文本（例 `📅 時間：115年2月7日（星期六）08:30–12:30`），沒有逐則邊界、沒有逐則日期、沒有逐則連結。硬解析無從下手。

流程：

1. 抓頁面 → 去 `<script>` / `<style>` → 抽純文字 → 逐行 strip、去空行
2. 與 `airway_snapshot.txt` 逐行 diff，取**新增的行**
3. 無新增行 → 完全不呼叫 LLM，結束
4. 有新增行 → 把新增段落丟給 Claude Haiku，問「這是不是活動／課程／工作坊公告？是的話標題與日期為何？」
5. `uid` = 標題文字的 SHA-1 前 12 碼
6. `url` 一律為頁面本身網址

**成本**：只有新增時才呼叫，量趨近於零，不影響現行 Anthropic 帳戶的 $5/月上限。

**LLM 判不出來時，一律當成活動放主區**（不確定時偏向通知，見 §5）。

## 5. 降噪：排版分層，不做過濾

**不**用 LLM 決定「要不要推」。過濾錯的代價是漏報，而漏報正是本系統要解決的問題本身；在核心引入一個會編答案且失敗無聲的環節，trade-off 方向是錯的。

改為：**所有新項目都推，一則不漏**，只把明顯非活動者標 `minor=True` 降到訊息底部的「其他公告」小區塊。

| 來源 | 降級規則 |
|---|---|
| `TSCVA` | 標題含 `名單`、`恭賀`、`獲獎`、`甄審條件` → `minor`（實抓 6 則中命中 3 則）。另有 2 則（`…報告順序`、`…甄選辦法`）是獎項作業公告但不含上述關鍵字，**刻意不追加關鍵字去攔**——為個案加規則屬 over-fitting，且依 §5 原則不確定時一律偏向通知。 |
| `TSA` | 不降級（`.e-type` 顯示全部都是活動） |
| `RAPM` / `PAIN` | 不降級（來源本身即活動列表） |
| `AIRWAY` | 由 Haiku 標記；判不出來 → 不降級 |

## 6. 失敗告警

系統的失效模式與它要解決的問題是同一個（漏報），因此告警優先於解析正確性。

| 情況 | 動作 |
|---|---|
| HTTP 非 200 或 timeout（retry×3 後） | 推播告警，標明站別 |
| HTTP 200 但**解析出 0 筆** | 推播「疑似改版」告警——四個結構化站正常皆 ≥5 筆 |
| AIRWAY 純文字行數較快照暴跌 > 50% | 推播告警（Wix 改版或頁面搬家） |
| 單站失敗 | **不中斷其他站**，其餘照常抓取與推播 |
| 告警節流 | 同一站 7 天內最多告警一次，避免站掛掉時天天吵 |

思路同 `daily_fetch_classify.py` 的 `MIN_ARTICLES = 20` 守門，此處為逐站版本。

## 7. 狀態檔與去重

沿用 `daily_data/sent_articles.json` 的既有慣例：排序後 pretty-print，**一則一行**，讓每日 commit 的 diff 只有真正新增的那幾行。

```
society_watch/seen.json            {"seen": ["TSA:3105", "TSCVA:e9003f5d-...", ...]}
society_watch/airway_snapshot.txt  Wix 純文字快照，一行一段
```

Airway 用純文字而非 JSON，因為 git diff 本身就是我們要的東西。

三條硬規則：

1. **狀態檔只增不減。** TSA 是 15 筆滾動視窗，舊活動會掉出列表；若為省空間裁剪 `seen`，該筆日後若重新出現就會重推。一則 uid 數十 bytes，跑十年不過數百 KB，不值得為此冒重推風險。
2. **首次執行必須是 bootstrap 模式：只寫狀態檔、不推播。** 否則第一次跑會把五站現存約 50 則一次推出造成洗版。用明確的 `--bootstrap` 旗標控制，不依賴「檔案不存在就靜默跳過」這種隱式行為。
3. **`uid` 一律用站方穩定 ID，不用標題或連結全文做 hash。** 實抓證據：TSA 有一則標題為 `[請確認登記成功、收到繳費通知信後再繳費]2026圍術期 POCUS 實戰工作坊(報名已額滿，名單詳內)(0901議程更新)`，顯示標題會被主辦方反覆編輯；以標題 hash 為 key 會導致每次改議程都重推。
   - 例外：AIRWAY 無站方 ID，只能用標題 hash，此限制已知並接受。

## 8. 測試

五份 2026-09-10 實抓樣本已存入 `tests/fixtures/society_watch/`，parser 一律對著離線 fixture 測試，**不打真實網路**：

```
tsa_events_20260910.html        52 KB
tscva_news_20260910.html        22 KB
rapm_newslist2_20260910.html    74 KB（學會活動）
rapm_newslist5_20260910.html    44 KB（友會活動）
pain_fragment_20260910.html     14 KB
airway_text_20260910.txt        4 KB（已抽為純文字，避免 1.1 MB Wix HTML 進 public repo）
```

斷言寫實際值：

- TSA 抽出 15 筆；首筆 `uid == "3105"`、`date_text == "115/11/08"`、`kind == "鎮靜活動"`
- TSCVA 抽出 6 筆；首筆 `uid == "e9003f5d-1793-4fc4-babe-d031dd36b18b"`、`date_text == "2026-09-01"`、`minor is True`；6 筆中 `minor` 命中 3 筆
- PAIN 抽出 10 筆；首筆 `uid == "3142"`、`date_text == "2026 八月 23"`
- RAPM 學會活動抽出 16 筆、首筆 `uid == "32"`、`date_text == "2026-08-26"`；友會活動抽出 11 筆、首筆 `uid == "23"`
- AIRWAY 純文字 124 行；空 diff 時不呼叫 LLM

狀態層另測：bootstrap 不推播、同一 uid 不重推、僅新增才推、單站例外不影響其他站。

## 9. 通知格式

單則 LINE 訊息推給使用者個人（非日報的群組），沿用 `daily_push.py` 的 4800 字拆分接力邏輯。

```
🔔 學會新活動 3 則

【台灣麻醉醫學會】
・2026年健康台灣深耕計畫暨特管法輕中度鎮靜課程_1108高醫場
  115/11/08｜高雄醫學大學臨床技能中心
  https://www.anesth.org.tw/events/content.asp?ID=3105

【疼痛醫學會】
・…（連結為列表頁，該站無逐則網址）

── 其他公告 ──
・【TSCVA】2026 年度專科醫師甄審通過名單
```

連結的先天限制據實標明，不假裝有：PAIN 只有列表頁，AIRWAY 整頁一個網址。

## 10. 憑證與安全

- monorepo 為 **PUBLIC**。學會公告本身是公開資訊，抓取結果進 repo 不構成問題。
- LINE 推播憑證與個人 userId 一律走 **GitHub Secrets**，不落地成檔案。
- **LINE userId 綁定 bot channel**：麻醉日報那支 bot 取得的 userId，與 MCP plugin 那支 bot 的 userId 不同，不可互用。實作時需以實際推播的 bot channel 取得使用者 userId（加好友後從 webhook log 撈）。
- 沿用既有 `LINE_CHANNEL_ACCESS_TOKEN`，新增 `LINE_USER_ID` secret（不重用 `LINE_GROUP_ID`）。

## 11. 排程

GitHub Actions cron **每日 02:00 UTC（台灣時間 10:00）** 執行一次（`cron: '0 2 * * *'`），刻意與日報的 08:45 抓取與 09:05 推送錯開。學會公告更新頻率為週級，一天多抓數次只是浪費配額。Actions cron 常有數十分鐘延遲，對本用途無影響。
