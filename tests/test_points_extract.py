"""Haiku 抽取測試。只測 prompt 組裝與回應解析，不打 API。"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import extract  # noqa: E402
from points_watch.models import Article  # noqa: E402

TODAY = date(2026, 10, 9)
ARTICLE = Article(
    feed="frequentmiler",
    title="Buy IHG Points for as low as 0.5 cents each",
    url="https://frequentmiler.com/buy-ihg-points/",
    published=date(2026, 10, 8),
    summary="IHG has returned with another sale, offering a 100% bonus when buying points.",
)
GOOD = {"is_promo": True, "program": "IHG", "kind": "bonus", "percent": 100,
        "stated_cpp": 0.5, "end_date": "2026-10-31", "up_to": True}


def _parse(payload) -> object:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return extract.parse_response(raw, ARTICLE, TODAY)


def test_prompt_contains_article_and_dates():
    prompt = extract.build_prompt(ARTICLE, TODAY)
    assert ARTICLE.title in prompt and ARTICLE.summary in prompt
    assert "2026-10-09" in prompt and "2026-10-08" in prompt
    assert "FLYINGBLUE" in prompt          # 九個代號都要列給模型


def test_good_response():
    promo = _parse(GOOD)
    assert (promo.program, promo.kind, promo.percent, promo.stated_cpp, promo.up_to) == \
        ("IHG", "bonus", 100, 0.5, True)
    assert promo.end_date == date(2026, 10, 31)
    assert promo.url == ARTICLE.url


def test_json_wrapped_in_prose_or_fence():
    promo = _parse("好的，結果如下：\n```json\n" + json.dumps(GOOD) + "\n```")
    assert promo.program == "IHG"


def test_not_a_promo_returns_none():
    assert _parse({"is_promo": False}) is None


def test_nulls_allowed_for_cpp_and_end_date():
    promo = _parse({**GOOD, "stated_cpp": None, "end_date": None})
    assert promo.stated_cpp is None and promo.end_date is None


def test_end_date_today_is_ok():
    # last call 文章在截止當天發出，仍是有效促銷
    assert _parse({**GOOD, "end_date": "2026-10-09"}).end_date == TODAY


@pytest.mark.parametrize("bad", [
    "抱歉，我無法判斷。",                       # 沒有 JSON
    "{not json}",
    {"program": "IHG"},                          # 缺 is_promo
    {**GOOD, "program": "HILTON"},               # 不在追蹤清單
    {**GOOD, "kind": "cashback"},
    {**GOOD, "percent": 0},
    {**GOOD, "percent": 301},
    {**GOOD, "percent": "100%"},
    {**GOOD, "stated_cpp": 0.05},
    {**GOOD, "stated_cpp": 12},
    {**GOOD, "end_date": "October 31"},
    {**GOOD, "end_date": "2026-10-08"},          # 早於今天
    {**GOOD, "up_to": "yes"},
])
def test_bad_response_raises(bad):
    # 一律拋例外而非回 None：None 的語意是「模型判定不是促銷」，
    # 兩者混在一起的話，模型回垃圾會被當成「沒事」而永久漏報。
    with pytest.raises(extract.ExtractError):
        _parse(bad)


@pytest.mark.parametrize("returned, code", [
    ("ALASKA", "ALASKA"), ("alaska", "ALASKA"), ("Alaska Airlines", "ALASKA"),
    ("Alaska Atmos Rewards", "ALASKA"), ("Flying Blue", "FLYINGBLUE"),
    ("IHG One Rewards", "IHG"), ("Virgin Atlantic Flying Club", "VIRGIN"),
])
def test_program_name_normalised_to_code(returned, code):
    assert _parse({**GOOD, "program": returned}).program == code


@pytest.mark.parametrize("returned", ["Hilton Honors", "", None, 3, "IHG and Alaska"])
def test_program_must_match_exactly_one(returned):
    with pytest.raises(extract.ExtractError):
        _parse({**GOOD, "program": returned})


def test_prompt_includes_body():
    from dataclasses import replace
    with_body = replace(ARTICLE, body="Between October 2 and October 19, 2026")
    assert "Between October 2 and October 19, 2026" in extract.build_prompt(with_body, TODAY)
    assert "（無）" in extract.build_prompt(ARTICLE, TODAY)
