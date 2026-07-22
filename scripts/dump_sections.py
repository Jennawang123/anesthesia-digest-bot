#!/usr/bin/env python3
"""列出某章各 sub-page 的小節，以及已映射到該篇的圖與圖說。

指派 target_section 的工作底稿：把「可選的小節」與「要歸位的圖」並排列出，
不必逐張開圖檔。只讀不寫。

用法：
    python3 scripts/dump_sections.py 41 [42 43 ...]
"""

import json
import sys
from pathlib import Path

from map_figures import subpages_cached
from upload_figures import Notion, load_token

ROOT = Path(__file__).resolve().parent.parent


def main():
    q = json.loads((ROOT / "miller_queue.json").read_text(encoding="utf-8"))
    byid = {c["ch"]: c for c in q["chapters"]}
    notion = Notion(load_token())

    for ch in (int(a) for a in sys.argv[1:]):
        manifest = json.loads(
            (ROOT / f"figures/ch{ch}/manifest.json").read_text(encoding="utf-8"))
        pages = subpages_cached(notion, byid[ch]["notion_page_id"],
                                ROOT / f"figures/ch{ch}/.subpages.json")
        print(f"\n{'=' * 70}\nCh{ch} {byid[ch]['title']}\n{'=' * 70}")
        for p in pages:
            figs = [f for f in manifest
                    if f.get("include") and f.get("target_page_id") == p["id"]]
            if not figs and not p["range"]:
                continue
            rng = f"pp. {p['range'][0]}–{p['range'][1]}" if p["range"] else "無區間"
            print(f"\n■ {p['title']}  {rng}")
            print("  小節：")
            for s in p["sections"]:
                print(f"    · {s}")
            print(f"  圖（{len(figs)}）：")
            for f in figs:
                cap = " ".join(f["caption"].split())[:150]
                print(f"    {f['fig_id']:<7} p.{f['book_page']}  {cap}")


if __name__ == "__main__":
    main()
