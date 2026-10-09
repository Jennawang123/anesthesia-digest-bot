"""國泰世華加碼的 Haiku 抽取。只測 prompt 組裝與回應解析，不打 API。"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import cub_extract  # noqa: E402
from points_watch.cub import Campaign, CubError  # noqa: E402

TODAY = date(2026, 10, 9)
CAMPAIGN = Campaign(path="/p.html", url="https://x.test/p", title="秋日遊轉點加碼",
                    blurb="最高加碼50%", modified="m1")
ASIA = {"name": "亞洲萬里通", "bonus": "滿 1 萬里送 800、滿 2 萬里送 1,600", "percent": 8,
        "start": "2026-10-01", "end": "2026-10-31",
        "registration": "10/28 16:00–10/30 23:59，限量 2,000 名", "cap": "每正卡戶 1,600 里"}
JAL = {"name": "JAL哩程儲蓄專案", "bonus": "每次轉換加贈 30%", "percent": 30,
       "start": "2026-10-01", "end": "2026-11-30", "registration": None, "cap": None}


def _parse(payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return cub_extract.parse_response(raw)


def _ok(*partners):
    return {"is_transfer_bonus": True, "partners": list(partners)}


def test_prompt_contains_title_text_and_today():
    prompt = cub_extract.build_prompt(CAMPAIGN, "活動內文在這裡", TODAY)
    assert "秋日遊轉點加碼" in prompt and "活動內文在這裡" in prompt and "2026-10-09" in prompt


def test_prompt_truncates_long_text():
    # 用一個 prompt 範本裡不會出現的字來數
    prompt = cub_extract.build_prompt(CAMPAIGN, "龘" * 20000, TODAY)
    assert prompt.count("龘") == cub_extract.TEXT_MAX


def test_not_a_transfer_bonus():
    assert _parse({"is_transfer_bonus": False}) is None


def test_two_partners():
    asia, jal = _parse(_ok(ASIA, JAL))
    assert (asia.name, asia.program, asia.percent) == ("亞洲萬里通", "ASIAMILES", 8)
    assert (asia.start, asia.end) == (date(2026, 10, 1), date(2026, 10, 31))
    assert asia.registration == "10/28 16:00–10/30 23:59，限量 2,000 名"
    assert asia.cap == "每正卡戶 1,600 里"
    assert (jal.program, jal.registration, jal.cap) == (None, None, None)


@pytest.mark.parametrize("name, program", [
    ("長榮航空", "EVA"), ("長榮航空 無限萬哩遊", "EVA"), ("EVA Air", "EVA"),
    ("亞洲萬里通", "ASIAMILES"), ("Asia Miles", "ASIAMILES"),
    ("洲際優悅會", None), ("法航荷航藍天飛行", None), ("PREVAIL Hotels", None),
])
def test_program_is_derived_from_name(name, program):
    assert _parse(_ok({**JAL, "name": name}))[0].program == program


def test_json_wrapped_in_fence():
    assert _parse("```json\n" + json.dumps(_ok(JAL), ensure_ascii=False) + "\n```")[0].name == "JAL哩程儲蓄專案"


def test_already_ended_partner_is_fine():
    # 活動進行到一半才被看到，個別夥伴已截止是正常的
    assert _parse(_ok({**JAL, "end": "2026-10-05"}))[0].end == date(2026, 10, 5)


def test_nulls_and_empty_strings_for_optional_fields():
    p = _parse(_ok({**JAL, "percent": None, "start": None, "end": None,
                    "registration": "", "cap": "  "}))[0]
    assert (p.percent, p.start, p.end, p.registration, p.cap) == (None, None, None, None, None)


@pytest.mark.parametrize("bad", [
    "抱歉，我無法判斷。",
    "{oops}",
    {"partners": [JAL]},                          # 缺 is_transfer_bonus
    {"is_transfer_bonus": True},                  # 缺 partners
    {"is_transfer_bonus": True, "partners": []},
    {"is_transfer_bonus": True, "partners": ["JAL"]},
    _ok({**JAL, "name": ""}),
    _ok({**JAL, "name": None}),
    _ok({**JAL, "bonus": " "}),
    _ok({**JAL, "percent": 0}),
    _ok({**JAL, "percent": 301}),
    _ok({**JAL, "percent": "30%"}),
    _ok({**JAL, "percent": True}),
    _ok({**JAL, "percent": 12.5}),
    _ok({**JAL, "end": "11/30"}),
    _ok({**JAL, "start": "2026-12-01", "end": "2026-11-30"}),
    _ok({**JAL, "registration": 5}),
])
def test_bad_response_raises(bad):
    # None 的語意是「模型判定不是加碼活動」。回應壞掉必須拋例外，
    # 兩者混在一起的話模型回垃圾會被當成「沒事」而整年漏報。
    with pytest.raises(CubError):
        _parse(bad)


def test_clock_times_are_kept():
    p = _parse(_ok({**JAL, "name": "法航荷航藍天飛行", "start_time": "07:00",
                    "end": "2026-11-01", "end_time": "07:59"}))[0]
    assert (p.start_time, p.end_time) == ("07:00", "07:59")
    assert p.as_dict()["end_time"] == "07:59"


def test_clock_times_default_to_none():
    p = _parse(_ok({**JAL, "start_time": "", "end_time": None}))[0]
    assert (p.start_time, p.end_time) == (None, None)
    assert _parse(_ok(JAL))[0].as_dict()["start_time"] is None


@pytest.mark.parametrize("bad", ["7:59", "24:00", "07:60", "上午七點", 759])
def test_bad_clock_time_raises(bad):
    with pytest.raises(CubError):
        _parse(_ok({**JAL, "end_time": bad}))
