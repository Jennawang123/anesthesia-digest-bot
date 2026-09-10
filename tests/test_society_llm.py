"""Airway LLM 抽取測試。只測 prompt 組裝與回應解析，不打 API。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch import llm  # noqa: E402


def test_prompt_含全部新增行():
    prompt = llm.build_prompt(["📣 北區麻醉月會", "📅 時間：115年2月7日"])
    assert "📣 北區麻醉月會" in prompt
    assert "📅 時間：115年2月7日" in prompt


def test_解析回應為Event():
    raw = '[{"title": "115年2月份北區麻醉月會", "date_text": "115年2月7日", "is_event": true}]'
    events = llm.parse_response(raw)
    assert len(events) == 1
    e = events[0]
    assert e.source == "AIRWAY"
    assert e.title == "115年2月份北區麻醉月會"
    assert e.date_text == "115年2月7日"
    assert e.url == "https://www.tsamairway.org.tw/最新資訊"
    assert e.minor is False


def test_uid為標題hash且穩定():
    raw = '[{"title": "北區麻醉月會", "date_text": "", "is_event": true}]'
    a = llm.parse_response(raw)[0]
    b = llm.parse_response(raw)[0]
    assert a.uid == b.uid
    assert len(a.uid) == 12


def test_非活動者標為minor():
    raw = '[{"title": "賀呂忠和主任榮任理事長", "date_text": "", "is_event": false}]'
    assert llm.parse_response(raw)[0].minor is True


def test_回應含程式碼圍籬也能解析():
    raw = '```json\n[{"title": "工作坊", "date_text": "", "is_event": true}]\n```'
    assert len(llm.parse_response(raw)) == 1


def test_回應無法解析時回空list():
    # 寧可漏這一輪也不要讓整支程式炸掉；Task 13 會另外送告警
    assert llm.parse_response("模型今天話很多但沒給 JSON") == []
