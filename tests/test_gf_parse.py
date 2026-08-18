"""Google Flights 航班列表解析測試。

所有 fixture 均為 2026-08-18 實測抓取的真實文字，非捏造。
時刻對照基準為使用者提供的長榮官網截圖（BR163 18:55–20:25 等）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from gf_parse import parse_clock, parse_row  # noqa: E402


def test_下午轉24小時制():
    # 長榮官網截圖 BR163 為 18:55 起飛
    assert parse_clock("下午6:55") == ("18:55", 0)


def test_晚上轉24小時制():
    # 同班機抵達 20:25
    assert parse_clock("晚上8:25") == ("20:25", 0)


def test_晚上11點半夜航班():
    # TPE-SEA 截圖為 23:40
    assert parse_clock("晚上11:40") == ("23:40", 0)


def test_凌晨12點應為00點():
    # SEA-TPE 截圖為 00:10
    assert parse_clock("凌晨12:10") == ("00:10", 0)


def test_清晨不加12():
    assert parse_clock("清晨7:30") == ("07:30", 0)
    assert parse_clock("清晨5:20") == ("05:20", 0)


def test_上午不加12():
    assert parse_clock("上午11:00") == ("11:00", 0)


def test_中午12點不變():
    assert parse_clock("中午12:30") == ("12:30", 0)


def test_跨日標記回傳日數差():
    # 截圖 SEA-TPE 抵達為 05:20+1
    assert parse_clock("清晨5:20+1") == ("05:20", 1)


def test_無法解析回傳None():
    assert parse_clock("整趟行程") is None


# 以下 fixture 為 2026-08-18 實測抓取的真實列表文字
ROW_NONSTOP = ("下午6:55 |  –  | 晚上8:25 | 長榮航空 | 2 小時 30 分鐘 | "
               "PUS–TPE | 直達 | 154 公斤 CO2e | 比一般排放量高出 22% | "
               "￦1,774,600 | 整趟行程")

ROW_CONNECTING = ("下午2:55 |  –  | 下午1:05+1 | 長榮航空 | 15 小時 10 分鐘 | "
                  "VIE–TPE | 轉機 1 次 | 1 小時 20 分鐘 BKK | 591 公斤 CO2e | "
                  "比一般排放量低 10% | ￦2,401,200 | 整趟行程")


def test_解析直飛航班():
    r = parse_row(ROW_NONSTOP)
    assert r["depart"] == "18:55"
    assert r["arrive"] == "20:25"
    assert r["arrive_plus_days"] == 0
    assert r["carrier"] == "長榮航空"
    assert r["duration"] == "2 小時 30 分鐘"
    assert r["from"] == "PUS"
    assert r["to"] == "TPE"
    assert r["nonstop"] is True
    assert r["via"] is None
    assert r["price"] == 1774600


def test_解析轉機航班():
    r = parse_row(ROW_CONNECTING)
    assert r["from"] == "VIE"
    assert r["to"] == "TPE"
    assert r["nonstop"] is False
    assert r["via"] == "BKK"
    assert r["price"] == 2401200
    assert r["arrive_plus_days"] == 1


def test_價格用全形韓元符號():
    # 用半形 ₩ 寫 regex 會抓不到，這是實作時踩過的坑
    assert parse_row(ROW_NONSTOP)["price"] == 1774600


def test_非航班列無法解析回傳None():
    assert parse_row("價格為包含所有稅額及手續費的最終價格") is None
