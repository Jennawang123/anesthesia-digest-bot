#!/usr/bin/env python3
"""把抽好的圖映射到 Notion sub-page，並列出各篇可用的小節供指派。

依 sub-page 標頭引言的 PDF 頁碼區間指派 target_page_id，例如：
    Miller's Anesthesia 10th ed. Ch 28 — Preoperative Evaluation, pp. 808–820（PDF pp. 1–12）

只讀不寫 Notion。target_section 由人判斷後再填，本腳本只負責把選項列出來。

用法：
    python3 scripts/map_figures.py figures/ch41 <章節 Notion page id>
"""

import argparse
import json
import re
import sys
from pathlib import Path

from upload_figures import Notion, load_token, section_names

# sub-page 標頭有三種寫法，不同章節是在不同 session 建的：
#   Ch28 型：… pp. 808–820（PDF pp. 1–12）        → PDF 頁碼是分章檔的
#   Ch41 型：… pp. 1267–1272                     → 只有書本頁碼
#   Ch72 型：… pp. 2266–2272（PDF pp. 2831–2837）→ PDF 頁碼是整本書的
# 三種都有書本頁碼，且 PDF 頁碼的意義不一致（Ch72 型拿去比對必然落空），
# 所以一律用書本頁碼比對，PDF 頁碼只在標頭沒有書本頁碼時才退而求其次。
BOOK_RANGE_RE = re.compile(r"(?<!PDF )pp?\.\s*(\d+)\s*[–\-—]\s*(\d+)")
PDF_RANGE_RE = re.compile(r"PDF\s*pp?\.\s*(\d+)\s*[–\-—]\s*(\d+)")


def rich_text(block):
    t = block["type"]
    return "".join(r["plain_text"] for r in block[t].get("rich_text", []))


def subpages_cached(notion, chapter_page_id, cache: Path):
    """sub-page 的標題與小節清單在指派過程中不會變，但每次列出都要打幾十次
    API 且會逾時。快取起來，只有加減小節時才需要刪掉重抓。"""
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    pages = subpages(notion, chapter_page_id)
    cache.write_text(json.dumps(pages, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return pages


def subpages(notion, chapter_page_id):
    """回傳章節底下每篇 sub-page 的 id、標題、PDF 頁碼區間、小節清單。"""
    out = []
    for b in notion.children(chapter_page_id):
        if b["type"] != "child_page":
            continue
        pid = b["id"]
        title = b["child_page"]["title"]
        blocks = notion.children(pid)

        rng = kind = None
        for blk in blocks[:5]:
            if blk["type"] not in ("quote", "paragraph", "callout"):
                continue
            text = rich_text(blk)
            m = BOOK_RANGE_RE.search(text)
            if m:
                rng, kind = (int(m.group(1)), int(m.group(2))), "book_page"
                break
            m = PDF_RANGE_RE.search(text)
            if m:
                rng, kind = (int(m.group(1)), int(m.group(2))), "pdf_page"
                break

        out.append({"id": pid, "title": title, "range": rng,
                    "key": kind, "sections": section_names(blocks)})
    return out


def fill_book_pages(manifest):
    """補上抽不到的 book_page（整頁大圖沒有頁眉頁碼）。

    同一章內 book_page - pdf_page 是固定位移，實測 13 章每章都只有一個值，
    所以用其他圖推回缺漏的那幾張是確定的，不是估計。位移不唯一時放棄補值。
    """
    offsets = {f["book_page"] - f["pdf_page"] for f in manifest
               if f.get("book_page")}
    if len(offsets) != 1:
        return 0
    off = offsets.pop()
    n = 0
    for f in manifest:
        if not f.get("book_page"):
            f["book_page"] = f["pdf_page"] + off
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("figures_dir")
    ap.add_argument("chapter_page_id")
    args = ap.parse_args()

    d = Path(args.figures_dir)
    mpath = d / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))

    filled = fill_book_pages(manifest)
    if filled:
        print(f"（補上 {filled} 張缺漏的書本頁碼）")

    notion = Notion(load_token())
    pages = subpages(notion, args.chapter_page_id)
    if not pages:
        sys.exit("找不到任何 sub-page，確認章節 page id 與 integration 權限。")

    print(f"=== {len(pages)} 篇 sub-page ===")
    for p in pages:
        label = {"pdf_page": "PDF pp.", "book_page": "書 pp."}.get(p["key"], "")
        rng = f"{label} {p['range'][0]}–{p['range'][1]}" if p["range"] else "⚠ 標頭讀不到頁碼區間"
        print(f"\n[{p['title']}]  {rng}")
        for s in p["sections"]:
            print(f"    - {s}")

    unmapped = []
    for f in manifest:
        if not f.get("include"):
            continue
        hit = [p for p in pages if p["range"] and f.get(p["key"]) is not None
               and p["range"][0] <= f[p["key"]] <= p["range"][1]]
        if len(hit) == 1:
            f["target_page_id"] = hit[0]["id"]
        elif len(hit) > 1:
            # 區間邊界重疊（前一篇的結束頁 = 下一篇的起始頁），取後者：
            # 圖多半屬於新起的段落。仍列出來讓人覆核。
            f["target_page_id"] = hit[-1]["id"]
            unmapped.append((f["fig_id"], f"落在 {len(hit)} 篇區間交界，暫指派後者"))
        else:
            f["target_page_id"] = None
            unmapped.append((f["fig_id"], "沒有符合的頁碼區間"))

    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                     encoding="utf-8")

    titles = {p["id"]: p["title"] for p in pages}
    print("\n=== 映射結果 ===")
    for f in manifest:
        if not f.get("include"):
            continue
        t = titles.get(f["target_page_id"], "⚠ 未映射")
        print(f"  Fig {f['fig_id']:<6} PDF p.{f['pdf_page']:<3} → {t}")
    if unmapped:
        print("\n需人工覆核：")
        for fid, why in unmapped:
            print(f"  Fig {fid}: {why}")
    print("\n下一步：填入每張圖的 target_section（上面各篇列出的小節名稱）。")


if __name__ == "__main__":
    main()
