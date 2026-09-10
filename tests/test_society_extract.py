"""各學會 parser 測試。全部對 2026-09-10 實抓 fixture 離線測試。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch import extract  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "society_watch"


def _fx(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ── TSA ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def tsa_events():
    return extract.parse_tsa(_fx("tsa_events_20260910.html"))


def test_tsa_抽出十五筆(tsa_events):
    assert len(tsa_events) == 15


def test_tsa_首筆欄位(tsa_events):
    e = tsa_events[0]
    assert e.source == "TSA"
    assert e.uid == "3105"
    assert e.date_text == "115/11/08"
    assert e.kind == "鎮靜活動"
    assert e.title == "台灣麻醉醫學會2026年健康台灣深耕計畫暨特管法輕中度鎮靜課程_1108高醫場"
    assert e.place == "高雄醫學大學國際學術研究大樓三樓臨床技能中心"
    assert e.url == "https://www.anesth.org.tw/events/content.asp?ID=3105&EduType=4"


def test_tsa_跨日活動日期保留起訖(tsa_events):
    e = next(x for x in tsa_events if x.uid == "3091")
    assert e.date_text == "115/09/26 ~ 115/09/27"


def test_tsa_民國年不做轉換(tsa_events):
    # 115 年即 2026 年，但一律不轉換：不轉換就不會轉錯
    assert all(not x.date_text.startswith("20") for x in tsa_events)


def test_tsa_全部不降級(tsa_events):
    assert all(x.minor is False for x in tsa_events)


# ── TSCVA ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def tscva_events():
    return extract.parse_tscva(_fx("tscva_news_20260910.html"))


def test_tscva_抽出六筆(tscva_events):
    assert len(tscva_events) == 6


def test_tscva_首筆欄位(tscva_events):
    e = tscva_events[0]
    assert e.source == "TSCVA"
    assert e.uid == "e9003f5d-1793-4fc4-babe-d031dd36b18b"
    assert e.date_text == "2026-09-01"
    assert e.title == "【恭賀通過名單】2026 年度 TSCVA 專科醫師甄審通過名單"
    assert e.url == "https://congress.tscva.org.tw/news/e9003f5d-1793-4fc4-babe-d031dd36b18b"
    assert e.minor is True


def test_tscva_降級命中三筆(tscva_events):
    # 「恭賀通過名單」「獲獎名單」「甄審條件及資格」命中；
    # 「報告順序」「甄選辦法」不含關鍵字，刻意不追加規則去攔（over-fitting）
    assert sum(1 for x in tscva_events if x.minor) == 3


def test_tscva_即將辦理活動不降級(tscva_events):
    e = next(x for x in tscva_events if x.title.startswith("[即將辦理活動]"))
    assert e.minor is False
