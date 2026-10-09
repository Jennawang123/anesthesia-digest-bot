"""評等測試：公式、三個等級的邊界、文章報價覆寫、新低、基準檔改寫。"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import rating  # noqa: E402
from points_watch.models import Promo  # noqa: E402

IHG = {"base_cpp": 1.00, "best_cpp": 0.50}


def _promo(kind="bonus", percent=100, stated_cpp=None, program="IHG"):
    return Promo(program=program, kind=kind, percent=percent, stated_cpp=stated_cpp,
                 end_date=date(2026, 10, 31), up_to=False, url="https://x.test/a")


def test_bonus_formula():
    assert rating.rate(_promo(percent=100), IHG).cpp == 0.50
    assert rating.rate(_promo(percent=80), IHG).cpp == 0.56     # 1/1.8=0.5556


def test_discount_formula():
    choice = {"base_cpp": 1.03, "best_cpp": 0.57}
    assert rating.rate(_promo(kind="discount", percent=45), choice).cpp == 0.57
    assert rating.rate(_promo(kind="discount", percent=40), choice).cpp == 0.62


@pytest.mark.parametrize("percent, grade", [
    (100, "green"),    # 0.50，平最佳
    (95, "green"),     # 0.51，在 3% 內（0.515）
    (90, "yellow"),    # 0.53
    (75, "yellow"),    # 0.57，在 15% 內（0.575）
    (70, "red"),       # 0.59
    (50, "red"),       # 0.67
])
def test_grade_boundaries(percent, grade):
    assert rating.rate(_promo(percent=percent), IHG).grade == grade


def test_stated_cpp_overrides_when_far_from_formula():
    # 公式算 0.50，文章寫 0.60（原價調漲或非單純加贈）→ 採文章報價
    r = rating.rate(_promo(percent=100, stated_cpp=0.60), IHG)
    assert (r.cpp, r.from_article, r.grade) == (0.60, True, "red")


def test_stated_cpp_ignored_when_close():
    r = rating.rate(_promo(percent=100, stated_cpp=0.51), IHG)
    assert (r.cpp, r.from_article) == (0.50, False)


def test_new_low():
    r = rating.rate(_promo(percent=110), IHG)     # 1/2.1=0.476 → 0.48
    assert (r.cpp, r.new_low, r.grade, r.best_cpp) == (0.48, True, "green", 0.50)


def test_equal_to_best_is_not_new_low():
    assert rating.rate(_promo(percent=100), IHG).new_low is False


def test_suspiciously_low_price_raises():
    # 比歷史最佳便宜三成以上，幾乎必是抽錯（把點數量當百分比之類）。
    # 放行的話會被標 🏆 並把基準永久改壞，之後真正的好價全變 🔴。
    with pytest.raises(rating.SuspiciousPrice):
        rating.rate(_promo(percent=250), IHG)      # 0.29 < 0.35


BASELINES_TEXT = (
    '{\n'
    '  "IHG":        {"base_cpp": 1.00, "best_cpp": 0.50},\n'
    '  "CHOICE":     {"base_cpp": 1.03, "best_cpp": 0.57}\n'
    '}\n'
)


def test_update_best_changes_only_one_number():
    out = rating.update_best(BASELINES_TEXT, "IHG", 0.48)
    assert out == BASELINES_TEXT.replace('"best_cpp": 0.50', '"best_cpp": 0.48')


def test_update_best_targets_the_right_program():
    out = rating.update_best(BASELINES_TEXT, "CHOICE", 0.5)
    assert '"IHG":        {"base_cpp": 1.00, "best_cpp": 0.50}' in out
    assert '"CHOICE":     {"base_cpp": 1.03, "best_cpp": 0.50}' in out


def test_update_best_unknown_program_raises():
    with pytest.raises(KeyError):
        rating.update_best(BASELINES_TEXT, "NOPE", 0.4)


def test_load_baselines(tmp_path):
    p = tmp_path / "baselines.json"
    p.write_text(BASELINES_TEXT, encoding="utf-8")
    assert rating.load_baselines(p)["CHOICE"] == {"base_cpp": 1.03, "best_cpp": 0.57}
