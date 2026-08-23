# 旅遊 app 字級調整（正常／大／特大）設計

日期：2026-08-24
範圍：`iceland-trip.html`、`family-trip-template.html`
不在範圍：`couple-trip-template.html`、`us-trip.html`（使用者 2026-08-24 拍板不補）

## 問題

爸媽有老花，反覆回報字太小。過去已手動放大過兩批（日期／金額／tab 標籤／圓餅圖例；記事本／待辦），仍被嫌。手動調字級這條路已經證明會一直重來，且調到某個值就必然有人嫌大或嫌小——需要的是讓使用者自己選。

`<meta viewport>` 帶 `maximum-scale=1.0, user-scalable=no`（兩支第 5 行），所以連手機系統的雙指放大都用不了。這個限制不能拿掉：日內活動拖曳排序與 lightbox 的雙指縮放都依賴它，拿掉會讓已經修過四次的拖曳再壞一次。因此只能做 app 內建開關。

## 決策

| 項目 | 決定 | 理由 |
|---|---|---|
| 存哪裡 | localStorage，每台裝置各自選 | 爸爸設特大、媽媽設大、Jenna 維持正常，互不影響。存 Firebase 會讓四個人一起變。 |
| 範圍 | 只放大閱讀內容 | tab 標籤、按鈕、輸入框、設定頁維持原大小，版面崩壞風險低很多。 |
| 級距 | 1.0 / 1.15 / 1.35 | 特大一看就知道不一樣（記事 19→26px、金額 23→31px），但一張日卡還裝得下數個活動。 |
| 機制 | CSS 變數乘數 `calc(Npx*var(--fs))` | 單一真相來源，原始字級在 diff 裡看得見，切換不用重畫 DOM。 |

### 否決的機制

- **另加覆寫表**（`body.fs-l .act-name{...}`）：既有程式碼零改動，但同一個字級散在三處，日後改字級會漏同步。memory 已記載「字級是這支 app 反覆被要求的方向」，這個維護陷阱會一直咬人。
- **改用 rem/em 重構**：em 巢狀會相乘，長地名在多層結構裡會失控；且非內容規則也得一併轉換才不會混亂。

## 設計

### 資料

存 `fs`（`'n'|'l'|'xl'`）而非直接存倍數——日後想微調倍率只要改對照表，不必處理使用者裝置裡的舊數值。

併進既有裝置設定物件，沿用 `saveDevice()`，不另開 localStorage key：
- 冰島版 `iceland_trip`：`{url, apiKey, fs}`
- 家庭版 `family_trip`：`{url, geminiKey, fs}`

對照表 `FS={n:1, l:1.15, xl:1.35}`。套用即 `document.documentElement.style.setProperty('--fs', FS[fs])`。

iOS 清掉 localStorage 時會連同 Firebase 網址一起沒、字級退回正常。這是「存裝置」的已知代價。

### 生效時機

`<head>` 內加一段極短 inline script，開檔就從 localStorage 讀出來套上，早於 Firebase 連線與主程式。不這樣做會先閃一下正常字級再跳大。讀不到或值不認得就當 `n`，且整段包 try/catch——localStorage 在某些情境會直接丟例外，不能讓它擋住整個 app 啟動。

### 縮放白名單

`:root` 定義 `--fs:1`。以下規則的 `font-size` 改成 `calc(Npx*var(--fs))`：

- **行程**：`.st` `.day-n` `.day-tit` `.day-dt` `.day-num` `.day-date-badge` `.wchip` `.schip` `.cchip` `.act-ico` `.act-time` `.act-name` `.act-loc a` `.act-note-t` `.act-cost`
- **記帳**：`.edl` `.ei` `.edesc` `.emeta` `.eamt` `.bdg`
- **統計**：`.pie-title` `.pie-leg-row` `.pie-amt` `.pie-pct` `.pie-rate` `.member-name`
- **記事／待辦**：`.nt2` `.np` `.nd` `.clt` `.clp` `.note-title` `.note-preview` `.todo-item` `.clc.done::after`
- **冰島版獨有**：`.kmchip` `.leg-d` `.leg-b` `.stay-ro` `.closed-tag` `.closed-note` `.sf-h` `.sf-ico` `.sf-lbl` `.sf-name` `.sf-dist` `.sf-tag` `.sf-note` `.dm-n` `.dm-name` `.dm-co` `.leaflet-marker-num` `.ov-h` `.ov-date` `.ov-date2` `.ov-stay` `.ov-name` `.ov-loc` `.ov-nav`
- **JS 模板／inline**：統計總計（25px/18px）、待辦完成計數（18px）、「尚無活動」（16px）、冰島版的離線狀態（17px）與「快照更新於」（15px）

不縮放：`#setup` 全區、`.hint`、標題列、底部 tab `.ti`、FAB、`.btn` `.ib` `.inp` `.ta` `.lb`、分類／幣別／拆帳選擇器（`.cati` `.pb` `.cr` `.acc-opt` `.pie-tab`）、公休日圓圈 `.dow-btn`、lightbox、拖曳幽靈 `#drag-ghost`。

**`.ds-chip`（Day 導覽列的日期 chip）刻意排除**：它顯示日期、看起來像內容，但位於固定高度的 sticky 導覽列，字放大會撐破或切字。爸媽真正在讀的是日卡本身。

### 固定高度連帶修正

白名單元素所在的容器若有寫死 `height`，改成 `min-height`。逐一量測後才改，不是整檔掃描替換——沒縮放的 tab 列等不動。

### 設定頁 UI

「顯示字級」放在設定頁**最上方**（爸媽進設定頁多半就是為了這個），三格 `.acc-opt` 樣式按鈕（正常／大／特大）。點下去立即生效並存檔，不經過「儲存設定」——這是裝置設定，跟走 Firebase `/config` 的 `saveCfg()` 分開。

下方一行**跟著縮放的範例字**。設定頁本身不放大，沒有這行的話按下去畫面毫無反應，爸媽會以為壞掉。

## 測試

`_selftest()` 新增：
- 三級對照表數值正確（1 / 1.15 / 1.35）
- 未知值與空值退回 `n`
- `fs` 有進 `saveDevice()` 寫出的 payload
- 白名單裡每個 selector 在該檔案確實存在——防止 selector 名稱打錯導致靜默失效（這類錯誤不會報錯，只會有一兩個元素沒跟著放大，肉眼很難發現）

兩支各自跑。

## 部署

兩支都是 Netlify 手動拖拉部署，commit 不等於上線。冰島版版本號在標題列右下角。
