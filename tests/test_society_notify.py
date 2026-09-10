"""通知格式化測試。"""
import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch import notify  # noqa: E402
from society_watch.models import Event  # noqa: E402

TSA_EVENT = Event(
    source="TSA", uid="3105",
    title="2026年特管法輕中度鎮靜課程_1108高醫場",
    date_text="115/11/08",
    url="https://www.anesth.org.tw/events/content.asp?ID=3105&EduType=4",
    kind="鎮靜活動",
    place="高雄醫學大學臨床技能中心",
)
MINOR_EVENT = Event(
    source="TSCVA", uid="abc",
    title="2026 年度專科醫師甄審通過名單",
    date_text="2026-09-01",
    url="https://congress.tscva.org.tw/news/abc",
    minor=True,
)


def test_標題顯示則數():
    msg = notify.format_message([TSA_EVENT, MINOR_EVENT])
    assert msg.startswith("🔔 學會新活動 2 則")


def test_依學會分組並顯示日期與地點():
    msg = notify.format_message([TSA_EVENT])
    assert "【台灣麻醉醫學會】" in msg
    assert "115/11/08｜高雄醫學大學臨床技能中心" in msg
    assert "https://www.anesth.org.tw/events/content.asp?ID=3105&EduType=4" in msg


def test_minor項目排在其他公告區():
    msg = notify.format_message([MINOR_EVENT, TSA_EVENT])
    assert "── 其他公告 ──" in msg
    assert msg.index("鎮靜課程") < msg.index("── 其他公告 ──")
    assert msg.index("── 其他公告 ──") < msg.index("甄審通過名單")


def test_全部都是minor時仍有其他公告區():
    msg = notify.format_message([MINOR_EVENT])
    assert "── 其他公告 ──" in msg


def test_沒有minor時不出現其他公告區():
    assert "── 其他公告 ──" not in notify.format_message([TSA_EVENT])


def test_無地點時只顯示日期():
    e = Event(source="PAIN", uid="1", title="工作坊", date_text="2026 八月 23",
              url="https://pain.org.tw/x")
    assert "2026 八月 23\n" in notify.format_message([e])


def test_短訊息不拆分():
    assert notify.split_message("短訊息") == ["短訊息"]


def test_長訊息在學會邊界拆分():
    body = "\n\n".join(f"【學會{i}】\n" + "・活動\n" * 100 for i in range(6))
    parts = notify.split_message(body, max_chars=1000)
    assert len(parts) > 1
    assert all(len(p) <= 1000 for p in parts)
    # 六個學會區塊都完整保留，沒有被切掉
    # （不能斷言每段開頭都是「【」：最後一段開頭是「⬆️ 接上頁」標記）
    assert sum(p.count("【學會") for p in parts) == 6


def test_單一區塊超長時硬切():
    parts = notify.split_message("【學會】\n" + "字" * 3000, max_chars=1000)
    assert all(len(p) <= 1000 for p in parts)


def test_告警訊息列出失敗站別():
    msg = notify.format_alert([("TSA", "解析出 0 筆，疑似改版"), ("PAIN", "HTTP 500")])
    assert "TSA" in msg and "疑似改版" in msg
    assert "PAIN" in msg and "HTTP 500" in msg


def test_同一學會的多筆設定只出現一個區塊():
    # SOURCES 裡 RAPM 有兩筆（學會活動／友會活動），SOURCE_ORDER 靠
    # dict.fromkeys 去重。去重被拿掉的話每則 RAPM 會推兩次，
    # 而原本 10 個測試沒有一個用到 RAPM，抓不到
    events = [
        Event(source="RAPM", uid="32", title="疼痛擂台", date_text="2026-08-26",
              url="https://rapm.org.tw/news-detail/32", kind="學會活動"),
        Event(source="RAPM", uid="23", title="AOSRA 研討會", date_text="2026-04-16",
              url="https://rapm.org.tw/news-detail/23", kind="友會活動"),
    ]
    msg = notify.format_message(events)
    assert msg.count("【區域麻醉暨疼痛醫學會】") == 1
    assert "疼痛擂台" in msg and "AOSRA 研討會" in msg


def test_未知來源不會被靜默丟掉():
    # 新增第六個來源時忘了寫進 sources.py 的話，事件會抓得到、算得進則數、
    # 進得了 seen.json，就是不推播——而且狀態已前進，永遠不再推
    e = Event(source="NEWSOC", uid="1", title="某個新學會的工作坊",
              date_text="2026-10-01", url="https://example.org/1")
    msg = notify.format_message([e])
    assert "某個新學會的工作坊" in msg
    assert msg.startswith("🔔 學會新活動 1 則")


def test_字數以utf16計算():
    # LINE 算 UTF-16 code unit，非 BMP 的 emoji 算 2；Python len() 算 1 會低估
    assert notify._line_len("🔔" * 10) == 20
    assert notify._line_len("鎮靜活動") == 4


def test_滿版emoji訊息不會超過上限():
    # 用 len() 判斷的話這種訊息會被誤判為安全而送出，LINE 回 400
    body = "\n\n".join(f"【學會{i}】\n" + "🔔" * 300 for i in range(6))
    parts = notify.split_message(body, max_chars=1000)
    assert all(notify._line_len(p) <= 1000 for p in parts)


def test_硬切不會把emoji切成一半():
    parts = notify.split_message("【學會】\n" + "🔔" * 2000, max_chars=1000)
    for p in parts:
        p.encode("utf-8")          # 切壞的 surrogate 會在這裡炸掉
        assert "\ufffd" not in p


def test_max_chars過小時明確報錯():
    # budget <= 0 會讓硬切迴圈的長度不再遞減 → 卡死而非拋錯，
    # CI 要等到 timeout 才會發現
    with pytest.raises(ValueError):
        notify.split_message("【學會】\n" + "字" * 200, max_chars=40)
