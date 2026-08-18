"""掃描結果儲存測試。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fare_store import LocalStore  # noqa: E402


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
