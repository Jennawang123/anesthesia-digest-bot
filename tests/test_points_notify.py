"""四種訊息的排版。"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import notify  # noqa: E402
from points_watch.models import Promo, Rated  # noqa: E402


def _rated(program="IHG", kind="bonus", percent=100, cpp=0.5, best=0.5, grade="green",
           new_low=False, from_article=False, up_to=False, end=date(2026, 10, 31)):
    promo = Promo(program=program, kind=kind, percent=percent, stated_cpp=None,
                  end_date=end, up_to=up_to, url="https://x.test/a")
    return Rated(promo=promo, cpp=cpp, best_cpp=best, grade=grade,
                 new_low=new_low, from_article=from_article)


def test_green_at_best_with_up_to():
    assert notify.format_promos([_rated(up_to=True)]) == "\n".join([
        "💰 點數促銷",
        "",
        "🟢 IHG 買點 100% 加贈",
        "每點 0.50¢（平歷史最佳）",
        "⚠️ 最高可達，需登入確認個人優惠",
        "截止 10/31",
        "https://x.test/a",
    ])


def test_yellow_miles_shows_gap():
    text = notify.format_promos([_rated(
        program="ALASKA", percent=70, cpp=2.21, best=1.88, grade="yellow",
        end=date(2026, 10, 20))])
    assert "🟡 Alaska 買哩程 70% 加贈" in text
    assert "每哩 2.21¢（歷史最佳 1.88¢，貴 18%）" in text
    assert "截止 10/20" in text
    assert "最高可達" not in text


def test_discount_wording():
    text = notify.format_promos([_rated(program="CHOICE", kind="discount", percent=45,
                                        cpp=0.57, best=0.57)])
    assert "🟢 Choice 買點 45% 折扣" in text


def test_new_low():
    text = notify.format_promos([_rated(cpp=0.48, best=0.50, new_low=True)])
    assert "每點 0.48¢（🏆 新低，原最佳 0.50¢）" in text


def test_from_article_note_and_missing_end_date():
    text = notify.format_promos([_rated(from_article=True, end=None)])
    assert "（依文章報價）" in text
    assert "截止日未註明" in text


def test_green_sorted_before_yellow_and_blank_line_between():
    text = notify.format_promos([
        _rated(program="ALASKA", cpp=2.0, best=1.88, grade="yellow"),
        _rated(program="IHG"),
    ])
    assert text.index("🟢 IHG") < text.index("🟡 Alaska")
    assert "https://x.test/a\n\n🟡 Alaska" in text


def test_reminder():
    entries = [{"program": "IHG", "kind": "bonus", "percent": 100, "cpp": 0.5,
                "end_date": "2026-10-11", "url": "https://x.test/a"}]
    assert notify.format_reminder(entries, date(2026, 10, 9)) == "\n".join([
        "⏰ 促銷即將截止",
        "",
        "🟢 IHG 買點 100% 加贈",
        "每點 0.50¢｜10/11 截止（剩 2 天）",
        "https://x.test/a",
    ])


def test_reminder_last_day():
    entries = [{"program": "ALASKA", "kind": "bonus", "percent": 100, "cpp": 1.88,
                "end_date": "2026-10-09", "url": "https://x.test/a"}]
    assert "每哩 1.88¢｜10/9 截止（今天截止）" in notify.format_reminder(entries, date(2026, 10, 9))


def test_alert():
    text = notify.format_alert([("omaat", "RSS 無法解析，可能被擋或改版")])
    assert text.startswith("⚠️ 點數促銷監測異常")
    assert "・omaat：RSS 無法解析，可能被擋或改版" in text


def test_heartbeat():
    text = notify.format_heartbeat(feed_count=3, article_count=42, promo_count=7)
    assert text.startswith("💓 點數促銷監測運作正常")
    assert "3" in text and "42" in text and "7" in text
