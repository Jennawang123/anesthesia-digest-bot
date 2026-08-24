#!/usr/bin/env python3
"""稽核 Nasr ed2 已抽出的圖，找出被裁掉內容的那些。

## 為什麼會被裁

extract_figures_raster.py 的 crop_rect() 用「raster 圖框的聯集」當裁切框。
圖上不屬於任何 raster 的**純文字**（panel 標題如「Systemic obstruction」、
底部的算式標註如「SVR + Outlet obstruction = Outflow resistance」）因此
落在框外被切掉。當初已知這個問題，但只用 caption 的跨距補了**寬度**
（見 crop_rect 的 docstring），**垂直方向從來沒補**——所以圖頂圖底整列
文字會消失。2026-08-21 由使用者在互動筆記上看 Fig 2.6 才發現。

## 做法（兩種證據，任一命中就標記）

**A. 邊緣墨跡**：被裁的圖，裁切線會切過內容，PNG 最外圈因此帶墨。這是
直接證據、幾乎不會誤報，但看不到「切在空白帶、只是漏掉上下某個元素」
的情形（Fig 2.6 的標題與圖之間隔著空白，邊緣就是乾淨的）。

**B. 鄰接 block**：讀 figures/nasr/manifest.json 拿到每張圖當初的 bbox，再從該框往上下
「泛洪擴張」：把與圖水平重疊、垂直間隙夠近、且**不是內文字體**的 text
block 逐步納入，直到沒有新的可納入為止。擴張後的框比原框高出超過門檻，
就判定原圖被裁。

用 is_body 排除內文是關鍵——圖上的標註不是內文字體，段落是。但這不夠
（表格文字同樣不是內文字體），所以再用垂直間隙上限擋住不相干的東西。

兩者互補：A 抓得到「被切掉的 raster」（Fig 2.5 缺的是圖不是字，B 抓不
到），B 抓得到「隔著空白被漏掉的標註」（Fig 2.4 的 x 軸標題 Qp:Qs 就在
裁切線下方 1.9pt，A 抓不到）。在 Ch2 六張已人工確認的圖上，A 對 5 張、
B 對 3 張，聯集 6/6。

## 輸出

- report.json：逐張的原框／建議框／上下各多出多少 pt／判定
- report.html：可疑圖的「現況 vs 重抽」並排對照，供目視確認
- *.png：依建議框重抽的圖

**只偵測與產出對照，不覆蓋原圖。** 判定僅供篩選，最終要人眼看過。
"""
import argparse
import html
import json
import sys
from pathlib import Path

import fitz
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_figures_raster as E

# 垂直間隙上限（pt）。圖內元素之間通常很近，內文段落與圖之間會拉開，
# 用這個值把兩者分開。放太大會把上方段落吃進來。
GAP_MAX = 16.0
# 水平重疊比例，相對「較窄的一方」——多 panel 窄圖的標註會比圖窄很多，
# 相對圖寬算會全數落空（這個坑在原腳本的 _score 已經踩過一次）。
MIN_OVERLAP = 0.25
# 高度增加超過這個值（pt）才算被裁；以下視為 PAD 的正常差異
SUSPECT_PT = 8.0
# 邊緣取樣的列數，與「非白」的灰階門檻
EDGE_K, EDGE_WHITE = 3, 248
# 邊緣帶墨比例超過這個值視為裁切線切過內容
EDGE_INK_MIN = 0.01
# 「擴到留白為止」的每步距離、總上限，與試探用的低 dpi
CLEAN_STEP, CLEAN_MAX, PROBE_DPI = 4.0, 140.0, 72
# 比較 pt 座標時的容差（PDF 座標本身只有 0.1pt 精度）
EPS = 0.5


def vgap(a, b):
    """兩個矩形的垂直間距，重疊則為 0。"""
    if a.y1 <= b.y0:
        return b.y0 - a.y1
    if b.y1 <= a.y0:
        return a.y0 - b.y1
    return 0.0


def hgap(a, b):
    """兩個矩形的水平間距，重疊則為 0。"""
    if a.x1 <= b.x0:
        return b.x0 - a.x1
    if b.x1 <= a.x0:
        return a.x0 - b.x1
    return 0.0


def rdist(a, b):
    """矩形間的粗略距離：兩軸間距取大的那個。"""
    return max(vgap(a, b), hgap(a, b))


def overlap_ratio(a0, a1, b0, b1):
    """兩段區間的重疊長度，除以較短的那一段。"""
    lo, hi = max(a0, b0), min(a1, b1)
    if hi <= lo:
        return 0.0
    return (hi - lo) / min(a1 - a0, b1 - b0)


def edge_ink(png_path):
    """四邊最外 EDGE_K 列／行的非白像素比例。

    裁切線切過內容時，該邊會留下墨跡；完整的圖四周是 PAD 留出的白邊。
    """
    im = Image.open(png_path).convert("L")
    w, h = im.size
    px = im.load()

    def frac(coords):
        coords = list(coords)
        n = sum(1 for x, y in coords if px[x, y] < EDGE_WHITE)
        return round(n / max(1, len(coords)), 4)

    return {
        "top": frac((x, y) for y in range(min(EDGE_K, h)) for x in range(w)),
        "bottom": frac((x, y) for y in range(max(0, h - EDGE_K), h) for x in range(w)),
        "left": frac((x, y) for x in range(min(EDGE_K, w)) for y in range(h)),
        "right": frac((x, y) for x in range(max(0, w - EDGE_K), w) for y in range(h)),
    }


def _edge_dirty(doc, pno, rect, side):
    """把 rect 重抽成低解析度點陣圖，看指定那一邊是否還帶墨。"""
    pix = doc[pno].get_pixmap(clip=rect, dpi=PROBE_DPI)
    if pix.width < 2 or pix.height < 2:
        return False
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
    w, h = im.size
    px = im.load()
    if side in ("top", "bottom"):
        k = min(2, h)
        ys = range(k) if side == "top" else range(max(0, h - k), h)
        coords = [(x, y) for y in ys for x in range(w)]
    else:
        k = min(2, w)
        xs = range(k) if side == "left" else range(max(0, w - k), w)
        coords = [(x, y) for x in xs for y in range(h)]
    n = sum(1 for x, y in coords if px[x, y] < EDGE_WHITE)
    return n / max(1, len(coords)) >= EDGE_INK_MIN


def clean_edges(box, doc, pno, all_caps, others, page_rect, blocks=()):
    """邊緣還帶墨時，往外擴到留白為止。

    被切掉的若是**圖形**而不是 text block，grow_box 找不到東西可補（實測
    49 張判定被裁的圖裡有 36 張重抽出來與原圖一模一樣）。這時只能靠邊緣
    墨跡本身當訊號：一路外擴，直到那一邊乾淨、或撞到頁眉／同頁其他圖／
    任何 caption 為止。
    """
    cur = fitz.Rect(box)
    top_limit, bot_limit = E.HEAD_Y, page_rect.y1
    for o in list(others) + list(all_caps):
        if o.y1 <= box.y0 + 1:
            top_limit = max(top_limit, o.y1)
        if o.y0 >= box.y1 - 1:
            bot_limit = min(bot_limit, o.y0)

    # 左右的障礙物除了其他圖與圖說，還要算上**內文段落**：雙欄版面裡隔壁
    # 欄的段落就貼在圖旁邊，只擋圖與圖說會讓它被整段吃進來。
    left_limit, right_limit = page_rect.x0, page_rect.x1
    side_obs = list(others) + list(all_caps) + \
        [b["rect"] for b in blocks if b["is_body"]]
    for o in side_obs:
        if overlap_ratio(box.y0, box.y1, o.y0, o.y1) <= 0:
            continue                      # 垂直不重疊，擋不到左右
        if o.x1 <= box.x0 + 1:
            left_limit = max(left_limit, o.x1)
        if o.x0 >= box.x1 - 1:
            right_limit = min(right_limit, o.x0)

    lim = {"top": top_limit, "bottom": bot_limit,
           "left": left_limit, "right": right_limit}
    for side in ("top", "bottom", "left", "right"):
        moved = 0.0
        while moved < CLEAN_MAX and _edge_dirty(doc, pno, cur, side):
            if side == "top":
                nxt = max(lim[side], cur.y0 - CLEAN_STEP)
                if nxt >= cur.y0 - 0.01:
                    break
                cur = fitz.Rect(cur.x0, nxt, cur.x1, cur.y1)
            elif side == "bottom":
                nxt = min(lim[side], cur.y1 + CLEAN_STEP)
                if nxt <= cur.y1 + 0.01:
                    break
                cur = fitz.Rect(cur.x0, cur.y0, cur.x1, nxt)
            elif side == "left":
                nxt = max(lim[side], cur.x0 - CLEAN_STEP)
                if nxt >= cur.x0 - 0.01:
                    break
                cur = fitz.Rect(nxt, cur.y0, cur.x1, cur.y1)
            else:
                nxt = min(lim[side], cur.x1 + CLEAN_STEP)
                if nxt <= cur.x1 + 0.01:
                    break
                cur = fitz.Rect(cur.x0, cur.y0, nxt, cur.y1)
            moved += CLEAN_STEP
    return cur


def grow_box(box, blocks, cap_rect, all_caps, others, page_rect):
    """從 box 往上下擴張，納入屬於這張圖的文字標註。

    **同頁每一個 caption 都是硬邊界**，不只目標圖自己那個。同頁上下排兩
    張圖時，上面那張的圖說就夾在兩張圖中間；只排除自己的 caption 會讓
    擴張越過它、把別人的圖說吃進來（實測 Fig 35.4 吃到 Fig 35.3 的圖說）。

    光有 caption 邊界還不夠：panel 標籤（(A)、(B)）排在自己那張圖的**圖說
    之前**，所以從上一張圖往下擴張時會先撞到它們（實測 Fig 24.1 吃到 24.2
    的 (A)(B)）。因此再加一條**就近歸屬**：候選 block 若離同頁其他圖的框
    比離自己更近，就不是自己的東西。這與原腳本 assign_rasters「raster 歸
    給最近的 caption」是同一個原則。
    """
    cur = fitz.Rect(box)
    used = set()
    # caption 在圖上方或下方，決定哪一側不能越界
    cap_above = cap_rect is not None and cap_rect.y1 <= box.y0 + 2
    cap_below = cap_rect is not None and cap_rect.y0 >= box.y1 - 2

    def blocked(lo, hi, x0, x1):
        """lo~hi 這段垂直區間內，是否隔著某個水平重疊的 caption。"""
        for c in all_caps:
            if c.y1 <= lo or c.y0 >= hi:
                continue
            if overlap_ratio(x0, x1, c.x0, c.x1) > 0:
                return True
        return False

    while True:
        grew = False
        for i, b in enumerate(blocks):
            if i in used or b["is_body"]:
                continue
            if others and any(vgap(b["rect"], o) < vgap(b["rect"], cur) for o in others):
                continue   # 離別張圖更近，不是自己的標註
            r = b["rect"]
            if r.y0 < E.HEAD_Y:                      # 頁眉／running head
                continue
            if E.PAGE_NUM_RE.match(b["text"].strip()):  # 頁碼
                continue
            if any(r.intersects(c) for c in all_caps):
                continue
            if overlap_ratio(cur.x0, cur.x1, r.x0, r.x1) < MIN_OVERLAP:
                continue

            # 用 EPS 容差判上下：擴張後的框邊常常剛好等於某個 block 的邊
            # （框 = 前一個 block 的邊減 PAD），二進位浮點下 291.3 未必等於
            # 291.3。差之毫釐就會掉進「已經在框內」把它永久跳過——Fig 2.6
            # 的「Systemic obstruction」標題就是這樣消失的。
            if r.y1 <= cur.y0 + EPS:                  # 在上方
                if cap_above and r.y0 < cap_rect.y1:
                    continue
                if blocked(r.y1, cur.y0, cur.x0, cur.x1):
                    continue
                gap = max(0.0, cur.y0 - r.y1)
            elif r.y0 >= cur.y1 - EPS:                # 在下方
                if cap_below and r.y1 > cap_rect.y0:
                    continue
                if blocked(cur.y1, r.y0, cur.x0, cur.x1):
                    continue
                gap = max(0.0, r.y0 - cur.y1)
            elif r.y0 >= cur.y0 - EPS and r.y1 <= cur.y1 + EPS:
                used.add(i)                           # 完全在框內
                continue
            else:                                     # 跨越框的上／下緣
                gap = 0.0

            if 0 <= gap <= GAP_MAX:
                # 只對新納入的 block 外擴 PAD；原框本來就含 PAD，
                # 整體再加一次會讓每張圖都憑空長大
                cur = cur | fitz.Rect(r.x0 - E.PAD, r.y0 - E.PAD,
                                      r.x1 + E.PAD, r.y1 + E.PAD)
                used.add(i)
                grew = True
        if not grew:
            break

    top = max(page_rect.y0, cur.y0)
    if box.y0 >= E.HEAD_Y:
        top = max(top, E.HEAD_Y)       # 同 grow_box_h：別擴進頁眉
    return fitz.Rect(max(page_rect.x0, cur.x0), top,
                     min(page_rect.x1, cur.x1),
                     min(page_rect.y1, cur.y1))


def body_columns(blocks):
    """從內文 block 推出版心的欄位區間（本書是雙欄）。"""
    cols = []
    for r in sorted((b["rect"] for b in blocks if b["is_body"]),
                    key=lambda r: r.x0):
        if cols and r.x0 <= cols[-1][1] + 2:
            cols[-1] = (cols[-1][0], max(cols[-1][1], r.x1))
        else:
            cols.append((r.x0, r.x1))
    return cols


def with_caption_tails(caps, blocks):
    """把圖說的**續行**併回圖說矩形。

    find_captions 只認得以「Figure X.Y」開頭的那個 block，圖說換行另起
    block 時（Fig 32.1 的「LV, left ventricle; RV, ...」）就不在邊界集合裡，
    水平擴張會把它當成圖上的標註吃進來。
    """
    out = []
    for c in caps:
        cur = fitz.Rect(c)
        grew = True
        while grew:
            grew = False
            for b in blocks:
                r = b["rect"]
                if b["is_body"] or r.intersects(cur):
                    continue
                if r.y0 < cur.y1 - 1 or r.y0 - cur.y1 > 8:
                    continue          # 不是緊接在下一行
                if overlap_ratio(cur.x0, cur.x1, r.x0, r.x1) < 0.5:
                    continue
                cur = cur | r
                grew = True
        out.append(cur)
    return out


def grow_box_h(box, blocks, all_caps, others, page_rect, cols=()):
    """從 box 往**左右**擴張，納入與圖垂直重疊、貼著圖邊的標註。

    第一版只做上下。真正被漏掉最多的其實是左右：raster 只涵蓋圖形本體，
    引線末端的標註排在圖形兩側、落在框外，crop_rect 又只拿 caption 的跨距
    補寬度——caption 常在右上角，跨距根本不含那些標註。實測 Fig 6.7
    （Left coronary anatomy）左邊 6 個標註全被切成「mflex」「forator」
    「r lateral」，右邊的「2nd diagonal」也只剩「2nd」。

    與 grow_box 的差別在於**要處理跨越框邊的 block**：一行標註可能左端在
    框外、右端在框內（Fig 6.7 的「Posterior lateral　Distal LAD」橫跨整張
    圖），若照上下版那樣歸類成「已在框內」就會整行漏掉。
    """
    cur = fitz.Rect(box)
    used = set()

    def blocked(lo, hi, y0, y1):
        """lo~hi 這段水平區間內，是否隔著某個垂直重疊的 caption。"""
        for c in all_caps:
            if c.x1 <= lo or c.x0 >= hi:
                continue
            if overlap_ratio(y0, y1, c.y0, c.y1) > 0:
                return True
        return False

    while True:
        grew = False
        for i, b in enumerate(blocks):
            if i in used or b["is_body"]:
                continue
            r = b["rect"]
            if r.y0 < E.HEAD_Y or E.PAGE_NUM_RE.match(b["text"].strip()):
                continue
            if any(r.intersects(c) for c in all_caps):
                continue
            # 就近歸屬：離同頁別張圖更近的標註不是自己的
            if others and any(rdist(r, o) < rdist(r, cur) for o in others):
                continue
            if overlap_ratio(cur.y0, cur.y1, r.y0, r.y1) < MIN_OVERLAP:
                continue
            # 不跨欄：候選整個落在某個**圖本身沒碰到**的內文欄裡，就是隔壁欄
            # 的東西。欄間空隙只有 15.6pt、比 GAP_MAX 還小，不擋會把隔壁欄的
            # 標題整段吃進來（實測 Fig 30.2 吃到「Surgical Management」）。
            if any(r.x0 >= c0 - 1 and r.x1 <= c1 + 1
                   and overlap_ratio(box.x0, box.x1, c0, c1) <= 0
                   for c0, c1 in cols):
                continue

            if r.x1 <= cur.x0:
                gap, span = cur.x0 - r.x1, (r.x1, cur.x0)
            elif r.x0 >= cur.x1:
                gap, span = r.x0 - cur.x1, (cur.x1, r.x0)
            else:
                gap, span = 0.0, None          # 與框重疊（含跨越框邊）
            if gap > GAP_MAX:
                continue
            if span and blocked(span[0], span[1], cur.y0, cur.y1):
                continue
            if r.x0 >= cur.x0 - 0.01 and r.x1 <= cur.x1 + 0.01:
                used.add(i)                    # 完全在框內，擴不出東西
                continue

            cur = cur | fitz.Rect(r.x0 - E.PAD, r.y0 - E.PAD,
                                  r.x1 + E.PAD, r.y1 + E.PAD)
            used.add(i)
            grew = True
        if not grew:
            break

    # 原本就在頁眉線以下的圖，擴張後也不該越過頁眉：吃到 block 時是拿
    # 「block 上緣減 PAD」當新框，PAD 會把框推進 running head 的下緣裡
    # （Fig 10.4 的 panel 標籤 y0=61.0，減 6 就變成 55，切到頁眉的字）。
    top = max(page_rect.y0, cur.y0)
    if box.y0 >= E.HEAD_Y:
        top = max(top, E.HEAD_Y)
    return fitz.Rect(max(page_rect.x0, cur.x0), top,
                     min(page_rect.x1, cur.x1),
                     min(page_rect.y1, cur.y1))


def audit(pdf_path, fig_dir, out_dir, dpi):
    fig_dir, out_dir = Path(fig_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((fig_dir / "manifest.json").read_text("utf-8"))

    doc = fitz.open(pdf_path)
    pages = E.parse_pages(doc)
    body = E.body_font(pages)

    # 只算 manifest 真正用到的那些頁。整本 360 頁的 text block 一次全展開會
    # 把記憶體吃爆（實測會被系統 SIGKILL），而且其中大半根本沒有圖。
    todo = [e for e in manifest if e.get("png") and e.get("bbox")]
    needed = sorted({e["pdf_page"] for e in todo})
    blocks_by_page = {i: E.text_blocks(pages[i], body) for i in needed}
    print(f"  取 {len(needed)} 頁的 text block（全書 {doc.page_count} 頁）", flush=True)

    rows = []
    for n, e in enumerate(todo, 1):
        if n % 25 == 0:
            print(f"  ...{n}/{len(todo)}", flush=True)
        pno = e["pdf_page"]
        page_rect = doc[pno].rect
        old = fitz.Rect(*e["bbox"])
        blocks = blocks_by_page[pno]

        caps = E.find_captions(blocks)
        all_caps = with_caption_tails(
            [c["rect"] for c in caps] +
            [c["rect"] for c in E.find_range_captions(blocks)], blocks)
        cap = next((c["rect"] for c in caps if c["fig_id"] == e["fig_id"]), None)

        others = [fitz.Rect(*x["bbox"]) for x in todo
                  if x["pdf_page"] == pno and x["fig_id"] != e["fig_id"] and x.get("bbox")]
        new = grow_box(old, blocks, cap, all_caps, others, page_rect)
        new = grow_box_h(new, blocks, all_caps, others, page_rect,
                         body_columns(blocks))

        def deltas(r):
            return (round(old.y0 - r.y0, 1), round(r.y1 - old.y1, 1),
                    round(old.x0 - r.x0, 1), round(r.x1 - old.x1, 1))

        top, bot, lft, rgt = deltas(new)

        ink = edge_ink(fig_dir / e["png"])
        # 第一版刻意不看左右，理由是「圖貼近版心邊界時左右本來就會帶墨」。
        # 那個顧慮是錯的方向：真的貼齊版心時 clean_edges 一步都擴不出去，
        # 頂多多產一張一模一樣的對照圖；而漏看左右的代價是整排引線標註被
        # 切掉還查不出來（Fig 6.7 由使用者在互動筆記上看到才發現）。
        inked = [k for k in ("top", "bottom", "left", "right")
                 if ink[k] >= EDGE_INK_MIN]
        by_block = max(top, bot, lft, rgt) >= SUSPECT_PT
        cropped = by_block or bool(inked)
        why = ([f"邊緣帶墨:{'/'.join(inked)}"] if inked else []) + \
              (["鄰接 block 未納入"] if by_block else [])

        row = {
            "fig_id": e["fig_id"],
            "chapter": e["nasr_chapter"],
            "pdf_page": pno,
            "book_page": e.get("book_page"),
            "png": e["png"],
            "include": e.get("include", True),
            "old_bbox": [round(v, 1) for v in old],
            "new_bbox": [round(v, 1) for v in new],
            "grew_top_pt": top,
            "grew_bottom_pt": bot,
            "grew_left_pt": lft,
            "grew_right_pt": rgt,
            "cropped": cropped,
            "evidence": why,
            "edge_ink": ink,
            "target_page": e.get("target_page_id"),
            "caption": e.get("caption", "")[:160],
        }
        if cropped:
            if inked:
                new = clean_edges(new, doc, pno, all_caps, others, page_rect,
                                  blocks)
                row["new_bbox"] = [round(v, 1) for v in new]
                (row["grew_top_pt"], row["grew_bottom_pt"],
                 row["grew_left_pt"], row["grew_right_pt"]) = deltas(new)
            name = f"fixed-{e['png']}"
            doc[pno].get_pixmap(clip=new, dpi=dpi).save(out_dir / name)
            row["fixed_png"] = name
        rows.append(row)

    rows.sort(key=lambda r: (-len(r["evidence"]),
                             -max(r["grew_top_pt"], r["grew_bottom_pt"],
                                  r["grew_left_pt"], r["grew_right_pt"]),
                             r["chapter"], float(r["fig_id"].replace(".", "0")
                                                 if r["fig_id"].count(".") == 1 else 0)))
    (out_dir / "report.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
    write_html(out_dir, fig_dir, rows)
    return rows


def write_html(out_dir, fig_dir, rows):
    bad = [r for r in rows if r["cropped"]]
    rel = Path("..") / fig_dir.name
    parts = ["""<!doctype html><meta charset="utf-8">
<title>Nasr ed2 裁切稽核</title>
<style>
body{font:14px/1.6 -apple-system,'PingFang TC',sans-serif;margin:2rem;background:#faf9f5;color:#1b2430}
h1{font-size:1.4rem;margin:0 0 .3rem}.sub{color:#5b6570;margin:0 0 1.4rem}
.item{background:#fff;border:1px solid #d8dbd1;border-radius:12px;padding:1rem;margin-bottom:1rem}
.hd{display:flex;gap:.8rem;align-items:baseline;flex-wrap:wrap;margin-bottom:.5rem}
.fid{font-weight:700;font-size:1.05rem}
.tag{font:11px ui-monospace,Menlo,monospace;background:#f3e3c6;color:#8c5e17;border-radius:99px;padding:.15rem .6rem}
.cap{color:#5b6570;font-size:.82rem;margin:.2rem 0 .6rem}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:.8rem}
.pair figure{margin:0}.pair img{width:100%;border:1px solid #d8dbd1;border-radius:8px;display:block;background:#fff}
.pair figcaption{font:11px ui-monospace,Menlo,monospace;color:#5b6570;margin-top:.3rem}
.ok{color:#2f6b44}</style>
"""]
    parts.append(f"<h1>Nasr ed2 圖片裁切稽核</h1>")
    parts.append(f'<p class="sub">共檢查 {len(rows)} 張，判定被裁 '
                 f'<b>{len(bad)}</b> 張。左為現況（已上傳 Notion 的版本），'
                 f'右為依建議框重抽。判定僅供篩選，請目視確認後再決定要不要換。</p>')
    for r in bad:
        parts.append('<div class="item"><div class="hd">'
                     f'<span class="fid">Fig {r["fig_id"]}</span>'
                     f'<span class="tag">Ch{r["chapter"]} · 書 p.{r["book_page"]} · PDF idx{r["pdf_page"]}</span>'
                     f'<span class="tag">上 +{r["grew_top_pt"]}　下 +{r["grew_bottom_pt"]}'
                     f'　左 +{r["grew_left_pt"]}　右 +{r["grew_right_pt"]} pt</span>' 
                     + ''.join(f'<span class="tag">{html.escape(w)}</span>' for w in r["evidence"])
                     + ('' if r["include"] else '<span class="tag">include=false</span>')
                     + '</div>')
        parts.append(f'<p class="cap">{html.escape(r["caption"])}</p>')
        parts.append('<div class="pair">'
                     f'<figure><img src="{rel}/{r["png"]}"><figcaption>現況 {r["png"]}</figcaption></figure>'
                     f'<figure><img src="{r["fixed_png"]}"><figcaption>重抽 {r["fixed_png"]}</figcaption></figure>'
                     '</div></div>')
    if not bad:
        parts.append('<p class="ok">沒有偵測到被裁的圖。</p>')
    (out_dir / "report.html").write_text("\n".join(parts), "utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=str(Path.home() /
                    "Desktop/pediatric cardiac handbook TEE.pdf"))
    ap.add_argument("--dir", default="figures/nasr")
    ap.add_argument("--out", default="figures/nasr-audit")
    ap.add_argument("--dpi", type=int, default=200)
    a = ap.parse_args()

    rows = audit(a.pdf, a.dir, a.out, a.dpi)
    bad = [r for r in rows if r["cropped"]]
    print(f"檢查 {len(rows)} 張，判定被裁 {len(bad)} 張 → {a.out}/report.html")
    for r in bad:
        print(f"  Fig {r['fig_id']:>6}  Ch{r['chapter']:<2} 書p.{str(r['book_page']):<4}"
              f" 上+{r['grew_top_pt']:<5} 下+{r['grew_bottom_pt']:<5}"
              f" 左+{r['grew_left_pt']:<5} 右+{r['grew_right_pt']:<5}"
              f" {'; '.join(r['evidence'])}")
