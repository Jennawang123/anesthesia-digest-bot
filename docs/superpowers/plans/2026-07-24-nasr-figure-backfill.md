# Nasr 第二版圖表回填小兒心臟學筆記 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Nasr《The Pediatric Cardiac Anesthesia Handbook》第二版的 139 張 Figure 抽成 PNG，依章號對照表插入 Notion「小兒心臟學讀書會（Park's）」系列既有筆記的對應小節。

**Architecture:** 三階段管線，每階段產出可在進下一步前檢查。① 抽圖為純本地確定性運算（無網路、無 token），以 raster 圖框直接裁切；② 對應為本地查表；③ 上傳沿用 Miller 既有的 `upload_figures.py`，一行都不改。

**Tech Stack:** Python 3（`python3`，macOS 無 `python`）、PyMuPDF（`fitz`）、`requests`、pytest 9.0.3。

**設計文件：** `docs/superpowers/specs/2026-07-24-nasr-figure-extraction-design.md`

---

## File Structure

| 檔案 | 責任 |
|---|---|
| `scripts/extract_figures_raster.py`（新增） | 階段①。caption 偵測、raster 過濾、配對、聯集、裁切、manifest、contact sheet |
| `nasr_ed2_figure_map.json`（新增） | 章號 → Notion page id 對照表（資料，非程式碼） |
| `scripts/map_nasr_figures.py`（新增） | 階段②-1。依對照表填 `target_page_id` |
| `scripts/dump_nasr_sections.py`（新增） | 階段②-2。列出目標頁的小節與待歸位的圖，指派小節的工作底稿 |
| `scripts/set_nasr_sections.py`（新增） | 階段②-3。把指派好的 `target_section` / `target_page_id` 寫回 manifest |
| `tests/test_extract_figures_raster.py`（新增） | 抽圖純函式的單元測試 |
| `tests/test_map_nasr_figures.py`（新增） | 對照表查表的單元測試 |
| `scripts/upload_figures.py`（**不修改**） | 階段③。既有腳本，manifest 格式相容 |
| `scripts/extract_figures.py`（**不修改**） | Miller 專用。被 import 重用 `parse_pages` / `body_font` / `text_blocks` / `write_contact_sheet`，以及 fallback 用的 `detect_columns` / `figure_rect` |

**重用而非複製：** `extract_figures.py` 的 `parse_pages`、`body_font`、`text_blocks`、`write_contact_sheet` 與書本無關，直接 import。`figure_rect` 與 `detect_columns` 內建 Miller 的版面假設，只在幾何 fallback 用（6 張，產物預設不納入）。不重用 `book_page_number`——它的 regex 限 3–4 位數，Nasr 的頁碼是 1–3 位。

**輸出目錄：** `figures/nasr/`。`figures/` 已在 `.gitignore`，PNG 與 manifest 不進版控。

---

## Task 1: 測試骨架與 raster 過濾

**Files:**
- Create: `tests/test_extract_figures_raster.py`
- Create: `scripts/extract_figures_raster.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_extract_figures_raster.py`：

```python
"""extract_figures_raster 的純幾何函式測試。

全部用合成的 fitz.Rect，不開 PDF —— 幾何邏輯與檔案無關，
測試要能在沒有那本 45MB PDF 的機器上跑。
"""
import sys
from pathlib import Path

import fitz
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from extract_figures_raster import usable_rasters  # noqa: E402

PAGE = fitz.Rect(0, 0, 480.5, 720)


class FakePage:
    """只提供 usable_rasters 需要的介面：rect、get_images、get_image_rects。"""

    def __init__(self, rects):
        self._rects = rects
        self.rect = PAGE

    def get_images(self):
        return [(i,) for i in range(len(self._rects))]

    def get_image_rects(self, xref):
        return [self._rects[xref]]


def test_濾掉整頁背景層():
    page = FakePage([
        fitz.Rect(0, 0, 480.5, 720),      # 背景層
        fitz.Rect(0, 0, 480.5, 720),      # 第二層背景
        fitz.Rect(65, 72, 352, 491),      # 真正的圖
    ])
    assert usable_rasters(page) == [fitz.Rect(65, 72, 352, 491)]


def test_濾掉過小的碎塊():
    page = FakePage([
        fitz.Rect(60, 60, 75, 75),        # 15x15，太小
        fitz.Rect(54, 73, 295, 230),      # 真正的圖
    ])
    assert usable_rasters(page) == [fitz.Rect(54, 73, 295, 230)]


def test_沒有可用圖時回傳空清單():
    assert usable_rasters(FakePage([fitz.Rect(0, 0, 480.5, 720)])) == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent" && python3 -m pytest tests/test_extract_figures_raster.py -v`

Expected: FAIL，`ModuleNotFoundError: No module named 'extract_figures_raster'`

- [ ] **Step 3: 寫最小實作**

建立 `scripts/extract_figures_raster.py`：

```python
#!/usr/bin/env python3
"""依 raster 圖框抽取 Nasr ed2 的 figure。

與 extract_figures.py（Miller 專用）的前提相反：Nasr 第二版全書向量繪圖
物件為 0，每張圖都是完整的內嵌 raster，圖框本身就是精確的裁切邊界，
不需要 Miller 那套「從 caption 往上找內文邊界」的啟發式。

用法：
    python3 scripts/extract_figures_raster.py <PDF> <輸出目錄> [--chapters 8 9] [--dpi 200]
"""

import fitz

# 每頁固定有兩張整頁尺寸的背景層，不是圖
BG_MIN_W, BG_MIN_H = 440, 640
# 小於這個尺寸的是裝飾碎塊（項目符號、logo）
MIN_RASTER = 20


def usable_rasters(page):
    """回傳頁面上真正屬於圖的 raster 框，濾掉背景層與碎塊。"""
    out = []
    for img in page.get_images():
        for r in page.get_image_rects(img[0]):
            if r.width > BG_MIN_W and r.height > BG_MIN_H:
                continue
            if r.width < MIN_RASTER or r.height < MIN_RASTER:
                continue
            out.append(r)
    return out
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest tests/test_extract_figures_raster.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_figures_raster.py tests/test_extract_figures_raster.py
git commit -m "feat: Nasr 抽圖的 raster 過濾，濾除整頁背景層與碎塊"
```

---

## Task 2: caption 偵測

Nasr 的圖說格式是 `Figure 8.1 …`（Miller 是 `Fig. 28.3`）。內文交叉引用可能出現在 block 開頭（實測 idx98 有一處「Figure 8.1. Figures 8.2-8.9 summarize…」），用內文字體排除——真正的圖說不是內文字體。

**Files:**
- Modify: `scripts/extract_figures_raster.py`
- Modify: `tests/test_extract_figures_raster.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_extract_figures_raster.py` 的 import 行加入 `find_captions`：

```python
from extract_figures_raster import find_captions, usable_rasters  # noqa: E402
```

並在檔案末尾追加：

```python
def block(text, rect, is_body=False):
    """模擬 extract_figures.text_blocks() 的輸出格式。"""
    return {"text": text, "rect": fitz.Rect(*rect), "is_body": is_body}


def test_抓出圖說並拆出章號與編號():
    caps = find_captions([
        block("Figure 8.3 Subxiphoid short-axis sweep.", (54, 301, 445, 330)),
    ])
    assert len(caps) == 1
    assert caps[0]["fig_id"] == "8.3"
    assert caps[0]["chapter"] == 8
    assert caps[0]["rect"] == fitz.Rect(54, 301, 445, 330)


def test_排除內文字體的交叉引用():
    caps = find_captions([
        block("Figure 8.1. Figures 8.2-8.9 summarize the images.",
              (60, 213, 440, 240), is_body=True),
        block("Figure 8.1 Transducer locations for standard TTE windows.",
              (60, 69, 440, 100)),
    ])
    assert [c["fig_id"] for c in caps] == ["8.1"]
    assert caps[0]["rect"].y0 == 69


def test_複數形的Figures不算圖說():
    assert find_captions([block("Figures 2.1 and 2.2 illustrate this.",
                                (60, 100, 440, 130))]) == []


def test_Table與Box不算圖說():
    assert find_captions([
        block("Table 1.1 Cardiovascular embryologic structure.", (54, 69, 377, 82)),
        block("Box 3.2 Preoperative checklist.", (54, 200, 377, 220)),
    ]) == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_extract_figures_raster.py -v`
Expected: FAIL，`ImportError: cannot import name 'find_captions'`

- [ ] **Step 3: 寫實作**

在 `scripts/extract_figures_raster.py` 的 `import fitz` 上方加入 `import re`，並在 `MIN_RASTER` 常數後加入：

```python
# Nasr 用「Figure 8.1」全字，Miller 用「Fig. 28.3」。複數形 Figures 因為
# 「Figure」後面接的是 s 而非空白或數字，天然不會命中。
CAPTION_RE = re.compile(r"^Figure\s*(\d+)\.(\d+)")
```

在 `usable_rasters` 之後加入：

```python
def find_captions(blocks):
    """從 text block 找出圖說。

    內文裡的交叉引用偶爾會出現在 block 開頭（實測 idx98 的
    「Figure 8.1. Figures 8.2-8.9 summarize…」），它用的是內文字體，
    真正的圖說不是。靠字體排除，實測全書零誤判。
    """
    out = []
    for b in blocks:
        m = CAPTION_RE.match(b["text"])
        if not m or b["is_body"]:
            continue
        out.append({
            "fig_id": f"{m.group(1)}.{m.group(2)}",
            "chapter": int(m.group(1)),
            "rect": b["rect"],
            "text": b["text"],
        })
    return out
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest tests/test_extract_figures_raster.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_figures_raster.py tests/test_extract_figures_raster.py
git commit -m "feat: Nasr 圖說偵測，以內文字體排除交叉引用"
```

---

## Task 3: caption↔raster 配對

Nasr 的 caption 有兩種擺法：跨欄大圖的 caption 在圖**下方**，單欄小圖的 caption 排在**旁邊那一欄同高度**。同頁有多個 caption 時，每個 raster 只能歸給一個 caption。

**Files:**
- Modify: `scripts/extract_figures_raster.py`
- Modify: `tests/test_extract_figures_raster.py`

- [ ] **Step 1: 寫失敗測試**

import 行改為：

```python
from extract_figures_raster import assign_rasters, find_captions, usable_rasters  # noqa: E402
```

檔案末尾追加：

```python
def cap(fig_id, rect):
    return {"fig_id": fig_id, "chapter": int(fig_id.split(".")[0]),
            "rect": fitz.Rect(*rect), "text": f"Figure {fig_id} …"}


def test_圖在caption上方():
    # idx21 實測：圖 (65,72,352,491)、圖說 (60,499,440,530)
    got = assign_rasters([cap("1.1", (60, 499, 440, 530))],
                         [fitz.Rect(65, 72, 352, 491)])
    assert got["1.1"] == [fitz.Rect(65, 72, 352, 491)]


def test_圖在旁欄同高():
    # idx26 實測：圖在左欄 (54,73,295,230)、圖說在右欄頂 (307,69,445,101)
    got = assign_rasters([cap("2.1", (307, 69, 445, 101))],
                         [fitz.Rect(54, 73, 295, 230)])
    assert got["2.1"] == [fitz.Rect(54, 73, 295, 230)]


def test_多panel窄圖全部歸給同一個caption():
    # idx168 實測型態：Fig 15.1 有 8 個 panel，每個只有 59-73pt 寬，
    # 遠小於 385pt 的圖說寬度。門檻若相對圖說寬度，這些 panel 會全數落空。
    rects = [fitz.Rect(60, 83, 119, 165),
             fitz.Rect(139, 73, 205, 162),
             fitz.Rect(228, 73, 300, 278)]
    got = assign_rasters([cap("15.1", (54, 286, 439, 327))], rects)
    assert sorted(got["15.1"], key=lambda r: (r.y0, r.x0)) == \
        sorted(rects, key=lambda r: (r.y0, r.x0))


def test_寬圖配窄圖說也要配對成功():
    # 反向情形：圖比圖說寬。門檻若要求 raster 落在圖說跨距內，這種會落空。
    got = assign_rasters([cap("12.1", (60, 400, 200, 430))],
                         [fitz.Rect(55, 90, 445, 390)])
    assert got["12.1"] == [fitz.Rect(55, 90, 445, 390)]


def test_距離過遠的碎塊不配對():
    # idx88 實測：Fig 7.3 的圖說在 y=579，頁頂有個 23pt 寬的裝飾圖示，
    # 水平雖然對得上，但隔了大半頁，不該被當成這張圖的內容。
    got = assign_rasters([cap("7.3", (60, 579, 434, 600))],
                         [fitz.Rect(71, 77, 94, 105)])
    assert got["7.3"] == []


def test_同頁兩個caption各自取到自己的圖():
    # idx100 實測型態：上下各一組圖說
    got = assign_rasters(
        [cap("8.3", (54, 301, 445, 330)), cap("8.4", (54, 646, 445, 675))],
        [fitz.Rect(60, 80, 440, 295), fitz.Rect(60, 380, 440, 640)])
    assert got["8.3"] == [fitz.Rect(60, 80, 440, 295)]
    assert got["8.4"] == [fitz.Rect(60, 380, 440, 640)]


def test_沒有可配對的圖時回傳空清單():
    assert assign_rasters([cap("7.2", (54, 69, 445, 100))], []) == {"7.2": []}
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_extract_figures_raster.py -v`
Expected: FAIL，`ImportError: cannot import name 'assign_rasters'`

- [ ] **Step 3: 寫實作**

在 `CAPTION_RE` 後加入常數：

```python
# 配對時要求的最小重疊比例
MIN_OVERLAP = 0.3
# 圖與圖說的垂直間隙上限（頁高的比例）。超過就不是同一張圖，
# 用來擋掉頁頂的裝飾圖示被下方的圖說認領。
MAX_GAP = 0.6
```

在 `find_captions` 之後加入：

```python
def _overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _score(cap_rect, r, page_height):
    """caption 與 raster 的配對距離；不成立回傳 None。

    兩種擺法各判一次：
      下方型 —— 圖在 caption 上方，水平方向重疊夠多，距離取垂直間隙。
      旁欄型 —— 圖與 caption 垂直方向重疊夠多、水平不重疊，距離取水平間隙。

    重疊門檻一律相對於「較窄／較矮的那一方」。這點踩過兩次：門檻相對
    caption 寬度時，Fig 15.1 的 8 個窄 panel 全數落空；改成要求 raster
    落在 caption 跨距內時，換成寬圖配窄圖說的 Fig 9.1、12.1、27.7、31.6
    落空。相對較窄一方兩種情形都成立。
    """
    if r.y1 <= cap_rect.y0 + 2:
        h = _overlap(r.x0, r.x1, cap_rect.x0, cap_rect.x1)
        if h > MIN_OVERLAP * min(r.width, cap_rect.width):
            gap = cap_rect.y0 - r.y1
            if gap < MAX_GAP * page_height:
                return gap

    v = _overlap(r.y0, r.y1, cap_rect.y0, cap_rect.y1)
    if v > MIN_OVERLAP * min(r.height, cap_rect.height):
        if _overlap(r.x0, r.x1, cap_rect.x0, cap_rect.x1) <= 0:
            return abs(cap_rect.x0 - r.x1) if r.x1 <= cap_rect.x0 \
                else abs(r.x0 - cap_rect.x1)
    return None


def assign_rasters(captions, rasters, page_height=720):
    """把 raster 分派給 caption，回傳 {fig_id: [rect, ...]}。

    每個 raster 只歸給距離最近的那個 caption —— 同頁有兩三個圖說時
    （實測 22 頁），不這樣做會讓上下兩組圖被同一個圖說吃掉。
    多 panel 圖則是同一個 caption 收到多個 rect，稍後取聯集。
    """
    out = {c["fig_id"]: [] for c in captions}
    for r in rasters:
        best, best_score = None, None
        for c in captions:
            s = _score(c["rect"], r, page_height)
            if s is None:
                continue
            if best_score is None or s < best_score:
                best, best_score = c["fig_id"], s
        if best is not None:
            out[best].append(r)
    return out
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest tests/test_extract_figures_raster.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_figures_raster.py tests/test_extract_figures_raster.py
git commit -m "feat: caption 與 raster 配對，支援圖下方與旁欄同高兩種擺法"
```

---

## Task 4: 裁切框聯集與書本頁碼

**Files:**
- Modify: `scripts/extract_figures_raster.py`
- Modify: `tests/test_extract_figures_raster.py`

- [ ] **Step 1: 寫失敗測試**

import 行改為：

```python
from extract_figures_raster import (assign_rasters, book_page, crop_rect,  # noqa: E402
                                    fill_book_pages, find_captions, usable_rasters)
```

檔案末尾追加：

```python
def test_聯集後加留白且不超出頁面():
    got = crop_rect([fitz.Rect(54, 80, 230, 200), fitz.Rect(250, 90, 440, 210)], PAGE)
    assert got == fitz.Rect(48, 74, 446, 216)


def test_留白不會超出頁面邊界():
    # 加了 PAD 之後 (-4,-4,476,721)，四邊都要夾回頁面範圍內
    got = crop_rect([fitz.Rect(2, 2, 470, 715)], PAGE)
    assert got == fitz.Rect(0, 0, 476, 720)


def test_偶數頁頁碼在前():
    assert book_page([block("10 The Pediatric Cardiac Anesthesia Handbook",
                            (54, 44, 300, 56))]) == 10


def test_奇數頁頁碼在後():
    assert book_page([block("Cardiovascular Development 5", (300, 44, 445, 56))]) == 5


def test_頁眉位置過低不算頁碼():
    # 整頁圖的第一個 block 是圖說，不是頁眉
    assert book_page([block("Figure 8.3 Subxiphoid sweep.", (54, 301, 445, 330))]) is None


def test_以章內位移回填缺漏的書本頁碼():
    figs = [
        {"fig_id": "8.2", "nasr_chapter": 8, "pdf_page": 99, "book_page": 86},
        {"fig_id": "8.3", "nasr_chapter": 8, "pdf_page": 100, "book_page": None},
        {"fig_id": "8.4", "nasr_chapter": 8, "pdf_page": 100, "book_page": None},
        {"fig_id": "2.1", "nasr_chapter": 2, "pdf_page": 26, "book_page": 10},
    ]
    fill_book_pages(figs)
    assert [f["book_page"] for f in figs] == [86, 87, 87, 10]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_extract_figures_raster.py -v`
Expected: FAIL，`ImportError: cannot import name 'crop_rect'`

- [ ] **Step 3: 寫實作**

在 `MIN_OVERLAP` 後加入常數：

```python
# 裁切留白。Nasr 的 raster 框已經很貼合，不需要 Miller 那麼寬的 10pt
PAD = 6
# 頁眉的 y 上限；超過這個位置的第一個 block 不是頁眉
HEAD_Y = 60
PAGE_NUM_RE = re.compile(r"^\d{1,3}$")
```

在 `assign_rasters` 之後加入：

```python
def crop_rect(rects, page_rect):
    """多個 rect 取聯集，四周加留白，並夾在頁面範圍內。"""
    box = rects[0]
    for r in rects[1:]:
        box = box | r
    return fitz.Rect(max(page_rect.x0, box.x0 - PAD),
                     max(page_rect.y0, box.y0 - PAD),
                     min(page_rect.x1, box.x1 + PAD),
                     min(page_rect.y1, box.y1 + PAD))


def book_page(blocks):
    """從頁眉取印刷頁碼。

    偶數頁是「10 The Pediatric Cardiac Anesthesia Handbook」（頁碼在前），
    奇數頁是「Cardiovascular Development 5」（頁碼在後）。整頁圖與章首頁
    沒有頁眉，回傳 None，稍後用章內位移回填。
    """
    if not blocks or blocks[0]["rect"].y0 >= HEAD_Y:
        return None
    toks = blocks[0]["text"].split()
    for t in (toks[0], toks[-1]) if toks else ():
        if PAGE_NUM_RE.match(t):
            return int(t)
    return None


def fill_book_pages(figs):
    """用章內位移回填抓不到頁眉的書本頁碼。

    pdf_page 與 book_page 的位移逐章漂移（實測 Ch1 +16 遞減到 Ch37 −3，
    因 Part 分隔頁而變動），不能全書套單一公式，但同一章內唯一且恆定。
    """
    seen = {}
    for f in figs:
        if f["book_page"]:
            seen.setdefault(f["nasr_chapter"], []).append(
                f["pdf_page"] - f["book_page"])
    offset = {ch: max(set(v), key=v.count) for ch, v in seen.items()}
    for f in figs:
        if not f["book_page"] and f["nasr_chapter"] in offset:
            f["book_page"] = f["pdf_page"] - offset[f["nasr_chapter"]]
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest tests/test_extract_figures_raster.py -v`
Expected: 20 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_figures_raster.py tests/test_extract_figures_raster.py
git commit -m "feat: 裁切框聯集與書本頁碼偵測，含章內位移回填"
```

---

## Task 5: 抽圖主流程與 CLI

把前四個 task 的零件串成可執行的腳本：逐頁掃 caption、配對、跨頁 fallback、輸出 PNG 與 manifest、產 contact sheet。

**Files:**
- Modify: `scripts/extract_figures_raster.py`

- [ ] **Step 1: 加入主流程**

在 `scripts/extract_figures_raster.py` 檔首的 import 區塊補上：

```python
import argparse
import json
from pathlib import Path

from extract_figures import (body_font, detect_columns, figure_rect, parse_pages,
                             text_blocks, write_contact_sheet)
```

並在 `PAGE_NUM_RE` 後加入：

```python
# 聯集後超過版心這個倍數視為可疑，可能把鄰圖也吃進來了
OVERSIZE = 1.2
# 幾何 fallback 裁出的高度低於這個值視為失敗
MIN_PLAUSIBLE_HEIGHT = 40
```

在 `fill_book_pages` 之後加入：

```python
def column_of(page_rect, cap_rect):
    mid = page_rect.width / 2
    if cap_rect.width > 0.7 * (page_rect.width - 72):
        return "span"
    return "left" if cap_rect.x1 < mid + 20 else "right"


def extract(pdf_path, out_dir, dpi, chapters=None):
    doc = fitz.open(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pages = parse_pages(doc)
    body = body_font(pages)
    cols = detect_columns(pages, body)

    blocks_by_page = [text_blocks(pages[i], body) for i in range(doc.page_count)]
    rasters_by_page = [usable_rasters(doc[i]) for i in range(doc.page_count)]

    manifest = []
    for pno in range(doc.page_count):
        caps = find_captions(blocks_by_page[pno])
        if chapters:
            caps = [c for c in caps if c["chapter"] in chapters]
        if not caps:
            continue

        page_rect = doc[pno].rect
        # 分派時要看該頁「所有」圖說，不能只看 --chapters 篩選後的那些，
        # 否則同頁另一章的圖會被誤認領。篩選只作用在輸出。
        assigned = assign_rasters(find_captions(blocks_by_page[pno]),
                                  rasters_by_page[pno], page_rect.height)
        for c in caps:
            rects = assigned[c["fig_id"]]
            suspect = []

            entry = {
                "fig_id": c["fig_id"],
                "nasr_chapter": c["chapter"],
                "pdf_page": pno,
                "book_page": book_page(blocks_by_page[pno]),
                "caption": c["text"],
                "png": None,
                "bbox": None,
                "panels": len(rects),
                "column": column_of(page_rect, c["rect"]),
                "suspect": suspect,
                "include": True,
                "target_page_id": None,
                "target_section": None,
                "uploaded_block_id": None,
            }

            if rects:
                box = crop_rect(rects, page_rect)
                if box.width > OVERSIZE * page_rect.width or \
                        box.height > OVERSIZE * page_rect.height:
                    suspect.append("oversized_union")
            else:
                # 該頁沒有可用 raster —— 這張圖被烙進整頁尺寸的背景掃描層，
                # 圖框隔離不出來。退回 Miller 那套 caption 往上裁的幾何法。
                # 實測品質不可信（Fig 11.4 裁出的是整張表格加頁眉），因此
                # 一律標記並預設不納入，由使用者在 contact sheet 上逐張認可。
                box = figure_rect(doc[pno], {"rect": c["rect"]},
                                  blocks_by_page[pno], cols)
                suspect.append("geometric_fallback")
                entry["include"] = False
                if box.height < MIN_PLAUSIBLE_HEIGHT or box.width <= 0:
                    suspect.append("crop_failed")
                    manifest.append(entry)
                    continue

            name = f"fig-{c['fig_id'].replace('.', '-')}_p{pno}.png"
            doc[pno].get_pixmap(clip=box, dpi=dpi).save(out_dir / name)
            entry["png"] = name
            entry["bbox"] = [round(v, 1) for v in (box.x0, box.y0, box.x1, box.y1)]
            manifest.append(entry)

    fill_book_pages(manifest)
    manifest.sort(key=lambda f: (f["nasr_chapter"],
                                 int(f["fig_id"].split(".")[1])))
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # contact sheet 只放實際產出的圖；crop_failed 沒有檔案，只留在 manifest
    write_contact_sheet(out_dir, [f for f in manifest if f["png"]],
                        Path(pdf_path).stem)
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("out_dir")
    ap.add_argument("--chapters", type=int, nargs="+",
                    help="只抽指定章號，省略則全書")
    ap.add_argument("--dpi", type=int, default=200)
    a = ap.parse_args()

    m = extract(a.pdf, a.out_dir, a.dpi, set(a.chapters) if a.chapters else None)
    print(f"抽出 {sum(1 for f in m if f['png'])} 張圖 → {a.out_dir}")
    for f in m:
        if f["suspect"]:
            print(f"  ⚠ Fig {f['fig_id']} (PDF idx{f['pdf_page']}): "
                  f"{' '.join(f['suspect'])}")
```

- [ ] **Step 2: 確認既有測試仍通過**

Run: `python3 -m pytest tests/test_extract_figures_raster.py -v`
Expected: 20 passed（純函式未動）

- [ ] **Step 3: 對真實 PDF 跑全書，驗證總數**

Run:
```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
python3 scripts/extract_figures_raster.py \
  ~/Desktop/"pediatric cardiac handbook TEE.pdf" figures/nasr-all --dpi 100
```

Expected: 印出 `抽出 139 張圖 → figures/nasr-all`，並列出 6 筆 `geometric_fallback`（Fig 7.2、7.3、11.2、11.4、11.5、11.9）。

驗證 manifest 總筆數為 139：

```bash
python3 -c "
import collections, json
m = json.load(open('figures/nasr-all/manifest.json'))
print('總筆數', len(m))
print('有 PNG', sum(1 for f in m if f['png']))
print('預設納入', sum(1 for f in m if f['include']))
print('geometric_fallback', [f['fig_id'] for f in m if 'geometric_fallback' in f['suspect']])
print('缺書頁碼', [f['fig_id'] for f in m if not f['book_page']])
print('Ch8 張數', sum(1 for f in m if f['nasr_chapter'] == 8))
print('panel 分布', collections.Counter(f['panels'] for f in m if f['png']))
"
```

Expected:
```
總筆數 139
有 PNG 139
預設納入 133
geometric_fallback ['7.2', '7.3', '11.2', '11.4', '11.5', '11.9']
缺書頁碼 []
Ch8 張數 11
panel 分布 Counter({1: 93, 2: 20, 3: 7, 4: 4, 5: 3, 6: 3, 7: 2, 8: 1})
```

若總筆數不是 139，停下來比對 spec 的「caption 的辨識」一節再排查，不要調參數硬湊。

- [ ] **Step 4: 清掉驗證用的暫存輸出**

Run: `rm -rf figures/nasr-all`

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_figures_raster.py
git commit -m "feat: Nasr 抽圖主流程與 CLI，支援 --chapters 分章抽取"
```

---

## Task 6: 章號→Notion 頁對照表

**Files:**
- Create: `nasr_ed2_figure_map.json`

- [ ] **Step 1: 建立對照表**

內容取自 spec「章號→Notion 頁對照表」一節。建立 `nasr_ed2_figure_map.json`：

```json
{
  "description": "Nasr ed2 章號 → 小兒心臟學讀書會 Notion 頁對照表。供 map_nasr_figures.py 查表填 target_page_id。split=true 的章需逐圖分派，由 set_nasr_sections.py 指定。",
  "source_pdf": "~/Desktop/pediatric cardiac handbook TEE.pdf",
  "spec": "docs/superpowers/specs/2026-07-24-nasr-figure-extraction-design.md",
  "chapters": {
    "1": {"title": "Cardiovascular Development", "figures": 1, "notion_title": "正常心臟解剖", "notion_page_id": "3a1e77f4-b1f0-81d1-bcab-c92324b4098a"},
    "2": {"title": "Important Concepts in CHD", "figures": 6, "notion_title": "4 types of lesion", "notion_page_id": "3a1e77f4-b1f0-813d-9432-dc883d83a125", "user_edited": true},
    "4": {"title": "Intraoperative Management", "figures": 1, "notion_title": "術中管理", "notion_page_id": "3a2e77f4-b1f0-810b-aa94-f7ed16a667c9"},
    "5": {"title": "Developmental Hemostasis and PBM", "figures": 3, "notion_title": "Developmental Hemostasis 與 PBM", "notion_page_id": "3a4e77f4-b1f0-81e6-952c-f3e263f5dfb2"},
    "6": {"title": "Interpretation of Cardiac Catheterization Data", "figures": 5, "notion_title": "心導管數據判讀", "notion_page_id": "3a2e77f4-b1f0-8120-9461-f9fba4666931"},
    "7": {"title": "Management of Cardiopulmonary Bypass", "figures": 9, "notion_title": "體外循環", "notion_page_id": "3a2e77f4-b1f0-81bc-a7ce-f41fdec3abcf"},
    "8": {"title": "Echocardiography", "figures": 11, "notion_title": "Echocardiography（TEE 完整切面與 segmental 判讀）", "notion_page_id": "3a4e77f4-b1f0-8137-8413-d0fcd88b23f6"},
    "9": {"title": "Risk Scoring Systems", "figures": 1, "notion_title": "Risk Scoring Systems", "notion_page_id": "3a4e77f4-b1f0-8172-be57-f184937d24d3"},
    "10": {"title": "Mechanical Circulatory Support", "figures": 10, "notion_title": "機械輔助裝置（ECMO/VAD）", "notion_page_id": "3a2e77f4-b1f0-81ab-ad38-dac1a21a9d8d"},
    "11": {"title": "Postoperative Cardiac Intensive Care Unit Care", "figures": 9, "notion_title": "Postoperative CICU Care", "notion_page_id": "3a4e77f4-b1f0-81e1-b6cd-ce08ac9c7721"},
    "12": {"title": "Patent Ductus Arteriosus", "figures": 1, "notion_title": "PDA", "notion_page_id": "3a1e77f4-b1f0-817a-9aea-e8105c704aab"},
    "13": {"title": "Aortopulmonary Window", "figures": 1, "notion_title": "Ch12 AP Window", "notion_page_id": "3a2e77f4-b1f0-81e0-be2d-e0a5a040fd3c"},
    "14": {"title": "Coarctation of the Aorta", "figures": 4, "notion_title": "CoA", "notion_page_id": "3a1e77f4-b1f0-818f-b6d1-eef636346de0"},
    "15": {"title": "Atrial Septal Defect", "figures": 4, "notion_title": "ASD", "notion_page_id": "3a1e77f4-b1f0-81a6-bded-f7e00e25be07"},
    "16": {"title": "Ventricular Septal Defect", "figures": 2, "notion_title": "VSD", "notion_page_id": "3a1e77f4-b1f0-8123-9ff5-f3933527d0a4"},
    "17": {"title": "Atrioventricular Canal Defects", "figures": 4, "notion_title": "AVSD", "notion_page_id": "3a1e77f4-b1f0-813a-be7d-deeb67c9da57"},
    "18": {"title": "Double Outlet Right Ventricle", "figures": 4, "notion_title": "Ch10 DORV", "notion_page_id": "3a2e77f4-b1f0-8180-99d4-c4c97d7174e8", "user_edited": true},
    "19": {"title": "Truncus Arteriosus", "figures": 3, "notion_title": "Ch9 Truncus Arteriosus", "notion_page_id": "3a1e77f4-b1f0-814e-9174-d7b5c83e3f4d"},
    "20": {"title": "Total Anomalous Pulmonary Venous Return", "figures": 2, "notion_title": "Ch5 TAPVR", "notion_page_id": "3a1e77f4-b1f0-8106-9bf9-fb4c53591116"},
    "21": {"title": "Left Ventricular Outflow Tract Obstruction", "figures": 2, "notion_title": "AS", "notion_page_id": "3a1e77f4-b1f0-819a-94b1-e24d5843ac59"},
    "22": {"title": "Mitral Valve", "figures": 2, "notion_title": "Ch13 Mitral Valve Disease", "notion_page_id": "3a2e77f4-b1f0-81b4-908a-c28b8446c577"},
    "23": {"title": "Pulmonary Atresia/Intact Ventricular Septum", "figures": 2, "notion_title": "PA-IVS", "notion_page_id": "3a1e77f4-b1f0-81ae-b9ca-f4a556ce9acc"},
    "24": {"title": "Tetralogy of Fallot", "figures": 4, "notion_title": "TOF（典型）", "notion_page_id": "3a1e77f4-b1f0-813b-9c0d-d47118f84f2a"},
    "25": {"title": "Tetralogy of Fallot with Pulmonary Atresia", "figures": 1, "notion_title": "TOF+PA", "notion_page_id": "3a1e77f4-b1f0-8182-95f6-cd7f157d9121"},
    "26": {"title": "Tetralogy of Fallot with Absent Pulmonary Valve", "figures": 1, "notion_title": "TOF+AbsentPV", "notion_page_id": "3a1e77f4-b1f0-81f0-8c78-f4344af60ede"},
    "27": {"title": "Transposition of the Great Arteries", "figures": 7, "split": true, "options": [
      {"notion_title": "D-TGA", "notion_page_id": "3a1e77f4-b1f0-8199-8de5-ceaab9cbdcb6"},
      {"notion_title": "L-TGA", "notion_page_id": "3a1e77f4-b1f0-8119-83b1-d050c09cd9d4"}]},
    "28": {"title": "Single-ventricle Lesions", "figures": 9, "notion_title": "Ch18 Single-Ventricle Lesions 統整框架", "notion_page_id": "3a2e77f4-b1f0-81db-9617-da0fa9331937"},
    "29": {"title": "Hypoplastic Left Heart Syndrome", "figures": 2, "notion_title": "HLHS 解剖生理手術路徑", "notion_page_id": "3a1e77f4-b1f0-8183-a5e0-c7b24a4598b0", "user_edited": true},
    "30": {"title": "Interrupted Aortic Arch", "figures": 5, "notion_title": "IAA", "notion_page_id": "3a1e77f4-b1f0-81fe-bd7c-de2ed0e8752f"},
    "31": {"title": "Vascular Rings", "figures": 6, "notion_title": "Ch14 Vascular Rings", "notion_page_id": "3a2e77f4-b1f0-8168-a60b-cf115b99d028"},
    "32": {"title": "Tricuspid Atresia", "figures": 3, "notion_title": "Tricuspid Atresia", "notion_page_id": "3a1e77f4-b1f0-819a-b927-cca2b6e179d9"},
    "33": {"title": "Heart Transplantation", "figures": 3, "notion_title": "Ch16 Heart Transplantation", "notion_page_id": "3a2e77f4-b1f0-8120-8561-ee025c67e349"},
    "35": {"title": "ALCAPA and AAOCA", "figures": 5, "split": true, "options": [
      {"notion_title": "ALCAPA (Bland-White-Garland Syndrome)", "notion_page_id": "3a2e77f4-b1f0-81dd-a717-fe812b1b51b5"},
      {"notion_title": "AAOCA", "notion_page_id": "3a4e77f4-b1f0-8178-8929-f86b05412845"}]},
    "36": {"title": "Heterotaxy", "figures": 3, "notion_title": "Ch15 Heterotaxy", "notion_page_id": "3a2e77f4-b1f0-8119-9ca8-f6ae27030695"},
    "37": {"title": "Ebstein Anomaly", "figures": 3, "notion_title": "Ebstein Anomaly 詳細筆記", "notion_page_id": "3a1e77f4-b1f0-8148-afc4-c64ef74032d9"}
  },
  "no_figures": {
    "3": "Preoperative Evaluation — 書中無 Figure",
    "34": "Heart-Lung and Lung Transplantation — 書中無 Figure"
  },
  "known_gaps": {
    "6.2": "文字層無 caption block，抽不到，需人工處理",
    "6.3": "文字層無 caption block，抽不到，需人工處理"
  }
}
```

- [ ] **Step 2: 驗證 JSON 合法且圖數加總為 139**

Run:
```bash
python3 -c "
import json
d = json.load(open('nasr_ed2_figure_map.json'))
ch = d['chapters']
print('章數', len(ch), '圖數加總', sum(c['figures'] for c in ch.values()))
print('split 章', [k for k, v in ch.items() if v.get('split')])
missing = [k for k, v in ch.items() if not v.get('split') and not v.get('notion_page_id')]
print('缺 page id 的章', missing)
"
```

Expected:
```
章數 35 圖數加總 139
split 章 ['27', '35']
缺 page id 的章 []
```

- [ ] **Step 3: 驗證所有 page id 在 Notion 讀得到**

Run:
```bash
python3 -c "
import json, sys
sys.path.insert(0, 'scripts')
from upload_figures import Notion, load_token
import requests
tok = load_token()
h = {'Authorization': f'Bearer {tok}', 'Notion-Version': '2022-06-28'}
d = json.load(open('nasr_ed2_figure_map.json'))
ids = []
for k, v in d['chapters'].items():
    if v.get('split'):
        ids += [(k, o['notion_page_id'], o['notion_title']) for o in v['options']]
    else:
        ids.append((k, v['notion_page_id'], v['notion_title']))
bad = []
for ch, pid, title in ids:
    r = requests.get(f'https://api.notion.com/v1/pages/{pid}', headers=h, timeout=30)
    if not r.ok:
        bad.append((ch, title, r.status_code))
print('檢查', len(ids), '個頁面，失敗', len(bad))
for b in bad: print('  ', b)
"
```

Expected: `檢查 37 個頁面，失敗 0`

若有失敗，先確認該頁是否已被封存或 id 有誤，修正對照表後再繼續。

- [ ] **Step 4: Commit**

```bash
git add nasr_ed2_figure_map.json
git commit -m "feat: Nasr ed2 章號對 Notion 病灶頁對照表，35 章 139 張"
```

---

## Task 7: map_nasr_figures.py

**Files:**
- Create: `scripts/map_nasr_figures.py`
- Create: `tests/test_map_nasr_figures.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_map_nasr_figures.py`：

```python
"""章號查表填 target_page_id 的測試。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from map_nasr_figures import apply_map  # noqa: E402

TABLE = {
    "8": {"title": "Echocardiography", "notion_page_id": "page-echo"},
    "27": {"title": "TGA", "split": True, "options": [
        {"notion_title": "D-TGA", "notion_page_id": "page-dtga"},
        {"notion_title": "L-TGA", "notion_page_id": "page-ltga"}]},
}


def fig(fig_id, chapter, page_id=None):
    return {"fig_id": fig_id, "nasr_chapter": chapter,
            "target_page_id": page_id, "include": True}


def test_一般章直接填入page_id():
    figs = [fig("8.3", 8)]
    assert apply_map(figs, TABLE) == (1, [])
    assert figs[0]["target_page_id"] == "page-echo"


def test_split章不自動填並列入待人工分派():
    figs = [fig("27.1", 27), fig("27.2", 27)]
    assert apply_map(figs, TABLE) == (0, ["27.1", "27.2"])
    assert figs[0]["target_page_id"] is None


def test_已填過的不覆蓋():
    figs = [fig("8.3", 8, "手動指定的頁")]
    assert apply_map(figs, TABLE) == (0, [])
    assert figs[0]["target_page_id"] == "手動指定的頁"


def test_對照表沒有的章列入待人工分派():
    figs = [fig("99.1", 99)]
    assert apply_map(figs, TABLE) == (0, ["99.1"])
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_map_nasr_figures.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'map_nasr_figures'`

- [ ] **Step 3: 寫實作**

建立 `scripts/map_nasr_figures.py`：

```python
#!/usr/bin/env python3
"""依章號對照表填 manifest 的 target_page_id。純本地查表，不連 Notion。

Miller 那套是用 sub-page 標頭的書本頁碼區間比對；Nasr 這邊行不通——
小兒心臟學筆記是 lesion-based 頁面，標頭來源行混列四本書，沒有單一
可比對的頁碼區間。改用章號直接查表。

用法：
    python3 scripts/map_nasr_figures.py figures/nasr
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE_PATH = ROOT / "nasr_ed2_figure_map.json"


def apply_map(figs, table):
    """回傳 (填入筆數, 待人工分派的 fig_id 清單)。

    split 章（一章對應兩個病灶頁）與表上沒有的章都不自動填，
    交給 set_nasr_sections.py 逐圖指定。已經有值的不覆蓋。
    """
    filled, manual = 0, []
    for f in figs:
        if f.get("target_page_id"):
            continue
        entry = table.get(str(f["nasr_chapter"]))
        if entry is None or entry.get("split"):
            manual.append(f["fig_id"])
            continue
        f["target_page_id"] = entry["notion_page_id"]
        filled += 1
    return filled, manual


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("figures_dir")
    args = ap.parse_args()

    mpath = Path(args.figures_dir) / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    table = json.loads(TABLE_PATH.read_text(encoding="utf-8"))["chapters"]

    filled, manual = apply_map(manifest, table)
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                     encoding="utf-8")

    print(f"填入 target_page_id：{filled} 張")
    if manual:
        print(f"待人工分派（split 章或表上無此章）：{', '.join(manual)}")
        print("用 scripts/set_nasr_sections.py 指定 page 與 section。")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest tests/test_map_nasr_figures.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/map_nasr_figures.py tests/test_map_nasr_figures.py
git commit -m "feat: 依章號對照表填 target_page_id"
```

---

## Task 8: dump_nasr_sections.py

指派小節的工作底稿：把目標頁的可選小節與待歸位的圖並排列出，不必逐張開圖檔。

**Files:**
- Create: `scripts/dump_nasr_sections.py`

- [ ] **Step 1: 寫實作**

建立 `scripts/dump_nasr_sections.py`：

```python
#!/usr/bin/env python3
"""列出待上傳圖片所屬 Notion 頁的小節，與該頁待歸位的圖。

指派 target_section 的工作底稿。只讀不寫。

用法：
    python3 scripts/dump_nasr_sections.py figures/nasr [--chapter 8]
"""

import argparse
import json
from pathlib import Path

from upload_figures import Notion, load_token, section_names

ROOT = Path(__file__).resolve().parent.parent
TABLE_PATH = ROOT / "nasr_ed2_figure_map.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("figures_dir")
    ap.add_argument("--chapter", type=int, help="只看指定章號")
    args = ap.parse_args()

    manifest = json.loads(
        (Path(args.figures_dir) / "manifest.json").read_text(encoding="utf-8"))
    table = json.loads(TABLE_PATH.read_text(encoding="utf-8"))["chapters"]

    figs = [f for f in manifest if f.get("include") and not f.get("uploaded_block_id")]
    if args.chapter:
        figs = [f for f in figs if f["nasr_chapter"] == args.chapter]

    notion = Notion(load_token())
    by_page = {}
    for f in figs:
        by_page.setdefault(f.get("target_page_id"), []).append(f)

    for pid, group in by_page.items():
        chs = sorted({f["nasr_chapter"] for f in group})
        titles = [table[str(c)]["title"] for c in chs if str(c) in table]
        print(f"\n{'=' * 70}")
        if pid is None:
            print(f"（尚未指派頁面）Nasr Ch{chs} {titles}")
            print(f"{'=' * 70}")
            for f in group:
                print(f"  Fig {f['fig_id']}  {f['caption'][:100]}")
            continue

        print(f"{pid}  ← Nasr Ch{chs} {titles}")
        print(f"{'=' * 70}")
        print("  可指派的小節：")
        for s in section_names(notion.children(pid)):
            print(f"    - {s}")
        print("  待歸位的圖：")
        for f in group:
            sect = f.get("target_section") or "（未指派）"
            print(f"    Fig {f['fig_id']}  [{sect}]  {f['caption'][:90]}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 手動確認可執行**

先確認語法與 import 正確（此時 `figures/nasr` 還不存在，預期報找不到檔案而非 import 錯誤）：

Run: `python3 scripts/dump_nasr_sections.py figures/nasr`
Expected: `FileNotFoundError`，訊息指向 `figures/nasr/manifest.json`。**不是** `ImportError` 或 `SyntaxError`。

- [ ] **Step 3: Commit**

```bash
git add scripts/dump_nasr_sections.py
git commit -m "feat: 列出目標頁小節與待歸位圖的工作底稿"
```

---

## Task 9: set_nasr_sections.py

**Files:**
- Create: `scripts/set_nasr_sections.py`

- [ ] **Step 1: 寫實作**

建立 `scripts/set_nasr_sections.py`：

```python
#!/usr/bin/env python3
"""把判斷好的 target_section（必要時連同 target_page_id）寫回 manifest。

輸入 JSON 從 stdin 讀，兩種格式：
    {"8.3": "TEE 標準切面",
     "27.1": {"section": "解剖與生理", "page": "<Notion page id>"}}

小節名稱必須與 Notion 上的小標完全相同，否則上傳時找不到錨點會退回
「二、圖表」。本腳本先驗證名稱存在，不符就中止，不寫入任何內容。

用法：
    python3 scripts/set_nasr_sections.py figures/nasr < assign.json
"""

import argparse
import json
import sys
from pathlib import Path

from upload_figures import Notion, load_token, section_names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("figures_dir")
    args = ap.parse_args()

    assign = json.load(sys.stdin)
    mpath = Path(args.figures_dir) / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))

    notion = Notion(load_token())
    sections_cache = {}

    def sections_of(page_id):
        if page_id not in sections_cache:
            sections_cache[page_id] = section_names(notion.children(page_id))
        return sections_cache[page_id]

    errors, staged = [], []
    for f in manifest:
        spec = assign.get(f["fig_id"])
        if spec is None:
            continue
        if isinstance(spec, str):
            section, page_id = spec, f.get("target_page_id")
        else:
            section, page_id = spec["section"], spec.get("page") or f.get("target_page_id")

        if not page_id:
            errors.append(f"Fig {f['fig_id']}：沒有 target_page_id，請在指派中帶 page")
            continue
        avail = sections_of(page_id)
        if section not in avail:
            errors.append(
                f"Fig {f['fig_id']}：頁面 {page_id[:8]}… 沒有小節「{section}」。"
                f"可選：{avail}")
            continue
        staged.append((f, section, page_id))

    unknown = set(assign) - {f["fig_id"] for f in manifest}
    if unknown:
        errors.append(f"manifest 裡沒有這些圖：{sorted(unknown)}")

    if errors:
        for e in errors:
            print(f"✗ {e}")
        sys.exit("有錯誤，未寫入任何內容。")

    for f, section, page_id in staged:
        f["target_section"] = section
        f["target_page_id"] = page_id
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print(f"已寫入 {len(staged)} 張圖的歸屬。")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 手動確認可執行**

Run: `echo '{}' | python3 scripts/set_nasr_sections.py figures/nasr`
Expected: `FileNotFoundError`，訊息指向 `figures/nasr/manifest.json`。**不是** `ImportError` 或 `SyntaxError`。

- [ ] **Step 3: Commit**

```bash
git add scripts/set_nasr_sections.py
git commit -m "feat: 把小節歸屬寫回 manifest，寫入前先驗證小節名稱存在"
```

---

## Task 10: Ch8 Echocardiography 驗收

**Files:** 無程式碼變更，執行既有腳本。

- [ ] **Step 1: 抽 Ch8 的圖**

Run:
```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent"
python3 scripts/extract_figures_raster.py \
  ~/Desktop/"pediatric cardiac handbook TEE.pdf" figures/nasr --chapters 8
```

Expected: `抽出 11 張圖 → figures/nasr`，無 suspect 標記（Ch8 全數由 raster 配對成功）。

- [ ] **Step 2: 開 contact sheet 給使用者驗收**

Run: `open figures/nasr/contact_sheet.html`

**停在這裡等使用者確認**：裁切是否完整（有沒有被切掉、有沒有混進內文或鄰圖）、哪幾張不需要。使用者說不要的圖，把 manifest 裡該筆的 `include` 改為 `false`。

- [ ] **Step 3: 填 target_page_id**

Run: `python3 scripts/map_nasr_figures.py figures/nasr`
Expected: `填入 target_page_id：11 張`，無待人工分派項目。

- [ ] **Step 4: 列出 TEE 頁的小節**

Run: `python3 scripts/dump_nasr_sections.py figures/nasr --chapter 8`

Expected: 印出 `3a4e77f4-b1f0-8137-8413-d0fcd88b23f6 ← Nasr Ch[8] ['Echocardiography']`，其下列出該頁的小節清單與 11 張待歸位的圖及其圖說。

- [ ] **Step 5: 依圖說指派小節**

讀上一步的圖說與小節清單，寫成指派 JSON。小節名稱必須逐字複製自輸出，不可自行改寫。例：

```bash
cat > /tmp/assign-ch8.json <<'EOF'
{
  "8.1": "TTE 與 TEE 的取像窗",
  "8.2": "TTE 標準切面"
}
EOF
python3 scripts/set_nasr_sections.py figures/nasr < /tmp/assign-ch8.json
```

Expected: `已寫入 N 張圖的歸屬。`

若回報某小節不存在，照它印出的「可選」清單改，不要去改 Notion 頁面。歸屬不明確的圖不要硬指派，留 `target_section` 為 null 讓它落回「二、圖表」。

- [ ] **Step 6: dry-run 確認插入位置**

Run: `python3 scripts/upload_figures.py figures/nasr --dry-run`

Expected: 列出每張圖將插入的 page id 與小節名稱，並印出 `--dry-run，未實際寫入。`

- [ ] **Step 7: 實際上傳**

Run: `python3 scripts/upload_figures.py figures/nasr`
Expected: 逐張印出 `上傳 Fig 8.x … 完成`，最後 `已插入 11/11 張到 3a4e77f4…`

- [ ] **Step 8: 使用者驗收 Notion 實際結果**

請使用者開 Notion 的「Echocardiography（TEE 完整切面與 segmental 判讀）」頁，確認圖的位置與品質。**通過才進 Task 11。**

- [ ] **Step 9: Commit**

`figures/` 在 `.gitignore`，無檔案可 commit。改為記錄驗收結果：

```bash
git commit --allow-empty -m "chore: Ch8 Echocardiography 11 張圖驗收通過"
```

---

## Task 11: 推展其餘 34 章

Ch8 驗收通過後執行。共 128 張（139 − Ch8 的 11 張）。

**Files:** 無程式碼變更。

- [ ] **Step 1: 抽其餘章節的圖**

沿用同一個 `figures/nasr` 目錄，`uploaded_block_id` 會保護已上傳的 Ch8。

Run:
```bash
python3 scripts/extract_figures_raster.py \
  ~/Desktop/"pediatric cardiac handbook TEE.pdf" figures/nasr
```

Expected: `抽出 139 張圖`，並列出 6 筆 `geometric_fallback`（7.2、7.3、11.2、11.4、11.5、11.9）。

**注意：這一步會覆寫 manifest.json，Ch8 已填的 `uploaded_block_id` 與 `target_section` 會遺失。** 執行前先備份，執行後把 Ch8 的欄位併回：

```bash
cp figures/nasr/manifest.json /tmp/manifest-ch8-backup.json
# 抽圖後
python3 -c "
import json
new = json.load(open('figures/nasr/manifest.json'))
old = {f['fig_id']: f for f in json.load(open('/tmp/manifest-ch8-backup.json'))}
for f in new:
    o = old.get(f['fig_id'])
    if o:
        for k in ('target_page_id', 'target_section', 'uploaded_block_id', 'include'):
            f[k] = o[k]
json.dump(new, open('figures/nasr/manifest.json', 'w'), ensure_ascii=False, indent=2)
print('併回', sum(1 for f in new if f['uploaded_block_id']), '張已上傳的紀錄')
"
```

Expected: `併回 11 張已上傳的紀錄`

- [ ] **Step 2: contact sheet 驗收**

Run: `open figures/nasr/contact_sheet.html`

停下來等使用者確認裁切品質與要排除的圖。不要的圖把 `include` 改 `false`。

**特別檢查 6 張 `geometric_fallback`**（縮圖牆上有紅字標記）：它們是被烙進整頁背景層、無法用圖框隔離的圖，改用 Miller 的幾何裁切法產出，品質不可信（實測 Fig 11.4 裁出的是整張表格加頁眉）。預設 `include: false` 不會上傳，使用者認可哪張才手動改 `true`。

- [ ] **Step 3: 填 target_page_id**

Run: `python3 scripts/map_nasr_figures.py figures/nasr`

Expected: `填入 target_page_id：116 張`（139 − Ch8 已填的 11 張 − Ch27 的 7 張 − Ch35 的 5 張），並列出待人工分派的 `27.1`–`27.7`、`35.1`–`35.5`。

註：`apply_map` 不看 `include`，6 張 `geometric_fallback` 也會被填入 `target_page_id`，但 `upload_figures.py` 只處理 `include: true` 的項目，不會被上傳。

- [ ] **Step 4: 分派 split 章**

讀 Ch27（TGA）與 Ch35（ALCAPA/AAOCA）的圖說，判斷每張屬於哪一頁：

Run: `python3 scripts/dump_nasr_sections.py figures/nasr --chapter 27`

依圖說內容指派，D-TGA 相關的用 `3a1e77f4-b1f0-8199-8de5-ceaab9cbdcb6`，L-TGA（congenitally corrected）用 `3a1e77f4-b1f0-8119-83b1-d050c09cd9d4`：

```bash
cat > /tmp/assign-split.json <<'EOF'
{
  "27.1": {"section": "解剖", "page": "3a1e77f4-b1f0-8199-8de5-ceaab9cbdcb6"}
}
EOF
python3 scripts/set_nasr_sections.py figures/nasr < /tmp/assign-split.json
```

Ch35 同樣處理，ALCAPA 用 `3a2e77f4-b1f0-81dd-a717-fe812b1b51b5`、AAOCA 用 `3a4e77f4-b1f0-8178-8929-f86b05412845`。

- [ ] **Step 5: 指派其餘各章的小節**

逐章跑工作底稿並指派。建議一次處理一章，避免小節名稱混淆：

```bash
for ch in 1 2 4 5 6 7 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 28 29 30 31 32 33 36 37; do
  echo "===== Ch$ch ====="
  python3 scripts/dump_nasr_sections.py figures/nasr --chapter $ch
done > /tmp/nasr-sections.txt
```

讀 `/tmp/nasr-sections.txt`，寫成一份完整的指派 JSON，一次寫回：

```bash
python3 scripts/set_nasr_sections.py figures/nasr < /tmp/assign-all.json
```

歸屬不明確的圖留 null，讓它落回「二、圖表」。這是設計上接受的結果，不要硬湊。

- [ ] **Step 6: dry-run 檢查**

Run: `python3 scripts/upload_figures.py figures/nasr --dry-run`

確認每張圖的目標頁與小節都合理，特別檢查沒有圖被誤送到別的病灶頁。

- [ ] **Step 7: 上傳**

Run: `python3 scripts/upload_figures.py figures/nasr`

Expected: 逐頁印出插入結果。已上傳的 Ch8 因為有 `uploaded_block_id` 會被跳過。

若中途失敗，manifest 每處理完一個位置就寫回一次，直接重跑即可，不會重複插圖。

- [ ] **Step 8: 統計並回報**

Run:
```bash
python3 -c "
import json, collections
m = json.load(open('figures/nasr/manifest.json'))
up = [f for f in m if f['uploaded_block_id']]
print('已上傳', len(up), '/', len(m))
print('落回二、圖表', sum(1 for f in up if not f['target_section']))
print('未上傳', [f['fig_id'] for f in m if not f['uploaded_block_id']])
"
```

- [ ] **Step 9: 更新記憶並 commit**

把完成狀況寫進 `project_pediatric_cardiology_park.md` 記憶檔（張數、日期、落回「二、圖表」的清單、Ch6 的 6.2/6.3 缺口），並更新 spec 的「狀態」為完成。

```bash
git add docs/superpowers/specs/2026-07-24-nasr-figure-extraction-design.md
git commit -m "docs: Nasr ed2 圖表回填完成，記錄執行結果"
```

---

## 已知限制

- **Ch6 的 Fig 6.2、6.3 抽不到**（文字層無 caption block）。若要補，需手動用 PyMuPDF 指定 idx 與裁切框產圖，再手動加進 manifest。
- **6 張 `geometric_fallback`**（7.2、7.3、11.2、11.4、11.5、11.9）預設 `include: false`。這些圖被烙進整頁背景掃描層，圖框隔離不出來，改用幾何裁切，品質不可信，需逐張目視認可。要精修只能手動指定裁切框。
- **重跑抽圖會覆寫 manifest**。Task 11 Step 1 的備份與併回步驟不可略過。
