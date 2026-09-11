"""來源設定表測試。"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch import sources  # noqa: E402


def test_七個來源代號齊全():
    assert {s["source"] for s in sources.SOURCES} == {
        "TSA", "TSCVA", "RAPM", "PAIN", "AIRWAY", "TWECCM", "TSCCM"
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


def test_tweccm只剩公告列表一筆():
    tweccm = [s for s in sources.SOURCES if s["source"] == "TWECCM"]
    assert len(tweccm) == 1
    assert tweccm[0]["parser"] == "tweccm"
    assert tweccm[0]["kind"] == "其他公告"


def test_tsccm抓最新資訊列表():
    tsccm = [s for s in sources.SOURCES if s["source"] == "TSCCM"]
    assert len(tsccm) == 1
    # 學會本體是 tsccm.org.tw；tweccm.org.tw 只是年會官網，別對調
    assert tsccm[0]["url"] == "https://www.tsccm.org.tw/news/news_list.asp"
    assert tsccm[0]["parser"] == "tsccm"


def test_同一則公告不會因為兩個來源而推兩次():
    # tweccm 首頁本身就含「其他公告」那四則的標題。首頁那筆 text diff 若還在，
    # 一則新公告會同時產出 TWECCM:130（公告列表，uid 取自檔案連結）與
    # TWECCM:<標題 hash>（首頁 diff）兩個 key，seen.json 的去重完全擋不住，
    # 同一則會推兩次而且兩則看起來都很正常。
    # 一般化成：同一個來源代號不可以同時有結構化 parser 與 text diff 兩種設定。
    kinds: dict[str, set[bool]] = {}
    for s in sources.SOURCES:
        kinds.setdefault(s["source"], set()).add(s["parser"] == "text")
    overlapping = sorted(k for k, v in kinds.items() if v == {True, False})
    assert overlapping == [], overlapping


def test_同一個來源代號最多一筆text設定():
    # text 來源的快照檔名是 snapshot_{source}.txt。同一個 source 有兩筆 text
    # 設定的話，後跑的會把先跑的快照整個蓋掉，兩邊從此每輪都誤判整頁新增，
    # 直接撞 new_lines_cap 天天告警——而測試筆數仍然分毫不差
    text_sources = [s["source"] for s in sources.SOURCES if s["parser"] == "text"]
    assert len(set(text_sources)) == len(text_sources), text_sources


def test_每個來源都有網址與parser名稱():
    assert len(sources.SOURCES) == 8      # 沒有這行，SOURCES 被清空時迴圈跑零圈也會過
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
