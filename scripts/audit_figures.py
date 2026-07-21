#!/usr/bin/env python3
"""比對各章「抽出的圖」與「全文出現過的圖號」，抓出漏抽。

抽圖靠 caption block + 字體判定；本腳本改用純文字掃描整份 PDF 的圖號作為
獨立對照，兩者不一致就是漏抽或誤抓。內文交叉引用也會出現圖號，所以
「全文圖號」是上界，正常情況應該等於抽出張數。

用法：
    python3 scripts/audit_figures.py
"""

import json
import re
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent


def main():
    q = json.loads((ROOT / "miller_queue.json").read_text(encoding="utf-8"))
    pdf_dir = Path(q["pdf_dir"])

    print(f"{'章':<6}{'抽出':>5}{'全文圖號':>9}  狀態")
    for c in q["chapters"]:
        if c["status"] != "done":
            continue
        d = ROOT / f"figures/ch{c['ch']}"
        mf = d / "manifest.json"
        if not mf.exists():
            print(f"Ch{c['ch']:<4}{'—':>5}{'—':>9}  尚未抽圖")
            continue

        manifest = json.loads(mf.read_text(encoding="utf-8"))
        got = {f["fig_id"].split(".", 1)[1] for f in manifest}

        doc = fitz.open(pdf_dir / c["file"])
        seen = set()
        # 圖號後面不能再接數字：內文交叉引用會把上標參考文獻編號黏上來，
        # 例如「Fig. 50.2」+ 上標 3383 → 「Fig. 50.23383」，會誤判成漏抽。
        # 圖號本身在 Miller 不超過兩位數。
        pat = re.compile(rf"Fig\.\s*{c['ch']}\.(\d{{1,2}})(?!\d)")
        for page in doc:
            seen |= set(pat.findall(page.get_text()))
        doc.close()

        missing = sorted(seen - got, key=int)
        extra = sorted(got - seen, key=int)
        status = "一致"
        if missing:
            status = f"⚠ 漏抽 {','.join(missing)}"
        if extra:
            status += f" / 多出 {','.join(extra)}"
        print(f"Ch{c['ch']:<4}{len(manifest):>5}{len(seen):>9}  {status}")


if __name__ == "__main__":
    main()
