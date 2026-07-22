#!/usr/bin/env python3
"""把判斷好的 target_section（必要時連同 target_page_id）寫回 manifest。

輸入 JSON 從 stdin 讀，格式：
    {"41.1": "解剖與作用機轉",
     "41.4": {"section": "技術", "page": "<sub-page id>"}}

小節名稱必須與 Notion 上的 heading_3 完全相同，否則上傳時找不到錨點會退回
「二、圖表」。本腳本先驗證名稱存在於該篇的小節清單，不符就中止，不寫入。

用法：
    python3 scripts/set_sections.py 41 < assign.json
"""

import json
import sys
from pathlib import Path

from map_figures import subpages
from upload_figures import Notion, load_token

ROOT = Path(__file__).resolve().parent.parent


def main():
    ch = int(sys.argv[1])
    assign = json.load(sys.stdin)

    mpath = ROOT / f"figures/ch{ch}/manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    q = json.loads((ROOT / "miller_queue.json").read_text(encoding="utf-8"))
    byid = {c["ch"]: c for c in q["chapters"]}

    notion = Notion(load_token())
    pages = {p["id"]: p for p in subpages(notion, byid[ch]["notion_page_id"])}

    errors = []
    for f in manifest:
        spec = assign.get(f["fig_id"])
        if spec is None:
            continue
        if isinstance(spec, str):
            section, page_id = spec, f.get("target_page_id")
        else:
            section = spec["section"]
            page_id = spec.get("page", f.get("target_page_id"))
            # 頁碼區間分派錯篇時要能改指定，用標題片段比 id 好寫也好讀
            if page_id not in pages:
                hit = [p for p in pages.values() if page_id in p["title"]]
                if len(hit) == 1:
                    page_id = hit[0]["id"]

        page = pages.get(page_id)
        if page is None:
            errors.append(f"Fig {f['fig_id']}: target_page_id 不在本章 sub-page 中")
        elif section not in page["sections"]:
            errors.append(f"Fig {f['fig_id']}: 「{section}」不是"
                          f"「{page['title']}」的小節")
        else:
            f["target_page_id"] = page_id
            f["target_section"] = section

    if errors:
        sys.exit("未寫入，先修正：\n  " + "\n  ".join(errors))

    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    done = sum(1 for f in manifest if f.get("include") and f.get("target_section"))
    total = sum(1 for f in manifest if f.get("include"))
    print(f"Ch{ch}: 已指派 {done}/{total}")


if __name__ == "__main__":
    main()
