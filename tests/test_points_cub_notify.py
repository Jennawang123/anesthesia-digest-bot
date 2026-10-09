"""✈️ 活動訊息與 ⏰ 提醒訊息的排版。"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import cub_notify  # noqa: E402

TITLE = "秋日遊-點數轉換指定航空里程/飯店積分限時加碼"
URL = "https://www.cathay-cube.com.tw/cathaybk/personal/event/overview/credit-card/travel/202609/miles20251011"


def _p(name, percent, bonus, start="2026-10-01", end="2026-11-30", program=None,
       registration=None, cap=None):
    return {"name": name, "program": program, "bonus": bonus, "percent": percent,
            "start": start, "end": end, "registration": registration, "cap": cap}


ASIA = _p("亞洲萬里通", 8, "滿 1 萬里送 800、滿 2 萬里送 1,600", end="2026-10-31",
          program="ASIAMILES", registration="10/28 16:00–10/30 23:59，限量 2,000 名",
          cap="每正卡戶 1,600 里")
JAL = _p("JAL哩程儲蓄專案", 30, "每次轉換加贈 30%")
IHG = _p("洲際優悅會", 50, "每次轉換加贈 50%")
FB = _p("法航荷航藍天飛行", 20, "每次轉換加贈 20%", end="2026-11-01")


def test_full_campaign_message():
    # 傳入順序刻意打亂：排版要自己把亞萬排最前、其餘依幅度由高到低
    assert cub_notify.format_campaign(TITLE, URL, [JAL, FB, ASIA, IHG]) == "\n".join([
        "✈️ 國泰世華小樹點轉點加碼",
        TITLE,
        "",
        "⭐ 亞洲萬里通｜8%（⚪ 低於 10%）",
        "  滿 1 萬里送 800、滿 2 萬里送 1,600",
        "  10/1–10/31",
        "  需登錄：10/28 16:00–10/30 23:59，限量 2,000 名",
        "  上限：每正卡戶 1,600 里",
        "・洲際優悅會｜50%",
        "  10/1–11/30",
        "・JAL哩程儲蓄專案｜30%",
        "  10/1–11/30",
        "・法航荷航藍天飛行｜20%",
        "  10/1–11/1",
        "",
        "長榮：本次未參加",
        URL,
    ])


def test_updated_header():
    text = cub_notify.format_campaign(TITLE, URL, [IHG], updated=True)
    assert text.splitlines()[0] == "✈️ 國泰世華小樹點轉點加碼（內容更新）"


@pytest.mark.parametrize("percent, lamp", [
    (15, "🟢 15% 以上"), (20, "🟢 15% 以上"),
    (10, "🟡 10–14%"), (14, "🟡 10–14%"),
    (9, "⚪ 低於 10%"),
])
def test_lamp_for_starred(percent, lamp):
    eva = _p("長榮航空 無限萬哩遊", percent, f"每次轉換加贈 {percent}%", program="EVA")
    assert f"⭐ 長榮航空 無限萬哩遊｜{percent}%（{lamp}）" in cub_notify.format_campaign(TITLE, URL, [eva])


def test_starred_without_percent_has_no_lamp_and_shows_bonus():
    eva = _p("長榮航空", None, "加贈貴賓室券一張", program="EVA")
    lines = cub_notify.format_campaign(TITLE, URL, [eva]).splitlines()
    assert "⭐ 長榮航空" in lines
    assert "  加贈貴賓室券一張" in lines


def test_eva_sorted_before_asia_miles_and_no_footer_when_both_present():
    eva = _p("長榮航空", 15, "每次轉換加贈 15%", program="EVA")
    text = cub_notify.format_campaign(TITLE, URL, [IHG, ASIA, eva])
    assert text.index("⭐ 長榮航空") < text.index("⭐ 亞洲萬里通") < text.index("・洲際優悅會")
    assert "本次未參加" not in text


def test_footer_when_neither_present():
    assert "長榮、亞洲萬里通：本次未參加" in cub_notify.format_campaign(TITLE, URL, [IHG])


def test_footer_when_only_eva_present():
    eva = _p("長榮航空", 15, "每次轉換加贈 15%", program="EVA")
    assert "亞洲萬里通：本次未參加" in cub_notify.format_campaign(TITLE, URL, [eva])


def test_others_without_percent_go_last_and_show_bonus():
    odd = _p("某飯店", None, "滿額贈早餐券")
    lines = cub_notify.format_campaign(TITLE, URL, [odd, JAL]).splitlines()
    assert lines.index("・JAL哩程儲蓄專案｜30%") < lines.index("・某飯店")
    assert "  滿額贈早餐券" in lines


@pytest.mark.parametrize("start, end, shown", [
    ("2026-10-01", "2026-11-30", "  10/1–11/30"),
    (None, "2026-11-30", "  至 11/30"),
    ("2026-10-01", None, "  10/1 起"),
    (None, None, "  期間未註明"),
    ("garbage", "2026-11-30", "  至 11/30"),
])
def test_period_line(start, end, shown):
    p = _p("JAL", 30, "每次轉換加贈 30%", start=start, end=end)
    assert shown in cub_notify.format_campaign(TITLE, URL, [p]).splitlines()


def test_reminder():
    text = cub_notify.format_reminder(TITLE, URL, date(2026, 10, 31), [ASIA], date(2026, 10, 28))
    assert text == "\n".join([
        "⏰ 國泰世華轉點加碼即將截止",
        "10/31 截止（剩 3 天）",
        "",
        "⭐ 亞洲萬里通｜8%",
        "  滿 1 萬里送 800、滿 2 萬里送 1,600",
        "  需登錄：10/28 16:00–10/30 23:59，限量 2,000 名",
        "",
        URL,
    ])


def test_reminder_last_day_and_plain_partners():
    text = cub_notify.format_reminder(TITLE, URL, date(2026, 11, 30), [JAL, IHG], date(2026, 11, 30))
    assert "11/30 截止（今天截止）" in text
    assert "・洲際優悅會｜50%" in text and "・JAL哩程儲蓄專案｜30%" in text
    assert "需登錄" not in text
