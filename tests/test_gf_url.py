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
