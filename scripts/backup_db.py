#!/usr/bin/env python3
"""把 Supabase 的所有表倒成本機 CSV。

用法：
    python3 scripts/backup_db.py

連線字串從 macOS Keychain 讀取（service `jenna-supabase-db`），
所以不需要在硬碟上放明碼檔案。要換字串：
    security add-generic-password -U -s jenna-supabase-db -a "$USER" \\
        -T /usr/bin/security -w "$(cat 某個暫存檔)"
環境變數 DATABASE_URL 若有設會優先採用（方便臨時測試）。

輸出到 ~/Documents/db-backups/YYYY-MM-DD_HHMM/，每張表一個 CSV，
外加 _manifest.txt 記錄各表筆數。預設保留最近 12 份，更舊的自動刪除。

注意：備份檔絕對不能放進這個 repo（origin 是 public），故輸出路徑寫死在家目錄。
"""

import csv
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

# 放家目錄根層而非 ~/Documents：後者受 macOS TCC 保護，launchd 排程執行時
# 檔案寫得進去、os.listdir 卻會 PermissionError（2026-08-02 實測）。
BACKUP_ROOT = Path.home() / "db-backups"
KEYCHAIN_SERVICE = "jenna-supabase-db"
KEEP = 12


def read_url():
    """優先用環境變數，否則從 Keychain 取。"""
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", KEYCHAIN_SERVICE,
             "-a", os.environ.get("USER", "")],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as e:
        sys.exit(f"錯誤：讀取 Keychain 失敗：{e}")
    if out.returncode != 0:
        sys.exit(f"錯誤：Keychain 裡找不到 {KEYCHAIN_SERVICE}，請先寫入（見檔頭說明）。")
    return out.stdout.strip()


def main():
    url = read_url()
    if not url:
        sys.exit("錯誤：拿到空的連線字串。")
    url = url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        sys.exit("錯誤：這條連線字串不是 Postgres，八成是退回本機 SQLite 了。")

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    outdir = BACKUP_ROOT / stamp
    outdir.mkdir(parents=True, exist_ok=True)

    tables = sorted(inspect(engine).get_table_names(schema="public"))
    if not tables:
        sys.exit("錯誤：public schema 一張表都沒有，先確認連對資料庫。")

    counts = []
    with engine.connect() as conn:
        for t in tables:
            rows = conn.execute(text(f'SELECT * FROM public."{t}"'))
            cols = list(rows.keys())
            n = 0
            with open(outdir / f"{t}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for r in rows:
                    w.writerow(r)
                    n += 1
            counts.append((t, n))
            print(f"  {t:<24} {n:>7} 筆")

    manifest = outdir / "_manifest.txt"
    manifest.write_text(
        f"備份時間 {stamp}\n\n"
        + "\n".join(f"{t}\t{n}" for t, n in counts)
        + f"\n\n合計 {len(counts)} 張表 / {sum(n for _, n in counts)} 筆\n",
        encoding="utf-8",
    )

    print(f"\n完成 → {outdir}")
    prune()


def prune():
    """只留最近 KEEP 份備份。清理失敗不該讓已完成的備份被當成失敗。"""
    try:
        dirs = sorted((d for d in BACKUP_ROOT.iterdir() if d.is_dir()), reverse=True)
        for d in dirs[KEEP:]:
            shutil.rmtree(d)
            print(f"  清除舊備份 {d.name}")
    except Exception as e:
        print(f"  （清理舊備份失敗，不影響本次備份）{e}")


if __name__ == "__main__":
    main()
