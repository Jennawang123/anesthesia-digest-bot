"""掃描結果儲存測試。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fare_store import LocalStore, merge_refresh  # noqa: E402


def test_寫入後可讀回(tmp_path):
    s = LocalStore(tmp_path / "f.json")
    s.put("abc", {"priceKRW": 1774600, "status": "ok"})
    assert s.get("abc")["priceKRW"] == 1774600


def test_已掃描過的id可判定(tmp_path):
    s = LocalStore(tmp_path / "f.json")
    s.put("abc", {"status": "ok"})
    assert s.has("abc") is True
    assert s.has("zzz") is False


def test_error狀態不算已掃描才能重試(tmp_path):
    # 斷點續跑時，錯誤的組合必須重跑，查無票的不必
    s = LocalStore(tmp_path / "f.json")
    s.put("e1", {"status": "error"})
    s.put("n1", {"status": "no_result"})
    assert s.has("e1") is False
    assert s.has("n1") is True


def test_落地為檔案且可重新載入(tmp_path):
    p = tmp_path / "f.json"
    LocalStore(p).put("abc", {"status": "ok", "priceKRW": 1})
    assert json.loads(p.read_text())["abc"]["priceKRW"] == 1
    assert LocalStore(p).has("abc") is True


def test_每次put都即時落地(tmp_path):
    # 掃描中途被中斷也不能掉資料
    p = tmp_path / "f.json"
    s = LocalStore(p)
    s.put("a", {"status": "ok"})
    assert "a" in json.loads(p.read_text())
    s.put("b", {"status": "ok"})
    assert "b" in json.loads(p.read_text())


def test_更新時把舊價格推入歷史(tmp_path):
    s = LocalStore(tmp_path / "f.json")
    s.put("a", {"status": "ok", "priceKRW": 100, "priceTWD": 2,
                "scannedAt": "2026-08-18T00:00:00+00:00"})
    s.put_with_history("a", {"status": "ok", "priceKRW": 120, "priceTWD": 3,
                             "scannedAt": "2026-08-19T00:00:00+00:00"})
    rec = s.get("a")
    assert rec["priceKRW"] == 120                      # 現值是新的
    assert len(rec["history"]) == 1                    # 舊值進歷史
    assert rec["history"][0]["priceKRW"] == 100
    assert rec["history"][0]["scannedAt"] == "2026-08-18T00:00:00+00:00"


def test_歷史會持續累積(tmp_path):
    s = LocalStore(tmp_path / "f.json")
    s.put("a", {"status": "ok", "priceKRW": 100})
    for p in (110, 120, 130):
        s.put_with_history("a", {"status": "ok", "priceKRW": p})
    assert [h["priceKRW"] for h in s.get("a")["history"]] == [100, 110, 120]


def test_歷史最多保留30筆(tmp_path):
    s = LocalStore(tmp_path / "f.json")
    s.put("a", {"status": "ok", "priceKRW": 0})
    for p in range(1, 40):
        s.put_with_history("a", {"status": "ok", "priceKRW": p})
    assert len(s.get("a")["history"]) == 30


def test_首次寫入不產生空歷史(tmp_path):
    s = LocalStore(tmp_path / "f.json")
    s.put_with_history("a", {"status": "ok", "priceKRW": 100})
    assert "history" not in s.get("a")


def test_查無票時不汙染歷史(tmp_path):
    # 某天暫時查不到票，不該把「無價格」寫進歷史
    s = LocalStore(tmp_path / "f.json")
    s.put("a", {"status": "ok", "priceKRW": 100})
    s.put_with_history("a", {"status": "no_result"})
    assert s.get("a")["priceKRW"] == 100      # 保留最後已知價格
    assert s.get("a")["status"] == "ok"


def test_重掃價格未變時保留詳掃時刻():
    # 重掃走快掃，只有第一段時刻；不可把詳掃補好的四段洗掉
    old = {"status": "ok", "priceKRW": 100, "detail": "full",
           "allNonstop": True, "scannedAt": "2026-08-18T00:00:00+00:00",
           "legs": [{"from": "PUS", "depart": "10:00"}] * 4}
    new = {"status": "ok", "priceKRW": 100, "detail": "quick",
           "priceTWD": 3, "scannedAt": "2026-08-19T00:00:00+00:00",
           "legs": [{"from": "PUS", "depart": "10:00"}, {}, {}, {}]}
    m = merge_refresh(old, new)
    assert m["detail"] == "full"
    assert m["allNonstop"] is True
    assert len(m["legs"][3]) > 0
    assert m["priceTWD"] == 3                                  # 新欄位有更新
    assert m["scannedAt"] == "2026-08-19T00:00:00+00:00"


def test_重掃價格變動時採用新結果():
    # 價格變了代表換了班次或 fare，舊時刻不可信，detail 退回 quick 待重補
    old = {"status": "ok", "priceKRW": 100, "detail": "full",
           "allNonstop": True, "legs": [{"depart": "10:00"}] * 4}
    new = {"status": "ok", "priceKRW": 130, "detail": "quick",
           "legs": [{"depart": "12:00"}, {}, {}, {}]}
    m = merge_refresh(old, new)
    assert m["detail"] == "quick"
    assert m["priceKRW"] == 130
    assert "allNonstop" not in m
