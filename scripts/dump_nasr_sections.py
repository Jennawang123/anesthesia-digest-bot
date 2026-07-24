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
