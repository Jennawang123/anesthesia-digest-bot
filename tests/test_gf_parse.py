"""Google Flights 航班列表解析測試。

所有 fixture 均為 2026-08-18 實測抓取的真實文字，非捏造。
時刻對照基準為使用者提供的長榮官網截圖（BR163 18:55–20:25 等）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from gf_parse import parse_clock  # noqa: E402


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
