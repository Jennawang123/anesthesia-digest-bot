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


# ── RAPM ──────────────────────────────────────────────────────────────────────

def test_rapm_學會活動抽出十六筆():
    events = extract.parse_rapm(_fx("rapm_newslist2_20260910.html"), kind="學會活動")
    assert len(events) == 16


def test_rapm_首筆欄位():
    events = extract.parse_rapm(_fx("rapm_newslist2_20260910.html"), kind="學會活動")
    e = events[0]
    assert e.source == "RAPM"
    assert e.uid == "32"
    assert e.date_text == "2026-08-26"
    assert e.kind == "學會活動"
    assert e.url == "https://rapm.org.tw/news-detail/32"
    # 活動日只在標題裡（＠November 1），不嘗試抽出
    assert e.title == "疼痛擂台 8：真實病人工作坊-全脊守護，從頸到骶 ＠November 1"


def test_rapm_標題壓平樣板空白():
    events = extract.parse_rapm(_fx("rapm_newslist2_20260910.html"), kind="學會活動")
    assert all("\n" not in x.title and "  " not in x.title for x in events)


def test_rapm_友會活動抽出十一筆():
    events = extract.parse_rapm(_fx("rapm_newslist5_20260910.html"), kind="友會活動")
    assert len(events) == 11
    assert events[0].uid == "23"
    assert events[0].kind == "友會活動"


def test_rapm_兩分類編號不重疊():
    a = extract.parse_rapm(_fx("rapm_newslist2_20260910.html"), kind="學會活動")
    b = extract.parse_rapm(_fx("rapm_newslist5_20260910.html"), kind="友會活動")
    assert not ({x.uid for x in a} & {x.uid for x in b})


def test_rapm_相對路徑連結會補成絕對網址():
    # 該站目前給絕對網址，但改版成相對路徑時不可靜默產出無效連結
    html = """<div class="service_item">
      <div class="service_title"><a href="/news-detail/99">測試公告</a></div>
      <div class="service_date">2026-09-01</div>
    </div>"""
    e = extract.parse_rapm(html, kind="學會活動")[0]
    assert e.url == "https://rapm.org.tw/news-detail/99"


def test_rapm_缺日期節點仍收錄不漏報():
    # 漏報是本系統最該避免的失效，缺欄位給空字串而非整筆丟棄
    html = """<div class="service_item">
      <div class="service_title"><a href="https://rapm.org.tw/news-detail/98">沒有日期的公告</a></div>
    </div>"""
    events = extract.parse_rapm(html, kind="學會活動")
    assert len(events) == 1
    assert events[0].uid == "98"
    assert events[0].date_text == ""


# ── PAIN ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def pain_events():
    return extract.parse_pain(_fx("pain_fragment_20260910.html"))


def test_pain_抽出十筆(pain_events):
    assert len(pain_events) == 10


def test_pain_首筆欄位(pain_events):
    e = pain_events[0]
    assert e.source == "PAIN"
    assert e.uid == "3142"
    assert e.date_text == "2026 八月 23"
    assert e.title.startswith("2026 台灣疼痛醫學會 全人整合醫學教育 系列工作坊")


def test_pain_全部連到列表頁(pain_events):
    # 該站無逐則網址（詳細是 onclick 不是 href）
    assert all(
        x.url == "https://pain.org.tw/index.php/educlass_page/index/33/1/8/34"
        for x in pain_events
    )


def test_pain_空表回傳空list():
    # 明年度尚無活動時，該 endpoint 回的是只有表頭的空表
    assert extract.parse_pain("<table class='table'><tbody></tbody></table>") == []


def test_pain_缺text_info時退回整格文字不漏報():
    # text-info 是 Bootstrap utility class，站方改版可能換掉，
    # 缺它不可讓整筆無聲消失
    html = """<table><tbody><tr>
      <td><span>2026</span><span>九月</span><span>15</span></td>
      <td>沒有包在 text-info 裡的活動名稱</td>
      <td><a onclick="cal_listview_click_func('9001')">詳細</a></td>
    </tr></tbody></table>"""
    events = extract.parse_pain(html)
    assert len(events) == 1
    assert events[0].uid == "9001"
    assert events[0].title == "沒有包在 text-info 裡的活動名稱"
    assert events[0].date_text == "2026 九月 15"
