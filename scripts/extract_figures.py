#!/usr/bin/env python3
"""依 caption 定位教科書 PDF 的 figure，整塊渲染成 PNG。

不使用 get_images()：Miller 各章的圖有的是純向量（Ch28 零內嵌圖片），
有的被切成上千個碎塊（Ch13 有 1740 個），逐張抽內嵌圖片得不到完整的圖。

用法：
    python3 scripts/extract_figures.py <章節PDF> <輸出目錄> [--dpi 200]
"""

import argparse
import json
import re
import unicodedata
from pathlib import Path

import fitz

CAPTION_RE = re.compile(r"^Fig(?:\.|ure)\s*(\d+)[.\-](\d+)")
# 任何圖說／表說都可以當作上邊界（用於上下堆疊的圖、圖緊接在表格下方的情況）
ANY_LABEL_RE = re.compile(r"^(?:Fig(?:\.|ure)|Table|Box)\s*\d+[.\-]\d+")
PAGE_NUM_RE = re.compile(r"^\d{3,4}$")

# 只有「內文字體」的 block 能當圖的上邊界。流程圖方框裡的字往往又長又寬
# （如 "Measure troponin daily for 48–72 h…"），純靠字數與寬度會誤判成內文，
# 把圖從中間切斷。內文字體由全書統計自動偵測，換書也成立。
MIN_BODY_CHARS = 25
# 裁切結果低於這個高度視為可疑，標記出來讓人工檢查。
MIN_PLAUSIBLE_HEIGHT = 40
# 留白要夠寬，否則跨欄流程圖貼著欄外的虛線連接線會被切掉（Fig. 28.7）
PAD = 10


def clean(text):
    """清掉 soft hyphen 與多餘空白。Elsevier 的 caption 內含 U+00AD。"""
    text = text.replace("­", "").replace(" ", " ")
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_pages(doc):
    """整份文件只做一次 dict 解析並快取。這步在向量密集的章節要一分鐘以上，
    字體統計、欄位偵測、逐頁抽圖都共用同一份結果。"""
    return [p.get_text("dict")["blocks"] for p in doc]


def body_font(pages):
    """全書字元數最多的 (字體, 字級) 即內文字體。Miller 是 PhotinaMT 10pt。"""
    tally = {}
    for blocks in pages:
        for b in blocks:
            if b["type"] != 0:
                continue
            for line in b["lines"]:
                for s in line["spans"]:
                    key = (s["font"], round(s["size"]))
                    tally[key] = tally.get(key, 0) + len(s["text"])
    return max(tally, key=tally.get)


def text_blocks(raw_blocks, body):
    """回傳頁面上的文字 block，附上該 block 是否以內文字體為主。"""
    out = []
    for b in raw_blocks:
        if b["type"] != 0:
            continue
        chars = body_chars = 0
        parts = []
        for line in b["lines"]:
            for s in line["spans"]:
                n = len(s["text"])
                chars += n
                if (s["font"], round(s["size"])) == body:
                    body_chars += n
                parts.append(s["text"])
            parts.append(" ")
        txt = clean("".join(parts))
        if not txt:
            continue
        out.append({
            "rect": fitz.Rect(b["bbox"]),
            "text": txt,
            "is_body": chars > 0 and body_chars / chars > 0.5,
        })
    return out


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def book_page_number(blocks):
    """從頁首/頁尾的 running head 取印刷頁碼。"""
    for b in blocks[:3] + blocks[-3:]:
        for line in b["text"].split():
            if PAGE_NUM_RE.match(line):
                return int(line)
    return None


def detect_columns(pages, body):
    """由全書內文 block 的左緣分群，推出版面欄位。Miller 為左右雙欄。

    寬度不能取自 caption —— 「Fig. 28.4 Tooth numbering.」這種短圖說只有 106pt，
    會把 239pt 寬的圖左右切掉。欄位右緣取成員的中位數，避免跨欄表格把欄寬撐大。
    """
    lefts = []
    for raw in pages:
        for b in text_blocks(raw, body):
            if b["is_body"] and b["rect"].width > 60:
                lefts.append(b["rect"])
    if not lefts:
        return []

    xs = sorted(r.x0 for r in lefts)
    groups = [[xs[0]]]
    for x in xs[1:]:
        if x - groups[-1][-1] <= 20:
            groups[-1].append(x)
        else:
            groups.append([x])

    cols = []
    for g in groups:
        if len(g) < 5:
            continue
        x0 = min(g)
        members = sorted(r.x1 for r in lefts if abs(r.x0 - x0) <= 20)
        cols.append((x0, members[len(members) // 2]))
    return cols


def band_for(cap, cols):
    """裁切寬度取自版面欄位，不取自 caption 寬度。

    短圖說有三種情形：落在單欄內（取該欄）、置中跨在欄間裝訂線上（取跨欄，
    如「Fig. 28.2, cont'd」只有 62pt 卻屬於整版表單）、完全比不到欄位
    （退回整個版心）。絕不退回 caption 自身寬度，那會把圖切窄。
    """
    if not cols:
        return cap.x0, cap.x1
    full = (min(c[0] for c in cols), max(c[1] for c in cols))
    touched = [c for c in cols if overlap(cap.x0, cap.x1, c[0], c[1]) > 2]
    if len(touched) >= 2:
        return min(c[0] for c in touched), max(c[1] for c in touched)
    if len(touched) == 1:
        c = touched[0]
        if overlap(cap.x0, cap.x1, c[0], c[1]) > 0.2 * (c[1] - c[0]):
            return c
    return full


def figure_rect(page, caption, blocks, cols):
    """圖的範圍 = caption 正上方、整欄寬，往上到最近的內文 block 底部。"""
    bx0, bx1 = band_for(caption["rect"], cols)
    cap = fitz.Rect(bx0, caption["rect"].y0, bx1, caption["rect"].y1)
    band_w = cap.width
    top_limit = page.rect.y0 + 36  # 頁邊距

    boundaries = []
    for b in blocks:
        r = b["rect"]
        if r.y1 > cap.y0 + 1:
            continue
        if overlap(r.x0, r.x1, cap.x0, cap.x1) < 0.3 * band_w:
            continue
        is_bound = (b["is_body"] and len(b["text"]) >= MIN_BODY_CHARS) or \
            ANY_LABEL_RE.match(b["text"])
        if not is_bound:
            continue  # 圖內文字（Helvetica 方框標籤等），不算邊界
        boundaries.append(r.y1)

    top = max(boundaries) + PAD if boundaries else top_limit
    return fitz.Rect(cap.x0 - PAD, top, cap.x1 + PAD, cap.y0 - 1)


def column_of(page, cap):
    mid = page.rect.width / 2
    if cap.width > 0.7 * (page.rect.width - 72):
        return "span"
    return "left" if cap.x1 < mid + 20 else "right"


def extract(pdf_path, out_dir, dpi):
    doc = fitz.open(pdf_path)
    out_dir = Path(out_dir)
    (out_dir).mkdir(parents=True, exist_ok=True)
    pages = parse_pages(doc)
    body = body_font(pages)
    cols = detect_columns(pages, body)

    manifest = []
    for pno, page in enumerate(doc):
        blocks = text_blocks(pages[pno], body)
        book_pg = book_page_number(blocks)
        for b in blocks:
            m = CAPTION_RE.match(b["text"])
            # 內文裡的交叉引用（「…as shown in Fig. 28.2」）用的是內文字體，
            # 真正的圖說不是。靠字體排除誤抓。
            if not m or b["is_body"]:
                continue
            fig_id = f"{m.group(1)}.{m.group(2)}"
            rect = figure_rect(page, b, blocks, cols)
            suspect = []
            if rect.height < MIN_PLAUSIBLE_HEIGHT:
                suspect.append("crop_too_short")
            if rect.height <= 0 or rect.width <= 0:
                suspect.append("empty_crop")
                continue

            # 檔名帶 PDF 頁碼，避免同一 fig_id 出現多次時互相覆蓋
            name = f"fig-{fig_id.replace('.', '-')}_p{pno}.png"
            pix = page.get_pixmap(clip=rect, dpi=dpi)
            pix.save(out_dir / name)

            manifest.append({
                "fig_id": fig_id,
                "pdf_page": pno,
                "book_page": book_pg,
                "caption": b["text"],
                "png": name,
                "bbox": [round(v, 1) for v in (rect.x0, rect.y0, rect.x1, rect.y1)],
                "column": column_of(page, b["rect"]),
                "suspect": suspect,
                "include": True,
                "target_page_id": None,
                "uploaded_block_id": None,
            })

    manifest.sort(key=lambda f: (f["pdf_page"], f["bbox"][1]))
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_contact_sheet(out_dir, manifest, Path(pdf_path).stem)
    return manifest


def write_contact_sheet(out_dir, manifest, title):
    cards = []
    for f in manifest:
        flag = ""
        if f["suspect"]:
            flag = f'<span class="flag">⚠ {" ".join(f["suspect"])}</span>'
        h = round(f["bbox"][3] - f["bbox"][1])
        w = round(f["bbox"][2] - f["bbox"][0])
        cards.append(f"""<figure>
  <img src="{f['png']}" alt="Fig. {f['fig_id']}">
  <figcaption>
    <b>Fig. {f['fig_id']}</b> {flag}
    <span class="meta">PDF p.{f['pdf_page']} · 書 p.{f['book_page']} · {f['column']} · {w}×{h}pt</span>
    <span class="cap">{f['caption'][:200]}</span>
  </figcaption>
</figure>""")

    html = f"""<!doctype html><meta charset="utf-8"><title>{title} — 圖表驗收</title>
<style>
 body{{font:15px/1.6 -apple-system,"PingFang TC",sans-serif;margin:24px;background:#fafafa;color:#222}}
 h1{{font-size:20px}} .n{{color:#666;font-size:13px;margin-bottom:20px}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:20px}}
 figure{{margin:0;background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:12px}}
 img{{width:100%;height:auto;display:block;border:1px solid #eee;background:#fff}}
 figcaption{{margin-top:8px;font-size:13px}}
 .meta{{display:block;color:#777;font-size:12px;margin:4px 0}}
 .cap{{display:block;color:#444;font-size:12px}}
 .flag{{color:#b00;font-weight:600}}
</style>
<h1>{title} — 圖表驗收</h1>
<div class="n">共 {len(manifest)} 張。請看裁切是否完整（圖有沒有被切掉、有沒有混進內文），以及哪幾張不需要放進筆記。</div>
<div class="grid">
{chr(10).join(cards)}
</div>"""
    (out_dir / "contact_sheet.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("out_dir")
    ap.add_argument("--dpi", type=int, default=200)
    a = ap.parse_args()
    m = extract(a.pdf, a.out_dir, a.dpi)
    print(f"抽出 {len(m)} 張圖 → {a.out_dir}")
    for f in m:
        if f["suspect"]:
            print(f"  ⚠ Fig. {f['fig_id']} (PDF p.{f['pdf_page']}): {f['suspect']}")
