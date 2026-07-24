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
