"""國泰世華這條線的流程。網路與 Haiku 以假函式取代，狀態寫到 tmp_path。"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import cub, cub_run  # noqa: E402
from points_watch.cub_extract import Partner  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "points_watch"
LIST_TEXT = (FIXTURES / "cub_list.json").read_text(encoding="utf-8")
PAGE_TEXT = (FIXTURES / "cub_promo_page.json").read_text(encoding="utf-8")
TODAY = date(2026, 10, 9)
PROMO_PATH = ("/content/cub-aem-cs/zh-tw/cathaybk/personal/event/overview/"
              "credit-card/travel/202609/miles20251011.html")
PROMO_MODIFIED = "2026-09-18T08:58:04.436+00:00"

ASIA = Partner(name="亞洲萬里通", bonus="滿 2 萬里送 1,600", percent=8,
               start=date(2026, 10, 1), end=date(2026, 10, 31),
               registration="10/28 16:00–10/30 23:59，限量 2,000 名", cap="每正卡戶 1,600 里")
IHG = Partner(name="洲際優悅會", bonus="每次轉換加贈 50%", percent=50,
              start=date(2026, 10, 1), end=date(2026, 11, 30), registration=None, cap=None)
EVA = Partner(name="長榮航空", bonus="每次轉換加贈 15%", percent=15,
              start=date(2026, 10, 20), end=date(2026, 11, 30), registration=None, cap=None)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """預設：清單回實抓樣本；三個候選頁都回加碼頁的 JSON；
    Haiku 只對標題含「秋日遊」的那筆回兩個夥伴，其餘判否。"""
    box = {"pushed": [], "list": LIST_TEXT, "partners": [ASIA, IHG], "judged": [],
           "fetch_error": None, "extract_error": None, "dir": tmp_path}

    def fake_get(url, **kw):
        if url == cub.LIST_URL:
            if isinstance(box["list"], Exception):
                raise box["list"]
            return box["list"]
        if box["fetch_error"]:
            raise box["fetch_error"]
        return PAGE_TEXT

    def fake_extract(campaign, text, today):
        box["judged"].append(campaign.title)
        if box["extract_error"]:
            raise box["extract_error"]
        return list(box["partners"]) if "秋日遊" in campaign.title else None

    monkeypatch.setattr(cub_run.fetch, "get", fake_get)
    monkeypatch.setattr(cub_run.cub_extract, "extract", fake_extract)
    return box


def _run(env, today=TODAY, dry_run=False):
    return cub_run.run(env["dir"], today, dry_run, env["pushed"].append)


def _json(env, name):
    return json.loads((env["dir"] / name).read_text(encoding="utf-8"))


def test_new_campaign_pushed_once_and_recorded(env):
    failures, stats = _run(env)
    assert failures == []
    assert stats == {"listed": 149, "matched": 3}
    assert len(env["judged"]) == 3
    assert len(env["pushed"]) == 1
    msg = env["pushed"][0]
    assert msg.startswith("✈️ 國泰世華小樹點轉點加碼\n秋日遊-點數轉換指定航空里程/飯店積分限時加碼")
    assert "⭐ 亞洲萬里通｜8%（⚪ 低於 10%）" in msg and "・洲際優悅會｜50%" in msg
    assert "長榮：本次未參加" in msg
    promos = _json(env, "cub_promos.json")
    assert list(promos) == [PROMO_PATH]
    assert [p["name"] for p in promos[PROMO_PATH]["partners"]] == ["亞洲萬里通", "洲際優悅會"]
    assert len(_json(env, "cub_seen.json")["seen"]) == 3


def test_second_run_is_silent_and_does_not_rejudge(env):
    _run(env)
    env["pushed"].clear(), env["judged"].clear()
    failures, _ = _run(env, date(2026, 10, 10))
    assert (failures, env["pushed"], env["judged"]) == ([], [], [])


def test_page_edited_but_same_partners_is_rejudged_not_repushed(env):
    _run(env)
    env["pushed"].clear(), env["judged"].clear()
    env["list"] = LIST_TEXT.replace(PROMO_MODIFIED, "2026-10-10T01:00:00.000+00:00")
    assert PROMO_MODIFIED not in env["list"]
    _run(env, date(2026, 10, 10))
    assert env["judged"] == ["秋日遊-點數轉換指定航空里程/飯店積分限時加碼"]
    assert env["pushed"] == []


def test_partner_added_later_pushes_an_update_and_keeps_reminder_history(env):
    _run(env)
    promos = _json(env, "cub_promos.json")
    promos[PROMO_PATH]["reminded"] = ["2026-10-31"]
    (env["dir"] / "cub_promos.json").write_text(json.dumps(promos, ensure_ascii=False), encoding="utf-8")
    env["pushed"].clear()
    env["list"] = LIST_TEXT.replace(PROMO_MODIFIED, "2026-10-12T01:00:00.000+00:00")
    env["partners"] = [ASIA, IHG, EVA]
    _run(env, date(2026, 10, 12))
    assert len(env["pushed"]) == 1
    assert env["pushed"][0].startswith("✈️ 國泰世華小樹點轉點加碼（內容更新）")
    assert "⭐ 長榮航空｜15%（🟢 15% 以上）" in env["pushed"][0]
    after = _json(env, "cub_promos.json")[PROMO_PATH]
    assert len(after["partners"]) == 3
    assert after["reminded"] == ["2026-10-31"]
    assert after["first_seen"] == "2026-10-09"


def test_list_fetch_failure_is_reported_not_raised(env):
    env["list"] = requests.ConnectionError("x")
    failures, stats = _run(env)
    assert failures == [("國泰世華／清單", "連線失敗 ConnectionError")]
    assert stats == {"listed": 0, "matched": 0}
    assert env["pushed"][0].startswith("⚠️ 點數促銷監測異常")


def test_list_structure_change_is_reported(env):
    env["list"] = '{"campaigns": []}'
    failures, _ = _run(env)
    assert failures == [("國泰世華／清單", "活動清單為空或結構改變")]


def test_judge_failure_alerts_and_retries_next_day(env):
    env["extract_error"] = cub.CubError("加碼判讀：Haiku 回應不含 JSON")
    failures, _ = _run(env)
    assert set(failures) == {("國泰世華／判讀", "加碼判讀：Haiku 回應不含 JSON")}
    alerts_sent = [m for m in env["pushed"] if m.startswith("⚠️")]
    assert len(alerts_sent) == 1
    assert alerts_sent[0].count("國泰世華／判讀") == 1     # 三篇同原因只列一行
    # 沒有任何新判讀結果就不寫檔，避免每天產生一個內容不變的 commit
    assert not (env["dir"] / "cub_seen.json").exists()
    env["extract_error"] = None
    env["pushed"].clear(), env["judged"].clear()
    _run(env, date(2026, 10, 10))
    assert len(env["judged"]) == 3
    assert len([m for m in env["pushed"] if m.startswith("✈️")]) == 1


def test_page_fetch_failure_is_a_judge_failure(env):
    env["fetch_error"] = requests.Timeout("x")
    failures, _ = _run(env)
    assert set(failures) == {("國泰世華／判讀", "連線失敗 Timeout")}
    assert env["judged"] == []


def test_push_failure_leaves_state_untouched(env):
    def boom(text):
        raise requests.HTTPError("500")
    with pytest.raises(requests.HTTPError):
        cub_run.run(env["dir"], TODAY, False, boom)
    assert not (env["dir"] / "cub_promos.json").exists()
    assert not (env["dir"] / "cub_seen.json").exists()


def test_dry_run_prints_and_writes_nothing(env, capsys):
    failures, stats = _run(env, dry_run=True)
    assert (failures, stats) == ([], {"listed": 149, "matched": 3})
    assert env["pushed"] == []
    assert "⭐ 亞洲萬里通｜8%" in capsys.readouterr().out
    assert list(env["dir"].iterdir()) == []


def test_dry_run_ignores_seen(env, capsys):
    _run(env)
    env["judged"].clear()
    _run(env, dry_run=True)
    assert len(env["judged"]) == 3


def test_reminder_three_days_before_each_end_date_once(env):
    _run(env)                                   # 亞萬 10/31、IHG 11/30
    env["pushed"].clear()
    _run(env, date(2026, 10, 27))
    assert env["pushed"] == []
    _run(env, date(2026, 10, 28))
    assert len(env["pushed"]) == 1
    assert env["pushed"][0].startswith("⏰ 國泰世華轉點加碼即將截止\n10/31 截止（剩 3 天）")
    assert "亞洲萬里通" in env["pushed"][0] and "洲際優悅會" not in env["pushed"][0]
    env["pushed"].clear()
    _run(env, date(2026, 10, 29))
    assert env["pushed"] == []
    _run(env, date(2026, 11, 27))
    assert len(env["pushed"]) == 1 and "洲際優悅會" in env["pushed"][0]
    assert _json(env, "cub_promos.json")[PROMO_PATH]["reminded"] == ["2026-10-31", "2026-11-30"]


def test_no_reminder_in_the_run_that_first_announces(env):
    _run(env, date(2026, 10, 29))               # 首見時亞萬只剩 2 天
    assert [m[:1] for m in env["pushed"]] == ["✈"]
    env["pushed"].clear()
    _run(env, date(2026, 10, 30))
    assert len(env["pushed"]) == 1 and env["pushed"][0].startswith("⏰")
