"""promos.json 讀寫與截止提醒判定。"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import store  # noqa: E402
from points_watch.models import Promo, Rated  # noqa: E402

TODAY = date(2026, 10, 9)


def _rated(grade="green", end=date(2026, 10, 31), program="IHG"):
    promo = Promo(program=program, kind="bonus", percent=100, stated_cpp=0.5,
                  end_date=end, up_to=True, url="https://x.test/a")
    return Rated(promo=promo, cpp=0.5, best_cpp=0.5, grade=grade,
                 new_low=False, from_article=False)


def test_entry_roundtrip(tmp_path):
    path = tmp_path / "promos.json"
    r = _rated()
    store.save_promos(path, {r.promo.key: store.entry(r, TODAY)})
    assert store.load_promos(path) == {
        "IHG|bonus|100|2026-10-31": {
            "program": "IHG", "kind": "bonus", "percent": 100, "cpp": 0.5,
            "grade": "green", "end_date": "2026-10-31", "url": "https://x.test/a",
            "first_seen": "2026-10-09", "reminded": False,
        }
    }
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_load_missing_file(tmp_path):
    assert store.load_promos(tmp_path / "nope.json") == {}


def test_entry_without_end_date():
    assert store.entry(_rated(end=None), TODAY)["end_date"] is None


@pytest.mark.parametrize("end, due", [
    (date(2026, 10, 12), False),   # 剩 3 天
    (date(2026, 10, 11), True),    # 剩 2 天
    (date(2026, 10, 10), True),
    (date(2026, 10, 9), True),     # 今天截止
    (date(2026, 10, 8), False),    # 已過期
])
def test_due_by_days_left(end, due):
    r = _rated(end=end)
    promos = {r.promo.key: store.entry(r, date(2026, 10, 1))}
    assert bool(store.due_reminders(promos, TODAY)) is due


def test_only_green_gets_reminder():
    r = _rated(grade="yellow", end=date(2026, 10, 10))
    assert store.due_reminders({r.promo.key: store.entry(r, TODAY)}, TODAY) == []


def test_reminded_once_only():
    r = _rated(end=date(2026, 10, 10))
    e = store.entry(r, TODAY)
    e["reminded"] = True
    assert store.due_reminders({r.promo.key: e}, TODAY) == []


def test_no_end_date_no_reminder():
    r = _rated(end=None)
    assert store.due_reminders({r.promo.key: store.entry(r, TODAY)}, TODAY) == []


def test_corrupt_entry_is_skipped_not_fatal():
    # 這個檔 commit 進 public repo、可能被手改。壞一筆不該讓整個 run 死掉。
    promos = {"bad": {"grade": "green", "end_date": "not-a-date"}, "worse": "string"}
    assert store.due_reminders(promos, TODAY) == []


def _known(percent=120, end=date(2026, 10, 19), first=TODAY, program="ALASKA"):
    r = _rated(end=end, program=program)
    e = store.entry(r, first)
    e["percent"] = percent
    return {"k": e}


def _new(percent=100, end=None, program="ALASKA", kind="bonus"):
    return Promo(program=program, kind=kind, percent=percent, stated_cpp=None,
                 end_date=end, up_to=True, url="https://x.test/b")


def test_covered_same_sale_reported_lower_and_undated():
    # 實例：Loyalty Lobby 先報 120%／10-19，OMAAT 再報 100%／無截止日
    assert store.covered(_known(), _new(), TODAY)


def test_higher_percent_is_not_covered():
    assert not store.covered(_known(percent=100), _new(percent=120), TODAY)


def test_ended_sale_does_not_cover_the_next_one():
    assert not store.covered(_known(end=date(2026, 10, 8)), _new(), TODAY)


def test_undated_record_covers_for_three_weeks_only():
    known = _known(end=None, first=date(2026, 9, 18))        # 21 天前
    assert store.covered(known, _new(), TODAY)
    assert not store.covered(_known(end=None, first=date(2026, 9, 17)), _new(), TODAY)


def test_other_program_or_kind_not_covered():
    assert not store.covered(_known(program="IHG"), _new(), TODAY)
    assert not store.covered(_known(), _new(kind="discount"), TODAY)


def test_covered_ignores_corrupt_entries():
    junk = {"a": "x", "b": {"program": "ALASKA", "kind": "bonus", "percent": "120"},
            "c": {"program": "ALASKA", "kind": "bonus", "percent": 120, "end_date": "nope"}}
    assert not store.covered(junk, _new(), TODAY)
