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


def test_pain同時抓今年與明年():
    urls = sources.pain_urls(date(2026, 9, 10))
    assert len(urls) == 2
    assert "yy=2026" in urls[0]
    assert "yy=2027" in urls[1]


def test_pain跨年時自動往後推():
    urls = sources.pain_urls(date(2027, 1, 5))
    assert "yy=2027" in urls[0]
    assert "yy=2028" in urls[1]


def test_rapm有兩個分類():
    rapm = [s for s in sources.SOURCES if s["source"] == "RAPM"]
    assert len(rapm) == 2
    assert {s["kind"] for s in rapm} == {"學會活動", "友會活動"}


def test_每個來源都有網址與parser名稱():
    for s in sources.SOURCES:
        assert s["url"].startswith("https://")
        assert s["parser"]
