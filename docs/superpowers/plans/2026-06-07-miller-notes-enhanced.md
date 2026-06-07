# Miller Notes Enhanced Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 強化 Miller's Anesthesia → Notion 筆記 workflow，套用新的五區塊格式（條列內文、圖表重建、臨床重點、易考點、常見陷阱）。

**Architecture:** 無新增程式碼。交付物為（1）更新的 memory 檔案讓未來 session 自動套用新格式，（2）可複製貼上的 session 啟動 prompt 模板，（3）一頁實際 PDF 的 end-to-end 驗收。

**Tech Stack:** Claude MCP（notion-create-pages, notion-fetch, notion-update-page）、PyMuPDF、Python 3

---

## Task 1: 更新記憶檔案

**Files:**
- Modify: `/Users/wangyingyu/.claude/projects/-Users-wangyingyu-Library-Mobile-Documents-com-apple-CloudDocs-Jenna-agent/memory/feedback_notion_notes_format.md`
- Modify: `/Users/wangyingyu/.claude/projects/-Users-wangyingyu-Library-Mobile-Documents-com-apple-CloudDocs-Jenna-agent/memory/MEMORY.md`

- [ ] **Step 1: 讀取現有記憶檔案**

```bash
cat "/Users/wangyingyu/.claude/projects/-Users-wangyingyu-Library-Mobile-Documents-com-apple-CloudDocs-Jenna-agent/memory/feedback_notion_notes_format.md"
```

- [ ] **Step 2: 將 feedback_notion_notes_format.md 完整替換為新格式規範**

用 Write 工具將檔案改寫為以下內容（完整覆蓋）：

```markdown
---
name: feedback-notion-notes-format
description: 整理 Miller 麻醉教科書 Notion 筆記的完整規範，含五區塊格式、圖表處理原則與三類已知問題
metadata:
  type: feedback
---

## Sub-page 固定格式（五區塊）

每個 Notion sub-page 的 content 依序為：

```
> Miller's Anesthesia 10th ed. Ch XX — 章節名稱, pp. XXXX–XXXX（PDF pp. XXXX–XXXX）

## 一、內文筆記
• 完整句子，一條一個概念；原文有因果就用「——」或「，因為」連接。
  - 子條目補充細節，不堆疊成段落。

## 二、圖表
（有表格 → 重建為 Notion table block）
（有流程圖/解剖圖 → 條列文字摘要核心訊息）
（無圖表 → 省略此區塊）

## 三、臨床重點
⚡ 直接與臨床操作相關的一句話（有幾條寫幾條，不硬湊）

## 四、易考點
❓ 問題 → 答案（有幾條寫幾條，不硬湊）

## 五、常見陷阱
⚠️ 錯誤認知 → 正確觀念（若該頁無明顯陷阱則省略此區塊）
```

**Why:** 條列式比散文更好讀；圖表重建讓表格可搜尋；三個記憶輔助區塊幫助複習。

**How to apply:** 每次 notion-create-pages 時，content 依此五區塊順序輸出。

---

## 內文條列原則

- 每條一個完整句子，一個概念
- 原文有說明機制/原因 → 寫出來；原文只陳述事實 → 只寫事實，不自行補充
- 必要時加縮排子條說明細節

---

## 圖表處理原則

| 圖表類型 | 處理方式 |
|---------|---------|
| 表格（藥物比較、數值、分類） | 重建為 Notion table block |
| 流程圖、決策樹 | 條列文字摘要核心步驟/判斷點 |
| 解剖圖、示意圖 | 條列文字描述圖的關鍵訊息 |
| 無圖表的頁面 | 省略「二、圖表」區塊 |

**Why:** 流程圖/解剖圖 Notion block 無法還原；文字摘要比截圖更省 token 且不需 image hosting。

---

## PDF 讀取方式：必須用視覺（Vision）法

**正確做法：**
1. 用 PyMuPDF 把 PDF 頁面渲染為 PNG 圖片（zoom matrix 1.8x），存到 `/tmp/`
2. 用 `Read` 工具讀取圖片，Claude 以視覺方式合成筆記內容
3. **絕對不可以用 `page.get_text()` 抽取文字**

**Why:** Miller's 採雙欄排版，PyMuPDF 的文字抽取會把左欄、右欄、圖說、浮水印混在一起，產生大量亂碼。

```python
import fitz, os
doc = fitz.open('/path/to/Miller 10th.pdf')
os.makedirs('/tmp/ch_pages', exist_ok=True)
mat = fitz.Matrix(1.8, 1.8)
for page_num in range(start, end):
    page = doc[page_num]
    pix = page.get_pixmap(matrix=mat)
    pix.save(f'/tmp/ch_pages/page_{page_num}.png')
```

---

## 驗證清單（每頁建完後必須執行）

notion-fetch 該頁面後逐項確認：
- [ ] 第一行是否有章節來源標注
- [ ] 條列句子是否完整（不截斷）
- [ ] 有無 Unicode 形近錯字（貧血→谼血、躁動→誐動 等）
- [ ] 有無簡體字漏出（长→長 等）
- [ ] 圖表是否正確重建（若有）
- [ ] 記憶輔助區塊是否存在且格式正確

**How to apply:** 不要等全章完成再驗證。每頁建完立即 notion-fetch，發現問題用 notion-update-page + replace_content 修正。

---

## 三類已知問題

### 問題一：PyMuPDF context 污染
**症狀：** 筆記出現完全無意義的字串（「早射前時間較短」「雨安」等）。
**原因：** 同 session 曾用 page.get_text() 抽過文字，亂碼進入 context。
**對策：** 全新 session 只用視覺法；若已污染，開新 session 重寫。

### 問題二：LLM Unicode 字符混淆
**症狀：** 個別字符被形近錯字取代（貧血→谼血、鎮痛→鑑瘻痛、长時間 等）。
**原因：** Claude 生成長串中文 JSON 時偶爾輸出碼位鄰近的錯誤字符。
**對策：** 每頁建完立即 notion-fetch 驗證；發現錯字用 replace_content 重寫。

### 問題三：已封存頁面無法編輯
**症狀：** notion-update-page 回傳 "Can't edit page on block with an archived ancestor."
**對策：** 在有效父頁面下重新 notion-create-pages 建立全新頁面。
```

- [ ] **Step 3: 確認 MEMORY.md index 條目描述是否需要更新**

讀取 MEMORY.md，找到 `feedback_notion_notes_format.md` 那行。若描述仍為舊版，更新為：

```
- [Notion 筆記格式與亂碼防範](feedback_notion_notes_format.md) — 五區塊格式（條列內文/圖表/臨床重點/易考點/陷阱）、圖表處理原則、三類已知問題
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add -A
git commit -m "feat: update miller notes memory to new 5-block format"
```

---

## Task 2: 建立 Session 啟動 Prompt 模板

**Files:**
- Create: `docs/miller-notes-session-prompt.md`

這個檔案是每次開始做 Miller 筆記前，貼給 Claude 的 system-level 指令。

- [ ] **Step 1: 建立模板檔案**

用 Write 工具建立 `docs/miller-notes-session-prompt.md`，內容如下：

````markdown
# Miller Notes Session Prompt

每次開始做 Miller 筆記前，將以下內容貼入對話作為起始指令。

---

## 貼入 Claude 的指令

```
我要整理 Miller's Anesthesia 10th edition 的 Notion 筆記。
本 session 全程只用視覺法（PyMuPDF 渲染 PNG → Read 工具讀圖），絕對不用 page.get_text()。

每個 sub-page 用以下五區塊格式：

> Miller's Anesthesia 10th ed. Ch XX — 章節名稱, pp. XXXX–XXXX（PDF pp. XXXX–XXXX）

## 一、內文筆記
• 完整句子，一條一個概念。原文有因果 → 用「——」或「，因為」連接。
  - 子條目補充細節。

## 二、圖表
（有表格 → 重建為 Notion table block；有流程圖/解剖圖 → 條列文字摘要核心訊息；無圖表 → 省略此區塊）

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
````

- [ ] **Step 2: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git add docs/miller-notes-session-prompt.md
git commit -m "feat: add miller notes session starter prompt template"
```

---

## Task 3: End-to-End 驗收（一頁實際 PDF）

這個 task 是手動驗收，確認新格式在真實頁面上運作正常。

**前置條件：** Task 1 & 2 完成，有 Miller 10th edition PDF 可存取。

- [ ] **Step 1: 渲染一頁 PDF 為 PNG**

```python
import fitz, os
doc = fitz.open('/path/to/Miller 10th.pdf')  # 替換為實際路徑
os.makedirs('/tmp/miller_test', exist_ok=True)
mat = fitz.Matrix(1.8, 1.8)
page = doc[50]  # 任選一頁，最好選有表格的頁面
pix = page.get_pixmap(matrix=mat)
pix.save('/tmp/miller_test/test_page.png')
print("Done:", pix.width, "x", pix.height)
```

執行：`python3 /tmp/render_test.py`
預期輸出：`Done: 1587 x 2052`（或類似尺寸）

- [ ] **Step 2: 用 Read 工具讀取圖片，確認 Claude 能正確辨識內容**

在 Claude Code 對話中執行：
```
Read /tmp/miller_test/test_page.png
```
預期：Claude 能描述頁面的文字內容與圖表結構，無亂碼。

- [ ] **Step 3: 用新格式建立一個測試 Notion sub-page**

在已知的 Notion 測試頁面下（或正式的 Miller 筆記父頁面下）執行 notion-create-pages，套用五區塊格式。

- [ ] **Step 4: notion-fetch 驗證輸出**

執行 notion-fetch 讀取剛建立的頁面，逐項確認驗證清單：
- 第一行有章節來源標注 ✓
- 條列句子完整不截斷 ✓
- 無 Unicode 形近錯字 ✓
- 無簡體字漏出 ✓
- 圖表若有則已重建 ✓
- 記憶輔助三區塊存在且格式正確 ✓

- [ ] **Step 5: 若驗證通過，刪除測試頁面（或保留作為範本）**

- [ ] **Step 6: Commit 驗收結果記錄（選擇性）**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
git commit -m "chore: miller notes enhanced format validated end-to-end" --allow-empty
```
