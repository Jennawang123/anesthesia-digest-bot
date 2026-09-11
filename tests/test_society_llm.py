"""文字來源的 LLM 抽取測試。只測 prompt 組裝與回應解析，不打 API。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from society_watch import llm  # noqa: E402

AIRWAY_URL = "https://www.tsamairway.org.tw/最新資訊"
TWECCM_URL = "https://www.tweccm.org.tw/"


def _parse(raw: str):
    return llm.parse_response(raw, "AIRWAY", AIRWAY_URL)


def test_prompt_含全部新增行():
    prompt = llm.build_prompt(
        ["📣 北區麻醉月會", "📅 時間：115年2月7日"], "台灣呼吸道處理醫學會"
    )
    assert "📣 北區麻醉月會" in prompt
    assert "📅 時間：115年2月7日" in prompt


def test_prompt_帶入呼叫端給的學會名():
    # prompt 若還寫死呼吸道學會，TWECCM 首頁的內容會被貼上錯誤的來源脈絡
    prompt = llm.build_prompt(["重要訊息"], "急重症聯合年會（SECC）")
    assert "急重症聯合年會（SECC）" in prompt
    assert "台灣呼吸道處理醫學會" not in prompt


def test_解析回應為Event():
    raw = '[{"title": "115年2月份北區麻醉月會", "date_text": "115年2月7日", "is_event": true}]'
    events = _parse(raw)
    assert len(events) == 1
    e = events[0]
    assert e.source == "AIRWAY"
    assert e.title == "115年2月份北區麻醉月會"
    assert e.date_text == "115年2月7日"
    assert e.url == "https://www.tsamairway.org.tw/最新資訊"
    assert e.minor is False


def test_uid為標題hash且穩定():
    raw = '[{"title": "北區麻醉月會", "date_text": "", "is_event": true}]'
    a = _parse(raw)[0]
    b = _parse(raw)[0]
    assert a.uid == b.uid
    assert len(a.uid) == 12


def test_非活動者標為minor():
    raw = '[{"title": "賀呂忠和主任榮任理事長", "date_text": "", "is_event": false}]'
    assert _parse(raw)[0].minor is True


def test_回應含程式碼圍籬也能解析():
    raw = '```json\n[{"title": "工作坊", "date_text": "", "is_event": true}]\n```'
    assert len(_parse(raw)) == 1


def test_回應無法解析時回空list():
    # parse_response 維持既有契約：解析不出來回空 list，不拋例外
    assert _parse("模型今天話很多但沒給 JSON") == []


def test_checked_版本能分辨垃圾與合法空陣列():
    # 兩者都產出空清單，只有 ok 這個旗標分得出來——
    # 丟掉它就等於讓「模型回垃圾」偽裝成「今天沒有活動」
    assert llm.parse_response_checked("[]", "AIRWAY", AIRWAY_URL) == ([], True)
    assert llm.parse_response_checked(
        "模型今天話很多但沒給 JSON", "AIRWAY", AIRWAY_URL
    ) == ([], False)


def test_陣列後面接散文也能解析():
    raw = '[{"title": "工作坊", "date_text": "", "is_event": true}] 以上是我找到的[全部]內容'
    events, ok = llm.parse_response_checked(raw, "AIRWAY", AIRWAY_URL)
    assert ok is True
    assert len(events) == 1


def test_元素不是物件時跳過而不拋例外():
    events, ok = llm.parse_response_checked(
        '["工作坊A", {"title": "工作坊B", "is_event": true}]', "AIRWAY", AIRWAY_URL
    )
    assert ok is True
    assert [e.title for e in events] == ["工作坊B"]


def test_新增行數超過上限時拋例外():
    # 整頁改版時不送一大包進去燒錢，改成拋例外讓 collect 記成失敗並告警
    with pytest.raises(llm.LLMResponseError, match="疑似整頁改版"):
        llm.classify(
            [f"第 {i} 行" for i in range(llm.MAX_NEW_LINES + 1)],
            "AIRWAY", "台灣呼吸道處理醫學會", AIRWAY_URL,
        )


def test_沒有新增行時不建立client也不呼叫api():
    # CLAUDE_API_KEY 不存在時仍須正常回空 list
    assert llm.classify([], "AIRWAY", "台灣呼吸道處理醫學會", AIRWAY_URL) == []


def test_事件的來源與網址取自呼叫端而非寫死():
    # 這條是一般化之後最容易靜默壞掉的地方：source 寫死成 AIRWAY 的話，
    # TWECCM 首頁的事件會跟 AIRWAY 共用 seen.json 的命名空間、
    # 在通知裡被分到呼吸道學會底下，而且每一項看起來都正常
    raw = '[{"title": "口頭論文發表及海報論文展示通知", "date_text": "", "is_event": true}]'
    e = llm.parse_response(raw, "TWECCM", TWECCM_URL)[0]
    assert e.source == "TWECCM"
    assert e.url == TWECCM_URL
    assert e.key.startswith("TWECCM:")


def test_相同標題在不同來源下去重鍵不相同():
    # uid 是標題 hash、不含 source。兩站若剛好有同名活動，
    # 去重鍵必須靠 Event.key 的 source 前綴分開，否則其中一站會被靜默吃掉
    raw = '[{"title": "急重症工作坊", "date_text": "", "is_event": true}]'
    a = llm.parse_response(raw, "AIRWAY", AIRWAY_URL)[0]
    b = llm.parse_response(raw, "TWECCM", TWECCM_URL)[0]
    assert a.uid == b.uid
    assert a.key != b.key
