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

    HISTORY_MAX = 30

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

    def put_with_history(self, combo_id, record):
        """更新記錄並把舊價格推入 history。

        重掃時用這個而非 put()，才能累積出價格趨勢。

        若新結果沒有價格（例如當天暫時查無票），保留原記錄不動——
        否則一次查詢失敗就會把已知的價格洗掉。
        """
        old = self.data.get(combo_id)
        if not record.get("priceKRW"):
            if old:
                return          # 保留最後已知的價格
            self.put(combo_id, record)
            return

        if old and old.get("priceKRW"):
            hist = list(old.get("history") or [])
            hist.append({
                "priceKRW": old["priceKRW"],
                "priceTWD": old.get("priceTWD"),
                "scannedAt": old.get("scannedAt"),
            })
            record["history"] = hist[-self.HISTORY_MAX:]
        self.put(combo_id, record)

    def all_ok(self):
        """回傳所有成功且有價格的記錄。"""
        return {k: v for k, v in self.data.items()
                if v.get("status") == "ok" and v.get("priceKRW")}


# 重掃時要保留的詳掃欄位，快掃結果沒有這些。
_DETAIL_KEYS = ("legs", "detail", "allNonstop")


def merge_refresh(old, new):
    """把重掃（快掃）結果併回舊記錄。

    重掃只讀第一段列表，後三段沒有時刻；若直接覆蓋，詳掃補好的
    四段時刻會被洗掉，而最便宜的前 N 組正是詳掃過的那批。

    價格沒變視為同一班機，保留舊的時刻與 detail；價格變了代表換了
    班次或 fare bucket，舊時刻不可信，改採新結果並讓 detail 退回
    quick，下次 --detail 會重補。
    """
    if not old:
        return new
    if old.get("detail") != "full" or old.get("priceKRW") != new.get("priceKRW"):
        return new
    merged = dict(new)
    for k in _DETAIL_KEYS:
        if k in old:
            merged[k] = old[k]
    return merged


def merge_detail(old, new):
    """把詳掃結果併回既有記錄。

    詳掃是逐段點選後的具體航班報價，與快掃讀列表最低總價的量測方式
    不同（實測差約 163 韓元）。排序基準必須全檔一致，故 priceKRW
    沿用快掃價，詳掃價另存 detailPriceKRW——否則詳掃過的組價格微幅
    變高就被沒詳掃的擠下去，比價表前幾名永遠是「時刻待補」。
    （2026-08-20 實際踩到：--detail 20 跑完，前 25 名仍全部待補。）

    順帶保住 history，避免詳掃洗掉每日重掃累積的價格趨勢。
    """
    if not old:
        return new
    merged = dict(new)
    if old.get("priceKRW"):
        merged["detailPriceKRW"] = new.get("priceKRW")
        merged["priceKRW"] = old["priceKRW"]
        if old.get("priceTWD"):
            merged["priceTWD"] = old["priceTWD"]
    if old.get("history"):
        merged["history"] = old["history"]
    return merged


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
