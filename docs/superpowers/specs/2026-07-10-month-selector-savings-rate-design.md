# 月份選單年份分組 + 年度結餘儲蓄率

## 背景

`finance-app/index.html` 的 `buildMonths()`（第 666-676 行）目前往回產生固定 24 個月的選項，是從「今天」往回推算，不是根據資料庫實際有資料的範圍。近期匯入了 2022-09 至今的歷史資料後，超過 24 個月的舊資料（2022-09～2024-07）雖然已經正確寫入、年度彙總抓得到，但月份下拉選單（`sel-exp`、`sel-inc`）裡完全沒有對應選項，使用者在「每月分析」找不到這些月份。

另外，收入頁「年度結餘」卡片（`id="balance-card-year"`，第 245-264 行）目前只顯示年度收入、年度支出、年度結餘三行，使用者想額外看到「儲蓄率」。

## 變更 1：月份選單改用年份分組

`buildMonths(id)` 改為往回產生 5 年份的選項（涵蓋範圍與既有 `buildYears()` 一致），每年用 `<optgroup>` 分組：

```js
function buildMonths(id) {
  const sel=document.getElementById(id);
  if(sel.options.length) return sel.value;
  const now=new Date();
  const nowYear=now.getFullYear(), nowMonth=now.getMonth();
  for(let yi=0;yi<5;yi++){
    const year=nowYear-yi;
    const group=document.createElement('optgroup');
    group.label=`${year}年`;
    const maxMonth=(yi===0)?nowMonth:11; // 今年只列到當月，往年列滿12個月
    for(let mi=maxMonth;mi>=0;mi--){
      const v=`${year}-${String(mi+1).padStart(2,'0')}`;
      const opt=document.createElement('option');
      opt.value=v; opt.textContent=v;
      group.appendChild(opt);
    }
    sel.appendChild(group);
  }
  return sel.value;
}
```

行為差異：
- 選項 `value` 格式仍是 `YYYY-MM`，不變。
- 所有讀取 `sel-exp`/`sel-inc` `.value` 的既有程式碼（`loadExpenses`、`loadIncome`、`deleteMonth` 等）完全不用修改。
- 下拉選單開啟後會依瀏覽器原生 `<optgroup>` 樣式顯示年份群組標籤（如「2026年」），組內是該年月份，由新到舊排列。
- 涵蓋範圍：往回 5 年（含今年），今年只列到當月為止，避免出現未來月份選項；往年列滿 1-12 月。

## 變更 2：年度結餘卡片新增儲蓄率

在 `loadYearlyBalance()` 函式（收入頁年度結餘的載入邏輯）算完 `bal-year-net` 之後，新增儲蓄率計算與顯示：

```js
const rateEl=document.getElementById('bal-year-rate');
if(s.total_income>0){
  const rate=(s.balance/s.total_income*100);
  rateEl.textContent=`儲蓄率 ${rate>=0?'+':''}${rate.toFixed(1)}%`;
  rateEl.style.color=rate>=0?'#4ade80':'#f87171';
} else {
  rateEl.textContent='儲蓄率 --';
  rateEl.style.color='#64748b';
}
```

對應 HTML：在 `balance-card-year` 卡片內、`bal-year-net` 那一行（第 260-263 行）之後新增一行：

```html
<div style="text-align:right;margin-top:4px">
  <span style="font-size:12px;color:#64748b" id="bal-year-rate">--</span>
</div>
```

公式：儲蓄率 = 年度結餘 ÷ 年度收入 × 100%。年度收入為 0 時顯示 `--`（避免除以 0），不套色。正數綠色、負數紅色，與既有結餘配色邏輯一致。

只加在年度結餘卡片，月度「本月結餘」卡片不變動。

## 錯誤處理

兩項變更都是既有函式內的擴充，沿用各自函式原本的 try/catch 範圍，不新增額外的錯誤路徑。

## 部署

純前端變更，只動 `finance-app/index.html`，push 到 monorepo `main` 分支後 Netlify 自動部署，不涉及後端。
