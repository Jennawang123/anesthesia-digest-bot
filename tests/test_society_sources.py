"""來源設定表測試。"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch import sources  # noqa: E402


def test_五個來源代號齊全():
    assert {s["source"] for s in sources.SOURCES} == {
        "TSA", "TSCVA", "RAPM", "PAIN", "AIRWAY"
    }


def test_pain抓去年今年明年三份():
    # 用完整字串比對而非子字串：只驗 "yy=2026" 的話，? 掉成路徑黏連
    # （…/0yy=2026）也會過，實際上等於沒帶 query param、靜默退回當年
    urls = sources.pain_urls(date(2026, 9, 10))
    assert urls == [
        f"{sources.PAIN_ENDPOINT}?yy={y}" for y in (2025, 2026, 2027)
    ]


def test_pain跨年時整個視窗往後推():
    urls = sources.pain_urls(date(2027, 1, 5))
    assert urls == [
        f"{sources.PAIN_ENDPOINT}?yy={y}" for y in (2026, 2027, 2028)
    ]


def test_pain視窗含去年以補跨年死角():
    # 視窗只往前滑的話，12/31 執行後才上架的當年項目 1/1 起永遠抓不到
    assert -1 in sources.PAIN_YEAR_OFFSETS


def test_rapm有兩個分類():
    rapm = [s for s in sources.SOURCES if s["source"] == "RAPM"]
    assert len(rapm) == 2
    assert {s["kind"] for s in rapm} == {"學會活動", "友會活動"}


def test_每個來源都有網址與parser名稱():
    assert len(sources.SOURCES) == 6      # 沒有這行，SOURCES 被清空時迴圈跑零圈也會過
    for s in sources.SOURCES:
        assert s["url"].startswith("https://")
        assert s["parser"]


def test_每筆設定的網址都不重複():
    # 兩筆 RAPM 是複製貼上來的，漏改 url 會讓友會活動永久不再監測，
    # 而且畫面上與其他測試都看不出來（kind 沒有被顯示在通知裡）
    urls = [s["url"] for s in sources.SOURCES]
    assert len(set(urls)) == len(urls)


def test_每個來源代號都有顯示名稱():
    assert set(sources.LABELS) == {s["source"] for s in sources.SOURCES}
    assert all(sources.LABELS.values())
