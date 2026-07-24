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
