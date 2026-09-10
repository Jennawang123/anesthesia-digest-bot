"""Airway LLM 抽取測試。只測 prompt 組裝與回應解析，不打 API。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

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
    # parse_response 維持既有契約：解析不出來回空 list，不拋例外
    assert llm.parse_response("模型今天話很多但沒給 JSON") == []


def test_checked_版本能分辨垃圾與合法空陣列():
    # 兩者都產出空清單，只有 ok 這個旗標分得出來——
    # 丟掉它就等於讓「模型回垃圾」偽裝成「今天沒有活動」
    assert llm.parse_response_checked("[]") == ([], True)
    assert llm.parse_response_checked("模型今天話很多但沒給 JSON") == ([], False)


def test_陣列後面接散文也能解析():
    raw = '[{"title": "工作坊", "date_text": "", "is_event": true}] 以上是我找到的[全部]內容'
    events, ok = llm.parse_response_checked(raw)
    assert ok is True
    assert len(events) == 1


def test_元素不是物件時跳過而不拋例外():
    events, ok = llm.parse_response_checked('["工作坊A", {"title": "工作坊B", "is_event": true}]')
    assert ok is True
    assert [e.title for e in events] == ["工作坊B"]


def test_新增行數超過上限時拋例外():
    # 整頁改版時不送一大包進去燒錢，改成拋例外讓 collect 記成失敗並告警
    with pytest.raises(llm.LLMResponseError, match="疑似整頁改版"):
        llm.classify([f"第 {i} 行" for i in range(llm.MAX_NEW_LINES + 1)])


def test_沒有新增行時不建立client也不呼叫api():
    # CLAUDE_API_KEY 不存在時仍須正常回空 list
    assert llm.classify([]) == []
