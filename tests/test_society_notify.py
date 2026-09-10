"""通知格式化測試。"""
import sys
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
