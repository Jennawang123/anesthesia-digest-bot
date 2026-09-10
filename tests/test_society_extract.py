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
