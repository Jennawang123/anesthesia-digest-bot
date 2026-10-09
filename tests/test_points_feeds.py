"""RSS 解析測試。對 2026-10-09 實抓樣本。"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import feeds  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "points_watch"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_item_counts():
    assert len(feeds.parse_feed(_load("loyaltylobby.xml"), "loyaltylobby")) == 14
    assert len(feeds.parse_feed(_load("omaat_search.xml"), "omaat")) == 25
    assert len(feeds.parse_feed(_load("frequentmiler_search.xml"), "frequentmiler")) == 20


def test_fields_of_ihg_article():
    articles = feeds.parse_feed(_load("frequentmiler_search.xml"), "frequentmiler")
    ihg = next(a for a in articles if a.title == "Buy IHG Points for as low as 0.5 cents each")
    assert ihg.feed == "frequentmiler"
    assert ihg.url == "https://frequentmiler.com/buy-ihg-points/"
    assert isinstance(ihg.published, date)
    assert "100% bonus" in ihg.summary
    assert "<" not in ihg.summary          # HTML 標籤已去除
    assert len(ihg.summary) <= feeds.SUMMARY_MAX


def test_url_query_stripped():
    # Loyalty Lobby 的 link 帶 ?omhide=true
    articles = feeds.parse_feed(_load("loyaltylobby.xml"), "loyaltylobby")
    assert all("?" not in a.url for a in articles)
    assert all(a.url.startswith("https://loyaltylobby.com/") for a in articles)


def test_html_entities_decoded():
    articles = feeds.parse_feed(_load("omaat_search.xml"), "omaat")
    assert not any("&#" in a.title for a in articles)


def test_cloudflare_block_page_raises():
    # 被擋時回的是 HTML。必須拋例外讓 main 記成該 feed 失敗，
    # 不可回空 list——那會跟「今天沒文章」分不出來。
    with pytest.raises(feeds.FeedError):
        feeds.parse_feed(_load("blocked.html"), "loyaltylobby")


def test_non_rss_xml_raises():
    with pytest.raises(feeds.FeedError):
        feeds.parse_feed("<?xml version='1.0'?><html><body/></html>", "x")


def test_item_without_link_skipped():
    xml = ("<rss><channel>"
           "<item><title>no link</title></item>"
           "<item><title>ok</title><link>https://x.test/a?b=1#c</link>"
           "<pubDate>garbage</pubDate></item>"
           "</channel></rss>")
    articles = feeds.parse_feed(xml, "x")
    assert [(a.title, a.url, a.published) for a in articles] == [("ok", "https://x.test/a", None)]


def test_body_from_content_encoded():
    xml = ('<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>'
           "<title>t</title><link>https://x.test/a</link>"
           "<description>short</description>"
           "<content:encoded><![CDATA[<p>Between October 2 and <b>October 19</b>, 2026</p>"
           + "x" * 5000 + "]]></content:encoded>"
           "</item></channel></rss>")
    a = feeds.parse_feed(xml, "x")[0]
    assert a.body.startswith("Between October 2 and October 19 , 2026")
    assert len(a.body) == feeds.BODY_MAX


def test_body_empty_when_feed_has_no_full_text():
    articles = feeds.parse_feed(_load("loyaltylobby.xml"), "loyaltylobby")
    assert all(a.body == "" for a in articles)     # fixture 已去掉 content:encoded
