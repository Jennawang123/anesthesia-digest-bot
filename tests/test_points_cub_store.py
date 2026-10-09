"""cub_promos.json 讀寫、夥伴內容比對、截止提醒判定。"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import cub_store  # noqa: E402

TODAY = date(2026, 10, 9)


def _p(name="亞洲萬里通", end="2026-10-31", bonus="滿 2 萬里送 1,600", **over):
    d = {"name": name, "program": None, "bonus": bonus, "percent": 8,
         "start": "2026-10-01", "end": end, "registration": None, "cap": None}
    d.update(over)
    return d


def _entry(partners, reminded=()):
    return {"title": "T", "url": "https://x.test/a", "partners": partners,
            "first_seen": "2026-10-09", "reminded": list(reminded)}


def test_roundtrip(tmp_path):
    path = tmp_path / "cub_promos.json"
    promos = {"/p.html": cub_store.entry("T", "https://x.test/a", [_p()], TODAY)}
    cub_store.save(path, promos)
    assert cub_store.load(path) == promos
    assert promos["/p.html"]["first_seen"] == "2026-10-09"
    assert promos["/p.html"]["reminded"] == []
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_load_missing(tmp_path):
    assert cub_store.load(tmp_path / "nope.json") == {}


def test_same_content_ignores_order_and_cosmetic_fields():
    a = [_p("亞洲萬里通"), _p("JAL", end="2026-11-30")]
    b = [_p("JAL", end="2026-11-30", cap="無"), _p("亞洲萬里通", registration="要登錄")]
    assert cub_store.same_content(a, b)


@pytest.mark.parametrize("change", [
    {"percent": 15}, {"end": "2026-11-15"}, {"start": "2026-10-05"}, {"name": "長榮航空"},
])
def test_content_differs(change):
    assert not cub_store.same_content([_p()], [_p(**change)])


def test_content_differs_when_partner_added():
    assert not cub_store.same_content([_p()], [_p(), _p("長榮航空")])


def test_same_content_tolerates_missing_dates():
    assert cub_store.same_content([_p(end=None)], [_p(end=None)])


@pytest.mark.parametrize("today, expect", [
    (date(2026, 10, 27), []),                 # 剩 4 天
    (date(2026, 10, 28), ["2026-10-31"]),     # 剩 3 天
    (date(2026, 10, 31), ["2026-10-31"]),     # 當天
    (date(2026, 11, 1), []),                  # 已過
])
def test_due_by_days_left(today, expect):
    groups = cub_store.due_groups(_entry([_p()]), today)
    assert [end.isoformat() for end, _ in groups] == expect


def test_partners_ending_same_day_are_grouped():
    e = _entry([_p("JAL", end="2026-11-30"), _p("洲際優悅會", end="2026-11-30"), _p()])
    groups = cub_store.due_groups(e, date(2026, 11, 28))
    assert len(groups) == 1
    assert [p["name"] for p in groups[0][1]] == ["JAL", "洲際優悅會"]


def test_two_end_dates_both_due_come_out_in_date_order():
    e = _entry([_p("藍天飛行", end="2026-11-01"), _p()])
    groups = cub_store.due_groups(e, date(2026, 10, 30))
    assert [end.isoformat() for end, _ in groups] == ["2026-10-31", "2026-11-01"]


def test_already_reminded_date_is_skipped():
    assert cub_store.due_groups(_entry([_p()], reminded=["2026-10-31"]), date(2026, 10, 29)) == []


def test_partner_without_end_date_never_reminds():
    assert cub_store.due_groups(_entry([_p(end=None)]), date(2026, 10, 29)) == []


def test_corrupt_entry_does_not_raise():
    # 這個檔 commit 進 public repo、可能被手改
    for bad in ("string", {}, {"partners": "x"}, {"partners": [{"end": "nope"}, "junk"]}):
        assert cub_store.due_groups(bad, TODAY) == []


def test_same_percent_with_different_wording_is_the_same_content():
    # 頁面被編輯後重新判讀，Haiku 對同一個 50% 的描述可能換一種說法
    a = [_p("洲際優悅會", bonus="每次轉換加贈 50%", percent=50)]
    b = [_p("洲際優悅會", bonus="加贈 50%", percent=50)]
    assert cub_store.same_content(a, b)


def test_without_percent_the_bonus_text_decides():
    a = [_p(bonus="加贈貴賓室券一張", percent=None)]
    assert cub_store.same_content(a, [_p(bonus="加贈貴賓室券一張", percent=None)])
    assert not cub_store.same_content(a, [_p(bonus="加贈貴賓室券兩張", percent=None)])
