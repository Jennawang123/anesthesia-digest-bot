# 住宿自動出發／入住卡片設計

日期：2026-08-29
範圍：`iceland-trip.html`、`family-trip-template.html`、`couple-trip-template.html`、`us-trip.html`（四支共用同一套行程渲染邏輯）

## 問題

住宿目前只記在入住日那一筆活動（`stay.out` 指向退房日），中間跨夜的日子 `day.acts` 裡沒有它。既有 `coveringHotel(sched,did)` 已經能推算「今晚住哪」，但只餵給地圖標記與安全資訊定位，行程列表本身沒有對應項目——中間夜晚(如 9/21)行程頁尾端看不到住宿，也完全沒有「今早從住宿出發」方向的推算，看不出從飯店到當天第一個景點要多久。

## 決策

| 項目 | 決定 | 理由 |
|---|---|---|
| 退房日早上算不算「從住宿出發」 | 算 | 邏輯上退房當天早上人也是從這間飯店出發；使用者 2026-08-29 拍板。 |
| 呈現方式 | 完整唯讀卡片（圖示＋飯店名），不能編輯/刪除/拖曳 | 使用者要看到的是「行程」項目，不只是一行距離文字；卡片與既有活動卡視覺一致，插進去不突兀。 |
| 資料寫哪裡 | 純渲染時計算，不寫回 Firebase | 沿用既有「跨夜住宿只記一筆」的設計哲學（見程式碼註解），避免一動時間要改三處、座標要各查一次。 |

### 否決的機制

- **把住宿也寫成每天一筆真實活動**（存進 `/schedule/{did}/acts`）：使用者不用改資料模型也能達到效果，且既有程式碼明確警告過這樣做的維護成本（改一次要改三處）。
- **只加強距離線文字，不做卡片**：使用者在澄清問題時已明確選擇要完整卡片。

## 設計

### 資料層：新增 `morningHotel(sched,did)`

與既有 `coveringHotel(sched,did)`（今晚住哪，語意：入住日 < 今天 < 退房日）互補：

```js
// 今天早上從哪間住宿出發。跟 coveringHotel 的差別只有一個 <=：
// 退房日早上人還是從這裡出發的，要算進去；入住日當天本身則不算
// （那天早上从哪裡出發是「前一個住宿」的事，不是這一間）。
function morningHotel(sched,did){
  const n=dayNum(did);
  for(const [hdid,day] of Object.entries(sched||{})){
    if(dayNum(hdid)>=n)continue;
    for(const a of Object.values(day.acts||{})){
      if(a.cat!=='hotel'||!a.stay?.out)continue;
      if(n<=dayNum(a.stay.out))return a;
    }
  }
  return null;
}
```

两者都是唯讀查詢，`sched` 對任何一天都可各自獨立算出「早上從哪來」「晚上住哪去」，不需要额外狀態。

### 渲染層

`renderSched()` 組裝當天項目時：

1. `morningHotel` 存在 → 在真實活動陣列**最前面**插入一張唯讀卡：「🛏️ 從《飯店名》出發」
2. `coveringHotel` 存在 → 在真實活動陣列**最後面**插入一張唯讀卡：「🛏️ 今晚住《飯店名》」

唯讀卡沒有 `.act-handle`、沒有 `draggable`、沒有編輯/刪除按鈕；`data-aid` 用 `stay-in`/`stay-out` 這種不會撞到 Firebase push key 格式的前綴標記，跟真實活動的 `aid` 區隔開，避免被拖曳排序或編輯邏輯誤認成真的活動。

既有「相鄰兩點算距離」的 `legHtml`／`legKey`／`lastLegs` 快取機制原封不動複用：把陣列組成 `[morningHotelCard?, ...realActs, coveringHotelCard?]` 後，用跟現在完全一樣的 `legRow=(cur.geo&&nxt?.geo)?legHtml(cur.geo,nxt.geo):''` 邏輯算相鄰兩項的距離，不管兩端是卡片還是活動都一視同仁。OSRM 快取命中、直線 fallback、`約` 標示全部照舊生效。

`dayGeoActs()`（地圖用點位清單）比照在最前面補上 `morningHotel` 這一端（目前只有 `coveringHotel` 那端在最後面），`calcDayKm()` 直接受益，不用改動——它本來就是把 `dayGeoActs()` 回傳的相鄰點兩兩加總。

舊的 `lastLegToStay()` 被這套統一渲染取代，直接刪除；它原本要處理的「當天最後一筆活動到今晚住宿」現在是陣列最後一組相鄰配對，自動涵蓋。

### Edge case

- **住宿沒有座標**（地理編碼失敗或還沒查）：卡片照樣顯示飯店名稱，但不畫距離線——跟現有「兩端都要有座標才畫距離列」規則一致，不用直線硬湊數字。
- **當天 0 筆真實活動，且 `morningHotel` 跟 `coveringHotel` 是同一間**（整天沒排行程、只是連住）：只插入**一張**卡（顯示「🛏️ 今晚住《飯店名》」），不插兩張、也不畫一段原地折返的 0 公里距離線。判斷依據是兩者回傳的活動物件參照是否相同。
- **原本空行程日的「尚無活動」提示**：改成只有在連住宿卡都沒有時才顯示，否則「今晚住宿」卡會跟「尚無活動」同時出現，互相矛盾。

### 不受影響的部分

- `coveringHotel()` 本身不改，安全資訊／地圖定位基準（`dayBaseLatLng`）邏輯不變。
- 「住宿總整理」總覽頁（`renderOverview` 裡過濾 `a.cat==='hotel'` 那段）只讀真實活動，不受唯讀卡影響。
- Firebase 資料結構完全不變，這次改動純粹是渲染層。

## 測試

`_selftest()` 比照既有 `coveringHotel` 測項，加 `morningHotel` 邊界測試：
- 入住日當天不算（那天早上不是從這間出發）
- 退房日算（新行為，跟 `coveringHotel` 的差異點）
- 中間日算
- 入住日之前不算
- 沒有 `stay.out` 就不跨夜

四支各自跑一次。

## 部署

四支都是 Netlify 手動拖拉部署，commit 不等於上線，需個別手動部署。冰島版有版本號可核對；其餘三支目前沒有版本號機制（不在本次範圍內新增）。
