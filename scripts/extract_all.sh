#!/bin/bash
# 對 miller_queue.json 中所有 status=done 的章節抽圖（Ch28 已完成，跳過）。
# 向量密集的章節每章要數分鐘，逐章串跑並印出進度。
cd "$(dirname "$0")/.." || exit 1

python3 - "$@" <<'PY'
import json, os, subprocess, sys, time

q = json.load(open("miller_queue.json"))
pdf_dir = q["pdf_dir"]
todo = [c for c in q["chapters"] if c["status"] == "done" and c["ch"] != 28]

for i, c in enumerate(todo, 1):
    out = f"figures/ch{c['ch']}"
    if os.path.exists(f"{out}/manifest.json"):
        print(f"[{i}/{len(todo)}] Ch{c['ch']} 已存在，跳過", flush=True)
        continue
    t = time.time()
    print(f"[{i}/{len(todo)}] Ch{c['ch']} {c['title']} …", flush=True)
    r = subprocess.run(
        ["python3", "scripts/extract_figures.py",
         os.path.join(pdf_dir, c["file"]), out],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(f"    失敗：{r.stderr.strip()[:300]}", flush=True)
    else:
        print(f"    {r.stdout.strip()}（{time.time() - t:.0f}s）", flush=True)
PY
