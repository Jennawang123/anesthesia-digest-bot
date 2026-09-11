"""主流程測試。以假的抓取函式取代網路。"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch import main  # noqa: E402
from society_watch.models import Event  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "society_watch"

EMPTY_TABLE = "<table class='table'><tbody></tbody></table>"


pain_urls_seen: list[str] = []


def _fake_fetch(mapping, failures=None):
    failures = failures or {}
    pain_urls_seen.clear()

    def _get(url, **kwargs):
        for key, exc in failures.items():
            if key in url:
                raise exc
        # PAIN 會被抓三次（去年／今年／明年）。這裡刻意嚴格：沒帶 yy 就炸，
        # 否則日後若有人把 collect() 改成統一讀 cfg["url"]，PAIN 會靜默
        # 退回只抓當年、跨年防護消失，而測試筆數仍然分毫不差地通過。
        if "educlass_page1_content" in url:
            if "yy=" not in url:
                raise AssertionError(f"PAIN 的抓取 URL 必須帶 yy=：{url}")
            pain_urls_seen.append(url)
            if "yy=2026" not in url:
                return EMPTY_TABLE
        for key, name in mapping.items():
            if key in url:
                return (FIXTURES / name).read_text(encoding="utf-8")
        return "<html></html>"

    return _get


ALL_OK = {
    "anesth.org.tw": "tsa_events_20260910.html",
    "congress.tscva.org.tw": "tscva_news_20260910.html",
    "news-list/2": "rapm_newslist2_20260910.html",
    "news-list/5": "rapm_newslist5_20260910.html",
    "educlass_page1_content": "pain_fragment_20260910.html",
}

# TSA 15 + TSCVA 6 + RAPM 16 + RAPM 11 + PAIN 10（今年）+ 0（明年空表）
TOTAL_EVENTS = 58


@pytest.fixture
def env(tmp_path, monkeypatch):
    """把狀態檔導到 tmp、攔截推播、AIRWAY 預設成功但無新增。"""
    pushed = []
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main.fetch, "get", _fake_fetch(ALL_OK))
    monkeypatch.setattr(main, "collect_airway", lambda: ([], ["A", "B"], None))
    monkeypatch.setattr(main.notify, "push_line", lambda text: pushed.append(text))
    return tmp_path, pushed, monkeypatch


def test_收集五站事件(env):
    events, failures, airway_lines = main.collect(date(2026, 9, 10))
    assert failures == []
    assert len(events) == TOTAL_EVENTS
    assert airway_lines == ["A", "B"]


def test_pain三個年份都有被抓(env):
    main.collect(date(2026, 9, 10))
    assert sorted(u.rsplit("=", 1)[1] for u in pain_urls_seen) == ["2025", "2026", "2027"]


def test_rapm兩個分類的告警key互不相干(env, monkeypatch):
    import requests
    monkeypatch.setattr(
        main.fetch, "get",
        _fake_fetch(ALL_OK, failures={"news-list/5": requests.ConnectionError("斷線")}),
    )
    _, failures, _ = main.collect(date(2026, 9, 10))
    # key 要帶 kind，否則友會活動的失敗會吃掉學會活動的 7 天告警冷卻期
    assert [f[0] for f in failures] == ["RAPM／友會活動"]


def test_單站失敗不中斷其他站(env, monkeypatch):
    import requests
    monkeypatch.setattr(
        main.fetch, "get",
        _fake_fetch(ALL_OK, failures={"congress.tscva.org.tw": requests.ConnectionError("斷線")}),
    )
    events, failures, _ = main.collect(date(2026, 9, 10))
    assert [f[0] for f in failures] == ["TSCVA"]
    assert any(e.source == "TSA" for e in events)
    assert not any(e.source == "TSCVA" for e in events)
    # 也要斷言「排在失敗站之後」的站有跑到，否則 continue 改成 break 也會全過
    assert any(e.source == "PAIN" for e in events)


def test_解析出零筆視為疑似改版(env, monkeypatch):
    # 拿掉 TSA 的對應，讓它抓到一個 HTTP 200 但沒有活動的空頁
    without_tsa = {k: v for k, v in ALL_OK.items() if "anesth" not in k}
    monkeypatch.setattr(main.fetch, "get", _fake_fetch(without_tsa))
    events, failures, _ = main.collect(date(2026, 9, 10))
    assert ("TSA", "解析出 0 筆，疑似改版") in failures
    assert any(e.source == "RAPM" for e in events)   # 其他站不受影響


def test_airway失敗時不回傳快照行(env, monkeypatch):
    monkeypatch.setattr(main, "collect_airway", lambda: ([], ["半截"], "行數暴跌"))
    _, failures, airway_lines = main.collect(date(2026, 9, 10))
    assert ("AIRWAY", "行數暴跌") in failures
    assert airway_lines is None


def test_airway首次執行不送llm只建快照(tmp_path, monkeypatch):
    # 其餘測試都把 collect_airway 整個換掉，這裡是唯一真的跑它本體的地方
    html = (FIXTURES / "airway_page_20260910.html").read_text(encoding="utf-8")
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main.fetch, "get", lambda url, **kwargs: html)
    called = []
    monkeypatch.setattr(main.llm, "classify", lambda lines: called.append(lines) or [])

    events, lines, error = main.collect_airway()
    assert (events, error) == ([], None)
    assert len(lines) > 50
    # 沒有舊快照時整頁都算「新增」，照送 Haiku 會直接撞上 MAX_NEW_LINES
    assert called == []


def test_airway行數暴跌時回報疑似改版且不送llm(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    main.state.save_snapshot(
        tmp_path / "airway_snapshot.txt", [f"第 {i} 行" for i in range(100)]
    )
    monkeypatch.setattr(
        main.fetch, "get", lambda url, **kwargs: "<html><body>只剩這一行</body></html>"
    )
    called = []
    monkeypatch.setattr(main.llm, "classify", lambda lines: called.append(lines) or [])

    events, lines, error = main.collect_airway()
    assert events == []
    assert error is not None and "暴跌" in error
    assert called == []


def test_airway拋例外時記成失敗且不推進快照(env, monkeypatch):
    # llm.classify 回垃圾時會拋 LLMResponseError，必須變成告警而不是「今天沒活動」
    def boom():
        raise main.llm.LLMResponseError("Haiku 回應無法解析為 JSON 陣列")

    monkeypatch.setattr(main, "collect_airway", boom)
    _, failures, airway_lines = main.collect(date(2026, 9, 10))
    assert [f[0] for f in failures] == ["AIRWAY"]
    assert "LLMResponseError" in failures[0][1]
    assert airway_lines is None


def test_bootstrap只寫狀態不推播(env):
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    assert pushed == []
    assert len(main.state.load_seen(tmp_path / "seen.json")) == TOTAL_EVENTS
    assert main.state.load_snapshot(tmp_path / "airway_snapshot.txt") == ["A", "B"]


def test_第二次執行沒有新項目就不推播(env):
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    main.run(bootstrap=False, today=date(2026, 9, 11))
    assert pushed == []


def test_有新項目就推播(env):
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    seen = main.state.load_seen(tmp_path / "seen.json")
    seen.discard("TSA:3105")
    main.state.save_seen(tmp_path / "seen.json", seen)

    main.run(bootstrap=False, today=date(2026, 9, 11))
    assert len(pushed) == 1
    assert "3105" in pushed[0]


def test_推播失敗時狀態不前進(env, monkeypatch):
    # 寫檔成功但推播失敗會造成永久漏報，所以狀態必須排在推播之後
    tmp_path, _, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    seen_before = main.state.load_seen(tmp_path / "seen.json")
    seen_before.discard("TSA:3105")
    main.state.save_seen(tmp_path / "seen.json", seen_before)
    monkeypatch.setattr(main, "collect_airway", lambda: ([], ["A", "B", "C 新公告"], None))

    def boom(text):
        raise RuntimeError("LINE 掛了")

    monkeypatch.setattr(main.notify, "push_line", boom)
    with pytest.raises(RuntimeError):
        main.run(bootstrap=False, today=date(2026, 9, 11))

    # seen 沒補回 3105、快照也沒吃掉那行新公告 → 下一輪還會重推
    assert "TSA:3105" not in main.state.load_seen(tmp_path / "seen.json")
    assert main.state.load_snapshot(tmp_path / "airway_snapshot.txt") == ["A", "B"]


def test_事件推播失敗時告警仍已送出(env, monkeypatch):
    # 告警排在事件推播之前，否則推播一炸，當天的異常告警也一起消失
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    # 造出一則新項目，事件推播才會真的發生（也才炸得起來）
    seen = main.state.load_seen(tmp_path / "seen.json")
    seen.discard("TSA:3105")
    main.state.save_seen(tmp_path / "seen.json", seen)

    import requests
    monkeypatch.setattr(
        main.fetch, "get",
        _fake_fetch(ALL_OK, failures={"congress.tscva.org.tw": requests.ConnectionError("斷線")}),
    )
    sent = []

    def push(text):
        sent.append(text)
        if not text.startswith("⚠️"):
            raise RuntimeError("LINE 掛了")

    monkeypatch.setattr(main.notify, "push_line", push)
    monkeypatch.setattr(main, "collect_airway", lambda: ([], ["A", "B", "新的一行"], None))
    with pytest.raises(RuntimeError):
        main.run(bootstrap=False, today=date(2026, 9, 11))

    assert any(t.startswith("⚠️") for t in sent)


def test_bootstrap遇到失敗站會提醒重跑(env, monkeypatch, capsys):
    import requests
    monkeypatch.setattr(
        main.fetch, "get",
        _fake_fetch(ALL_OK, failures={"congress.tscva.org.tw": requests.ConnectionError("斷線")}),
    )
    main.run(bootstrap=True, today=date(2026, 9, 10))
    out = capsys.readouterr().out
    assert "TSCVA" in out and "再跑一次 bootstrap" in out


def test_每個來源的parser名稱都查得到():
    # PARSERS 查表打錯字會被 except 吞成「該站抓取失敗」，
    # 降級成每 7 天一則告警而不是大聲失敗。這條讓它在測試階段就炸
    for cfg in main.SOURCES:
        if cfg["source"] == "AIRWAY":
            continue
        assert cfg["parser"] in main.PARSERS, cfg


def test_程式錯誤與網站問題在告警上分得開():
    # parser 的 TypeError 會跟斷線走同一條路，但它不會自己好。
    # 人要看得出來該去改 code，而不是等站方修好
    import requests
    assert main._reason(requests.ConnectionError("斷線")).startswith("ConnectionError")
    assert main._reason(TypeError("parser 壞了")).startswith("程式錯誤")


def test_告警原因長度受限以免節流失效():
    # 這串同時是 should_alert 的節流 key，訊息每輪不同的話 7 天冷卻會失效
    long = main._reason(TypeError("x" * 500))
    assert len(long) < 130


def test_程式錯誤會記進failure而非靜默(env, monkeypatch):
    def boom(html, cfg):
        raise TypeError("parser 自己壞了")

    monkeypatch.setitem(main.PARSERS, "tsa", boom)
    _, failures, _ = main.collect(date(2026, 9, 10))
    assert any(k == "TSA" and "程式錯誤" in r for k, r in failures)
