# Miller Notes Session Prompt

每次開始做 Miller 筆記前，將下方「貼入 Claude 的指令」複製貼入對話作為起始指令。

---

## 貼入 Claude 的指令

```
我要整理 Miller's Anesthesia 10th edition 的 Notion 筆記。
本 session 全程只用視覺法（PyMuPDF 渲染 PNG → Read 工具讀圖），絕對不用 page.get_text()。

每個 sub-page 用以下五區塊格式：

> Miller's Anesthesia 10th ed. Ch XX — 章節名稱, pp. XXXX–XXXX（PDF pp. XXXX–XXXX）

## 一、內文筆記
• 完整句子，一條一個概念。原文有因果 → 用「——」或「，因為」連接。
  - 子條目補充細節，不堆疊成段落。

## 二、圖表
（有表格 → 重建為 Notion table block）
（有流程圖/解剖圖 → 條列文字摘要核心訊息）
（無圖表 → 省略此區塊）

## 三、臨床重點
⚡ 臨床操作相關重點（有幾條寫幾條，不硬湊）

## 四、易考點
❓ 問題 → 答案（有幾條寫幾條，不硬湊）

## 五、常見陷阱
⚠️ 錯誤認知 → 正確觀念（若無明顯陷阱則省略）

規則：
- 因果說明只寫原文有的，不自行補充。
- 每頁建完立即 notion-fetch 驗證，發現問題立刻 replace_content 修正。
- 不要等全章完成再驗證。

請先告訴我：這章的 PDF 路徑是什麼？頁碼範圍是哪裡到哪裡？
```
