#!/usr/bin/env python3
"""依 raster 圖框抽取 Nasr ed2 的 figure。

與 extract_figures.py（Miller 專用）的前提相反：Nasr 第二版全書向量繪圖
物件為 0，每張圖都是完整的內嵌 raster，圖框本身就是精確的裁切邊界，
不需要 Miller 那套「從 caption 往上找內文邊界」的啟發式。

用法：
    python3 scripts/extract_figures_raster.py <PDF> <輸出目錄> [--chapters 8 9] [--dpi 200]
"""

import argparse
import json
import re
from pathlib import Path

import fitz

from extract_figures import (body_font, detect_columns, figure_rect, parse_pages,
                             text_blocks, write_contact_sheet)

# 每頁固定有兩張整頁尺寸的背景層，不是圖
BG_MIN_W, BG_MIN_H = 440, 640
# 小於這個尺寸的是裝飾碎塊（項目符號、logo）
MIN_RASTER = 20

# Nasr 用「Figure 8.1」全字，Miller 用「Fig. 28.3」。複數形 Figures 因為
# 「Figure」後面接的是 s 而非空白或數字，天然不會命中。
CAPTION_RE = re.compile(r"^Figure\s*(\d+)\.(\d+)")

# 配對時要求的最小重疊比例
MIN_OVERLAP = 0.3
# 圖與圖說的垂直間隙上限（頁高的比例）。超過就不是同一張圖，
# 用來擋掉頁頂的裝飾圖示被下方的圖說認領。
MAX_GAP = 0.6

# 裁切留白。Nasr 的 raster 框已經很貼合，不需要 Miller 那麼寬的 10pt
PAD = 6
# 頁眉的 y 上限；超過這個位置的第一個 block 不是頁眉
HEAD_Y = 60
PAGE_NUM_RE = re.compile(r"^\d{1,3}$")

# 聯集後超過版心這個倍數視為可疑，可能把鄰圖也吃進來了
OVERSIZE = 1.2
# 幾何 fallback 裁出的高度低於這個值視為失敗
MIN_PLAUSIBLE_HEIGHT = 40


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

    只有一張圖、而且那張圖剛好落在沒有頁眉的頁面時，該章拿不出任何位移
    基準（實測 Ch4 的 Fig 4.1）。這種情況退而求其次，借用章號最接近的
    那一章的位移——位移是隨章號單調漂移的，鄰章的值誤差最小。
    """
    seen = {}
    for f in figs:
        if f["book_page"]:
            seen.setdefault(f["nasr_chapter"], []).append(
                f["pdf_page"] - f["book_page"])
    offset = {ch: max(set(v), key=v.count) for ch, v in seen.items()}
    if not offset:
        return
    for f in figs:
        if f["book_page"]:
            continue
        ch = f["nasr_chapter"]
        near = min(offset, key=lambda k: (abs(k - ch), k))
        f["book_page"] = f["pdf_page"] - offset.get(ch, offset[near])


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
