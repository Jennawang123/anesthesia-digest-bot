#!/usr/bin/env python3
"""掃描結果的儲存。

本機 JSON 是唯一真實來源，支援斷點續跑；Firebase 只是給前端讀的同步副本。
掃描 864 組要跑近兩小時，中途中斷必須能接續，因此每筆 put 都立即落地。

Firebase Database URL 從環境變數 FOUR_LEG_FARE_DB 或
~/four_leg_fare.conf 讀取。本 repo 為 public，URL 絕不進版控。
"""

import json
import os
import urllib.request
from pathlib import Path

CONF = Path.home() / "four_leg_fare.conf"

# 這些狀態代表「已經有答案了」，續跑時可跳過。
# error 不在其中：那是查詢失敗，必須重試。
DONE_STATUSES = {"ok", "no_result"}


class LocalStore:
    """本機 JSON 儲存，每次寫入立即落地。"""

    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
        else:
            self.data = {}
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def has(self, combo_id):
        """是否已有可用結果（error 不算，需重試）。"""
        rec = self.data.get(combo_id)
        return bool(rec) and rec.get("status") in DONE_STATUSES

    def get(self, combo_id):
        return self.data.get(combo_id)

    def put(self, combo_id, record):
        self.data[combo_id] = record
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=1))

    def all_ok(self):
        """回傳所有成功且有價格的記錄。"""
        return {k: v for k, v in self.data.items()
                if v.get("status") == "ok" and v.get("priceKRW")}


def read_db_url():
    """讀 Firebase Database URL。找不到時回傳 None（僅本機儲存）。"""
    url = os.environ.get("FOUR_LEG_FARE_DB", "").strip()
    if url:
        return url.rstrip("/")
    if CONF.exists():
        for line in CONF.read_text().splitlines():
            line = line.strip()
            if line.startswith("FOUR_LEG_FARE_DB="):
                return line.split("=", 1)[1].strip().rstrip("/")
    return None


def push_firebase(db_url, combo_id, record, timeout=20):
    """PATCH 單筆記錄到 Firebase。

    只 PATCH 最深的子節點，不整包 PUT——整包 PUT 會洗掉其他欄位
    （專案先前踩過此坑）。
    """
    url = f"{db_url}/fares/{combo_id}.json"
    body = json.dumps(record, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url, data=body, method="PATCH",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status == 200
