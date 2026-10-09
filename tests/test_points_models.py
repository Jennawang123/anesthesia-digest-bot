"""資料模型測試：去重鍵的組成。"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch.models import Article, Promo  # noqa: E402


def _article(url="https://x.test/a", published=date(2026, 10, 2)):
    return Article(feed="omaat", title="t", url=url, published=published, summary="s")


def _promo(**over):
    base = dict(program="IHG", kind="bonus", percent=100, stated_cpp=0.5,
                end_date=date(2026, 10, 31), up_to=True, url="https://x.test/a")
    base.update(over)
    return Promo(**base)


def test_article_key_includes_publish_date():
    # OMAAT 每個計畫共用固定網址，只更新 pubDate；鍵只用 URL 的話，
    # 第一次促銷之後該計畫在 OMAAT 就永遠被當成「看過了」。
    a = _article(published=date(2026, 10, 2))
    b = _article(published=date(2026, 11, 20))
    assert a.key != b.key


def test_article_key_without_date():
    assert _article(published=None).key == "https://x.test/a|"


def test_promo_key_ignores_url_and_stated_cpp():
    # 同一促銷被兩家部落格報導，網址與報價寫法不同，仍是同一筆
    a = _promo(url="https://a.test/1", stated_cpp=0.5)
    b = _promo(url="https://b.test/2", stated_cpp=None)
    assert a.key == b.key == "IHG|bonus|100|2026-10-31"


def test_promo_key_differs_by_end_date():
    assert _promo().key != _promo(end_date=date(2026, 12, 5)).key


def test_promo_key_without_end_date():
    assert _promo(end_date=None).key == "IHG|bonus|100|"
