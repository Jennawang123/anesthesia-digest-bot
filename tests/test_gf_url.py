"""Google Flights tfs URL 構造測試。

基準值 REAL_TFS 取自使用者 2026-08-18 在瀏覽器實際操作產生的網址，
不是推測值。任何改動都必須讓 build_tfs 逐字元重現它。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from gf_url import build_tfs, build_url  # noqa: E402

REAL_TFS = (
    "CBwQAhoeEgoyMDI2LTEyLTIzagcIARIDUFVTcgcIARIDVFBFGh4SCjIwMjctMDItMjZqBwgB"
    "EgNUUEVyBwgBEgNTRUEaHhIKMjAyNy0wMy0wN2oHCAESA1NFQXIHCAESA1RQRRoeEgoyMDI3"
    "LTA0LTIwagcIARIDVFBFcgcIARIDSUNOQAFIAXABggELCP___________wGYAQM"
)

GROUND_TRUTH_LEGS = [
    ("2026-12-23", "PUS", "TPE"),
    ("2027-02-26", "TPE", "SEA"),
    ("2027-03-07", "SEA", "TPE"),
    ("2027-04-20", "TPE", "ICN"),
]


def test_四段行程可逐字元重現真實tfs():
    assert build_tfs(GROUND_TRUTH_LEGS) == REAL_TFS


def test_url含正確路徑與固定參數():
    url = build_url(GROUND_TRUTH_LEGS, currency="KRW")
    assert url.startswith("https://www.google.com/travel/flights/search?tfs=")
    assert "tfu=EgIIACIA" in url
    assert "curr=KRW" in url


def test_改日期會產生不同tfs():
    other = [("2026-12-21", "PUS", "TPE")] + GROUND_TRUTH_LEGS[1:]
    assert build_tfs(other) != REAL_TFS


def test_兩段行程也能編碼():
    two = GROUND_TRUTH_LEGS[:2]
    assert isinstance(build_tfs(two), str)
    assert len(build_tfs(two)) < len(REAL_TFS)


# 使用者在 Google Flights 點「僅顯示直達航班」後產生的真實網址。
# 注意 Google 只把旗標加在第一段（UI 的篩選只套用當前段）。
GOOGLE_NONSTOP_FIRST_LEG = (
    "CBwQAhogEgoyMDI2LTEyLTIzKABqBwgBEgNQVVNyBwgBEgNUUEUaHhIKMjAyNy0wMi0yNmoH"
    "CAESA1RQRXIHCAESA1NFQRoeEgoyMDI3LTAzLTA3agcIARIDU0VBcgcIARIDVFBFGh4SCjIw"
    "MjctMDQtMjBqBwgBEgNUUEVyBwgBEgNJQ05AAUgBcAGCAQsI____________AZgBAw"
)

# 四段全部限定直飛（本專案實際要用的形式）
ALL_NONSTOP = (
    "CBwQAhogEgoyMDI2LTEyLTIzKABqBwgBEgNQVVNyBwgBEgNUUEUaIBIKMjAyNy0wMi0yNigA"
    "agcIARIDVFBFcgcIARIDU0VBGiASCjIwMjctMDMtMDcoAGoHCAESA1NFQXIHCAESA1RQRRog"
    "EgoyMDI3LTA0LTIwKABqBwgBEgNUUEVyBwgBEgNJQ05AAUgBcAGCAQsI____________AZgBAw"
)


def test_僅第一段限直飛可重現Google產生的網址():
    assert build_tfs(GROUND_TRUTH_LEGS, nonstop=[0]) == GOOGLE_NONSTOP_FIRST_LEG


def test_四段全限直飛():
    assert build_tfs(GROUND_TRUTH_LEGS, nonstop=True) == ALL_NONSTOP


def test_預設不限直飛時與原本相同():
    # 既有行為不可被破壞
    assert build_tfs(GROUND_TRUTH_LEGS) == REAL_TFS
    assert build_tfs(GROUND_TRUTH_LEGS, nonstop=False) == REAL_TFS


def test_build_url可帶直飛參數():
    u = build_url(GROUND_TRUTH_LEGS, nonstop=True)
    assert ALL_NONSTOP in u
