"""RSS 2.0 文字 → Article。純解析，不碰網路。"""
import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit

from .models import Article

SUMMARY_MAX = 600   # 送給 Haiku 的摘要上限；實測 description 多在 300 字內

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


class FeedError(ValueError):
    """內容不是 RSS（被 Cloudflare 擋、站方改版、回了錯誤頁）。"""


def _clean(text: str | None) -> str:
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", text or ""))).strip()


def _strip_query(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _published(text: str | None):
    try:
        return parsedate_to_datetime(text or "").date()
    except (TypeError, ValueError):
        return None


def parse_feed(xml_text: str, feed: str) -> list[Article]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError as e:
        raise FeedError("RSS 無法解析，可能被擋或改版") from e
    if root.tag != "rss":
        raise FeedError("RSS 無法解析，可能被擋或改版")

    articles = []
    for item in root.findall("./channel/item"):
        link = item.findtext("link")
        title = _clean(item.findtext("title"))
        if not link or not title:
            continue
        articles.append(Article(
            feed=feed,
            title=title,
            url=_strip_query(link),
            published=_published(item.findtext("pubDate")),
            summary=_clean(item.findtext("description"))[:SUMMARY_MAX],
        ))
    return articles
