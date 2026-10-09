"""主流程測試。網路、Haiku、LINE 全部以假函式取代，狀態檔寫到 tmp_path。"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import extract, main  # noqa: E402
from points_watch.models import Promo  # noqa: E402

TODAY = date(2026, 10, 9)
BASELINES = (
    '{\n'
    '  "IHG":        {"base_cpp": 1.00, "best_cpp": 0.50},\n'
    '  "ALASKA":     {"base_cpp": 3.76, "best_cpp": 1.88}\n'
    '}\n'
)


def _rss(*items: tuple[str, str]) -> str:
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link>"
        "<pubDate>Thu, 08 Oct 2026 06:00:00 +0000</pubDate>"
        "<description>d</description></item>"
        for t, u in items
    )
    return f"<rss><channel>{body}</channel></rss>"


IHG_ITEM = ("Buy IHG Points for as low as 0.5 cents each", "https://fm.test/ihg")
NOISE = ("Some airline news", "https://fm.test/news")


def _promo(program="IHG", percent=100, end=date(2026, 10, 31), url="https://fm.test/ihg"):
    return Promo(program=program, kind="bonus", percent=percent, stated_cpp=None,
                 end_date=end, up_to=False, url=url)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """預設：三個 feed 都回同一份含一篇 IHG 文章的 RSS，Haiku 回 IHG 100%。"""
    (tmp_path / "baselines.json").write_text(BASELINES, encoding="utf-8")
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)

    box = {"pushed": [], "feeds": {}, "extract": lambda a, t: _promo(), "calls": []}

    def fake_get(url, **kw):
        result = box["feeds"].get(url.split("?")[0], _rss(IHG_ITEM, NOISE))
        if isinstance(result, Exception):
            raise result
        return result

    def fake_extract(article, today):
        box["calls"].append(article.title)
        return box["extract"](article, today)

    monkeypatch.setattr(main.fetch, "get", fake_get)
    monkeypatch.setattr(main.extract, "extract", fake_extract)
    monkeypatch.setattr(main, "push_line", box["pushed"].append)
    box["dir"] = tmp_path
    return box


def _json(env, name):
    return json.loads((env["dir"] / name).read_text(encoding="utf-8"))


def test_pushes_green_once_and_records_state(env):
    failures = main.run(today=TODAY)
    assert failures == []
    promo_msgs = [m for m in env["pushed"] if m.startswith("💰")]
    assert len(promo_msgs) == 1 and "🟢 IHG 買點 100% 加贈" in promo_msgs[0]
    assert env["calls"] == [IHG_ITEM[0]]            # 同文出現在三個 feed 只判讀一次；雜訊不送
    assert "IHG|bonus|100|2026-10-31" in _json(env, "promos.json")
    assert _json(env, "seen_articles.json")["seen"] == ["https://fm.test/ihg|2026-10-08"]


def test_second_run_is_silent(env):
    main.run(today=TODAY)
    env["pushed"].clear(), env["calls"].clear()
    main.run(today=TODAY)
    assert env["pushed"] == [] and env["calls"] == []


def test_same_promo_from_another_article_not_pushed_twice(env):
    main.run(today=TODAY)
    env["pushed"].clear()
    env["feeds"]["https://loyaltylobby.com/feed/"] = _rss(
        ("IHG Buy Points 100% Bonus Sale Through October 31", "https://ll.test/ihg"))
    main.run(today=TODAY)
    assert not [m for m in env["pushed"] if m.startswith("💰")]


def test_red_is_recorded_but_not_pushed(env):
    env["extract"] = lambda a, t: _promo(percent=50)      # 0.67，red
    main.run(today=TODAY)
    assert not [m for m in env["pushed"] if m.startswith("💰")]
    assert _json(env, "promos.json")["IHG|bonus|50|2026-10-31"]["grade"] == "red"


def test_not_a_promo_is_marked_seen(env):
    env["extract"] = lambda a, t: None
    main.run(today=TODAY)
    assert _json(env, "seen_articles.json")["seen"]
    assert not (env["dir"] / "promos.json").exists() or _json(env, "promos.json") == {}


def test_extract_failure_alerts_and_retries_next_day(env):
    def boom(a, t):
        raise extract.ExtractError("Haiku 回應不含 JSON")
    env["extract"] = boom
    failures = main.run(today=TODAY)
    # 三個 feed 回同一篇，collect 保留最先出現的那份，所以來源是 loyaltylobby
    assert failures == [("loyaltylobby／抽取", "Haiku 回應不含 JSON")]
    assert any(m.startswith("⚠️ 點數促銷監測異常") for m in env["pushed"])
    seen = (env["dir"] / "seen_articles.json")
    assert not seen.exists() or _json(env, "seen_articles.json")["seen"] == []


def test_suspicious_price_alerts_and_leaves_baseline_alone(env):
    env["extract"] = lambda a, t: _promo(percent=250)
    failures = main.run(today=TODAY)
    assert failures and "疑似抽取錯誤" in failures[0][1]
    assert (env["dir"] / "baselines.json").read_text(encoding="utf-8") == BASELINES
    assert not [m for m in env["pushed"] if m.startswith("💰")]


def test_new_low_updates_baseline_minimally(env):
    env["extract"] = lambda a, t: _promo(percent=110)     # 0.48
    main.run(today=TODAY)
    assert any("🏆 新低" in m for m in env["pushed"])
    assert (env["dir"] / "baselines.json").read_text(encoding="utf-8") == \
        BASELINES.replace('"best_cpp": 0.50', '"best_cpp": 0.48')


def test_one_feed_down_others_continue(env):
    env["feeds"]["https://onemileatatime.com/feed/"] = requests.ConnectionError("x")
    failures = main.run(today=TODAY)
    assert [s for s, _ in failures] == ["omaat"]
    assert any(m.startswith("💰") for m in env["pushed"])
    assert any(m.startswith("⚠️") for m in env["pushed"])


def test_empty_feed_is_a_failure(env):
    env["feeds"]["https://frequentmiler.com/feed/"] = _rss()
    failures = main.run(today=TODAY)
    assert ("frequentmiler", "RSS 回傳 0 篇，疑似改版") in failures


def test_alert_throttled_within_seven_days(env):
    env["feeds"]["https://onemileatatime.com/feed/"] = requests.ConnectionError("x")
    main.run(today=TODAY)
    env["pushed"].clear()
    main.run(today=date(2026, 10, 10))
    assert not [m for m in env["pushed"] if m.startswith("⚠️")]


def test_push_failure_leaves_state_untouched(env, monkeypatch):
    def fail(text):
        raise requests.HTTPError("500")
    monkeypatch.setattr(main, "push_line", fail)
    with pytest.raises(requests.HTTPError):
        main.run(today=TODAY)
    assert not (env["dir"] / "seen_articles.json").exists()
    assert not (env["dir"] / "promos.json").exists()


def test_bootstrap_marks_seen_without_extract_or_push(env):
    main.run(bootstrap=True, today=TODAY)
    assert env["pushed"] == [] and env["calls"] == []
    assert _json(env, "seen_articles.json")["seen"] == ["https://fm.test/ihg|2026-10-08"]
    main.run(today=TODAY)
    assert not [m for m in env["pushed"] if m.startswith("💰")]


def test_dry_run_prints_but_writes_nothing(env, capsys):
    main.run(dry_run=True, today=TODAY)
    assert env["pushed"] == []
    assert "🟢 IHG 買點 100% 加贈" in capsys.readouterr().out
    assert sorted(p.name for p in env["dir"].iterdir()) == ["baselines.json"]


def test_reminder_sent_once_when_two_days_left(env):
    env["extract"] = lambda a, t: _promo(end=date(2026, 10, 20))
    main.run(today=TODAY)
    env["pushed"].clear()
    main.run(today=date(2026, 10, 17))
    assert not [m for m in env["pushed"] if m.startswith("⏰")]
    main.run(today=date(2026, 10, 18))
    assert len([m for m in env["pushed"] if m.startswith("⏰")]) == 1
    env["pushed"].clear()
    main.run(today=date(2026, 10, 19))
    assert not [m for m in env["pushed"] if m.startswith("⏰")]


def test_heartbeat_once_per_week(env):
    main.run(today=TODAY)
    assert len([m for m in env["pushed"] if m.startswith("💓")]) == 1
    env["pushed"].clear()
    main.run(today=date(2026, 10, 10))
    assert not [m for m in env["pushed"] if m.startswith("💓")]


def test_pages_argument_fetches_more_urls(env, monkeypatch):
    urls = []
    monkeypatch.setattr(main.fetch, "get", lambda u, **kw: urls.append(u) or _rss(NOISE))
    main.run(pages=3, today=TODAY)
    assert len(urls) == 9 and "https://frequentmiler.com/feed/?paged=3" in urls


# ── 以下是審查主流程後補的 ──

def test_two_new_lows_same_program_keep_the_lowest(env):
    env["feeds"]["https://loyaltylobby.com/feed/"] = _rss(
        ("Buy IHG Points A", "https://x.test/1"), ("Buy IHG Points B", "https://x.test/2"))
    env["feeds"]["https://onemileatatime.com/feed/"] = _rss(NOISE)
    env["feeds"]["https://frequentmiler.com/feed/"] = _rss(NOISE)
    by_url = {"https://x.test/1": 120, "https://x.test/2": 110}   # 0.45、0.48
    env["extract"] = lambda a, t: _promo(percent=by_url[a.url], url=a.url)
    main.run(today=TODAY)
    assert '"best_cpp": 0.45' in (env["dir"] / "baselines.json").read_text(encoding="utf-8")


def test_different_reasons_on_same_feed_do_not_defeat_throttle(env):
    env["feeds"]["https://loyaltylobby.com/feed/"] = _rss(
        ("Buy IHG Points A", "https://x.test/1"), ("Buy IHG Points B", "https://x.test/2"))
    env["feeds"]["https://onemileatatime.com/feed/"] = _rss(NOISE)
    env["feeds"]["https://frequentmiler.com/feed/"] = _rss(NOISE)
    reasons = {"https://x.test/1": "Haiku 回應不含 JSON", "https://x.test/2": "end_date 早於今天"}

    def boom(a, t):
        raise extract.ExtractError(reasons[a.url])
    env["extract"] = boom
    main.run(today=TODAY)
    env["pushed"].clear()
    main.run(today=date(2026, 10, 10))
    main.run(today=date(2026, 10, 11))
    assert env["pushed"] == []


def test_no_reminder_in_same_run_as_first_push(env):
    env["extract"] = lambda a, t: _promo(end=date(2026, 10, 10))   # 首見時只剩 1 天
    main.run(today=TODAY)
    assert not [m for m in env["pushed"] if m.startswith("⏰")]
    env["pushed"].clear()
    main.run(today=date(2026, 10, 10))
    assert len([m for m in env["pushed"] if m.startswith("⏰")]) == 1


def test_no_heartbeat_on_a_run_with_failures(env):
    env["feeds"]["https://onemileatatime.com/feed/"] = requests.ConnectionError("x")
    main.run(today=TODAY)
    assert not [m for m in env["pushed"] if m.startswith("💓")]


def test_cli_exits_nonzero_on_extract_failure(env, monkeypatch):
    def boom(a, t):
        raise extract.ExtractError("Haiku 回應不含 JSON")
    env["extract"] = boom
    monkeypatch.setattr(sys, "argv", ["points_watch"])
    with pytest.raises(SystemExit) as e:
        main.main()
    assert e.value.code == 1


def test_up_to_new_low_notifies_but_keeps_baseline(env):
    env["extract"] = lambda a, t: Promo(
        program="IHG", kind="bonus", percent=110, stated_cpp=None,
        end_date=date(2026, 10, 31), up_to=True, url=a.url)
    main.run(today=TODAY)
    assert any("🏆 新低" in m for m in env["pushed"])
    assert (env["dir"] / "baselines.json").read_text(encoding="utf-8") == BASELINES
