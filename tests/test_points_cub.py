"""國泰世華清單與活動頁解析。對 2026-10-09 實抓樣本。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import cub  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "points_watch"
PROMO_TITLE = "秋日遊-點數轉換指定航空里程/飯店積分限時加碼"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _promo():
    return next(c for c in cub.parse_list(_load("cub_list.json")) if c.title == PROMO_TITLE)


def test_list_count():
    assert len(cub.parse_list(_load("cub_list.json"))) == 149


def test_promo_campaign_fields():
    c = _promo()
    assert c.path == ("/content/cub-aem-cs/zh-tw/cathaybk/personal/event/overview/"
                      "credit-card/travel/202609/miles20251011.html")
    assert c.url == ("https://www.cathay-cube.com.tw/cathaybk/personal/event/overview/"
                     "credit-card/travel/202609/miles20251011")
    assert c.modified == "2026-09-18T08:58:04.436+00:00"
    assert c.key == c.path + "|2026-09-18T08:58:04.436+00:00"
    assert "最高加碼50%回饋無上限" in c.blurb
    assert cub.page_json_url(c) == c.url + ".model.json"


def test_candidates_are_exactly_the_three_known():
    titles = {c.title for c in cub.parse_list(_load("cub_list.json")) if cub.is_candidate(c)}
    assert titles == {
        PROMO_TITLE,
        "小樹點(信用卡)兌換航空里程/飯店積分｜國泰世華商業銀行",
        "PChome 24h購物2026/10_累積加碼活動",
    }


@pytest.mark.parametrize("text, message", [
    ("<!DOCTYPE html><html></html>", "活動清單不是 JSON"),
    ("[]", "活動清單為空或結構改變"),
    ('{"campaigns": []}', "活動清單為空或結構改變"),
    ('{"items": [{"campaignPath": "/a.html"}]}', "活動清單為空或結構改變"),
    # 有資料但欄位全改名：不可回空 list，那會跟「沒有活動」分不出來
    ('{"campaigns": [{"path": "/a.html", "props": {"title": "x"}}]}', "活動清單結構改變"),
])
def test_broken_list_raises(text, message):
    with pytest.raises(cub.CubError, match=message):
        cub.parse_list(text)


def test_items_missing_fields_are_skipped_when_others_are_fine():
    text = json.dumps({"campaigns": [
        {"campaignPath": "/content/cub-aem-cs/zh-tw/x/a.html", "campaignProps": {"jcr:title": "A"}},
        {"campaignPath": "/content/cub-aem-cs/zh-tw/x/b.html", "campaignProps": {}},
        {"campaignProps": {"jcr:title": "C"}},
        "garbage",
    ]})
    got = cub.parse_list(text)
    assert [(c.title, c.url, c.blurb, c.modified) for c in got] == [
        ("A", "https://www.cathay-cube.com.tw/x/a", "", "")]


def test_promo_page_text():
    text = cub.page_text(_load("cub_promo_page.json"))
    assert 2000 < len(text) < 6000
    for needle in ("亞洲萬里通", "JAL哩程儲蓄專案", "洲際優悅會", "法航荷航藍天飛行",
                   "加贈 30%", "登錄限量2,000名", "2026年10月28日16:00"):
        assert needle in text
    assert "<" not in text and "&nbsp;" not in text and "\xa0" not in text


def test_standing_page_text_has_no_bonus():
    text = cub.page_text(_load("cub_standing_page.json"))
    assert len(text) > 2000
    assert "加贈" not in text


@pytest.mark.parametrize("text, message", [
    ("<html>", "活動頁不是 JSON"),
    ('{"title": "x"}', "活動頁找不到內文"),
    ('{":items": {"m": {":type": "a/cub-main/v1/cub-main", "text": "太短"}}}', "活動頁內文過短"),
])
def test_broken_page_raises(text, message):
    with pytest.raises(cub.CubError, match=message):
        cub.page_text(text)
