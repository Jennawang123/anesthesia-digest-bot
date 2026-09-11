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
    "tsamairway.org.tw": "airway_page_20260910.html",
    # 順序有意義：下載頁的網址同時含有 "tweccm.org.tw/"，
    # 首頁那筆若排在前面會把下載頁一起吃掉，公告列表靜默變成首頁內容
    "tweccm.org.tw/download": "tweccm_download_20260912.html",
    "tweccm.org.tw/": "tweccm_home_20260912.html",
}

# TSA 15 + TSCVA 6 + RAPM 16 + RAPM 11 + PAIN 10（今年）+ 0（明年空表）
# + TWECCM 公告 4；兩個文字來源（AIRWAY、TWECCM 首頁）首次執行都回 0 筆
TOTAL_EVENTS = 62

AIRWAY_LINES = 117      # tests/test_society_extract.py 對同一份 fixture 的斷言
TWECCM_HOME_LINES = 109


def _fake_text_source(cfg):
    """假的文字來源：每個來源回不同內容，快照才驗得出有沒有互相覆蓋。"""
    return [], [cfg["source"], "A", "B"], None


@pytest.fixture
def env(tmp_path, monkeypatch):
    """把狀態檔導到 tmp、攔截推播、AIRWAY 預設成功但無新增。"""
    pushed = []
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main.fetch, "get", _fake_fetch(ALL_OK))
    monkeypatch.setattr(main, "collect_text_source", _fake_text_source)
    monkeypatch.setattr(main.notify, "push_line", lambda text: pushed.append(text))
    return tmp_path, pushed, monkeypatch


def test_收集全部來源事件(env):
    events, failures, snapshots = main.collect(date(2026, 9, 10))
    assert failures == []
    assert len(events) == TOTAL_EVENTS
    # 兩個文字來源各自登記自己的快照，內容不會互相汙染
    assert snapshots == {
        "AIRWAY": ["AIRWAY", "A", "B"],
        "TWECCM": ["TWECCM", "A", "B"],
    }


def test_tweccm公告列表有被抓進來(env):
    events, _, _ = main.collect(date(2026, 9, 10))
    tweccm = [e for e in events if e.source == "TWECCM"]
    assert len(tweccm) == 4
    assert tweccm[0].uid == "130"


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


def test_tweccm兩筆設定的告警key互不相干(tmp_path, monkeypatch):
    # TWECCM 跟 RAPM 一樣共用 source 代號，公告列表與首頁是兩個不同的頁面，
    # 其中一個壞掉不可以吃掉另一個的 7 天冷卻期
    import requests
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        main.fetch, "get",
        _fake_fetch(ALL_OK, failures={"tweccm.org.tw/download": requests.ConnectionError("斷線")}),
    )
    _, failures, snapshots = main.collect(date(2026, 9, 12))
    assert [f[0] for f in failures] == ["TWECCM／其他公告"]
    # 首頁那筆照樣成功，快照照樣登記
    assert len(snapshots["TWECCM"]) == TWECCM_HOME_LINES


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


def test_文字來源失敗時不登記快照(env, monkeypatch):
    def _one_fails(cfg):
        if cfg["source"] == "AIRWAY":
            return [], ["半截"], "行數暴跌"
        return _fake_text_source(cfg)

    monkeypatch.setattr(main, "collect_text_source", _one_fails)
    _, failures, snapshots = main.collect(date(2026, 9, 10))
    assert ("AIRWAY", "行數暴跌") in failures
    # 失敗的來源不進 dict → advance_state 就不會推進它的快照
    assert "AIRWAY" not in snapshots
    # 另一個文字來源不受影響，照樣前進
    assert snapshots["TWECCM"] == ["TWECCM", "A", "B"]


AIRWAY_CFG = next(c for c in main.SOURCES if c["source"] == "AIRWAY")
TWECCM_HOME_CFG = next(
    c for c in main.SOURCES if c["source"] == "TWECCM" and c["parser"] == "text"
)


def test_文字來源首次執行不送llm只建快照(tmp_path, monkeypatch):
    # 其餘測試都把 collect_text_source 整個換掉，這裡是真的跑它本體的地方
    html = (FIXTURES / "airway_page_20260910.html").read_text(encoding="utf-8")
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main.fetch, "get", lambda url, **kwargs: html)
    called = []
    monkeypatch.setattr(
        main.llm, "classify",
        lambda lines, source, society, url: called.append(lines) or [],
    )

    events, lines, error = main.collect_text_source(AIRWAY_CFG)
    assert (events, error) == ([], None)
    assert len(lines) == AIRWAY_LINES
    # 沒有舊快照時整頁都算「新增」，照送 Haiku 會直接撞上 MAX_NEW_LINES
    assert called == []


def test_文字來源第二輪只把新增行送llm且帶對來源(tmp_path, monkeypatch):
    # 一般化之後最容易靜默壞掉的地方：classify 若拿到別站的 source/label/url，
    # 事件會掛到錯誤的學會底下，而筆數與流程完全正常
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    main.state.save_snapshot(tmp_path / "snapshot_tweccm.txt", ["舊的一行"])
    monkeypatch.setattr(
        main.fetch, "get",
        lambda url, **kwargs: "<div>舊的一行</div><div>新的一行</div>",
    )
    called = []
    monkeypatch.setattr(
        main.llm, "classify",
        lambda lines, source, society, url: called.append((lines, source, society, url)) or [],
    )

    main.collect_text_source(TWECCM_HOME_CFG)
    assert called == [(
        ["新的一行"], "TWECCM", "急重症聯合年會（SECC）", "https://www.tweccm.org.tw/",
    )]


def test_兩個文字來源寫到不同的快照檔(tmp_path, monkeypatch):
    # 檔名若不隨來源改變，後跑的會整個蓋掉先跑的，兩邊從此每輪誤判整頁新增
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main.fetch, "get", _fake_fetch(ALL_OK))
    monkeypatch.setattr(main.notify, "push_line", lambda text: None)
    main.run(bootstrap=True, today=date(2026, 9, 12))

    airway = main.state.load_snapshot(tmp_path / "snapshot_airway.txt")
    tweccm = main.state.load_snapshot(tmp_path / "snapshot_tweccm.txt")
    assert len(airway) == AIRWAY_LINES
    assert len(tweccm) == TWECCM_HOME_LINES
    assert airway[:1] != tweccm[:1]


def test_一個文字來源失敗不影響另一個的快照(tmp_path, monkeypatch):
    # 「失敗的來源不推進快照」的端到端版本：AIRWAY 斷線，它的舊快照必須原封不動，
    # 而 TWECCM 首頁照樣寫出新的
    import requests
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    main.state.save_snapshot(tmp_path / "snapshot_airway.txt", ["舊快照"])
    monkeypatch.setattr(
        main.fetch, "get",
        _fake_fetch(ALL_OK, failures={"tsamairway.org.tw": requests.ConnectionError("斷線")}),
    )
    monkeypatch.setattr(main.notify, "push_line", lambda text: None)
    failures = main.run(bootstrap=True, today=date(2026, 9, 12))

    assert [f[0] for f in failures] == ["AIRWAY"]
    assert main.state.load_snapshot(tmp_path / "snapshot_airway.txt") == ["舊快照"]
    assert len(main.state.load_snapshot(tmp_path / "snapshot_tweccm.txt")) == TWECCM_HOME_LINES


def test_文字來源行數暴跌時回報疑似改版且不送llm(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    main.state.save_snapshot(
        tmp_path / "snapshot_airway.txt", [f"第 {i} 行" for i in range(100)]
    )
    monkeypatch.setattr(
        main.fetch, "get", lambda url, **kwargs: "<html><body>只剩這一行</body></html>"
    )
    called = []
    monkeypatch.setattr(
        main.llm, "classify",
        lambda lines, source, society, url: called.append(lines) or [],
    )

    events, lines, error = main.collect_text_source(AIRWAY_CFG)
    assert events == []
    assert error is not None and "暴跌" in error
    assert called == []


def test_文字來源拋例外時記成失敗且不推進快照(env, monkeypatch):
    # llm.classify 回垃圾時會拋 LLMResponseError，必須變成告警而不是「今天沒活動」
    def boom(cfg):
        raise main.llm.LLMResponseError("Haiku 回應無法解析為 JSON 陣列")

    monkeypatch.setattr(main, "collect_text_source", boom)
    _, failures, snapshots = main.collect(date(2026, 9, 10))
    assert [f[0] for f in failures] == ["AIRWAY", "TWECCM／首頁"]
    assert all("LLMResponseError" in r for _, r in failures)
    assert snapshots == {}


def test_bootstrap只寫狀態不推播(env):
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    assert pushed == []
    assert len(main.state.load_seen(tmp_path / "seen.json")) == TOTAL_EVENTS
    assert main.state.load_snapshot(tmp_path / "snapshot_airway.txt") == ["AIRWAY", "A", "B"]
    assert main.state.load_snapshot(tmp_path / "snapshot_tweccm.txt") == ["TWECCM", "A", "B"]


def test_第二次執行沒有新項目就不推播(env):
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    main.run(bootstrap=False, today=date(2026, 9, 11))
    # 心跳是無條件的，這裡只斷言「沒有活動通知」
    assert not any(t.startswith("🔔") for t in pushed)


def test_有新項目就推播(env):
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    seen = main.state.load_seen(tmp_path / "seen.json")
    seen.discard("TSA:3105")
    main.state.save_seen(tmp_path / "seen.json", seen)

    main.run(bootstrap=False, today=date(2026, 9, 11))
    events_pushed = [t for t in pushed if t.startswith("🔔")]
    assert len(events_pushed) == 1
    assert "3105" in events_pushed[0]


def test_推播失敗時狀態不前進(env, monkeypatch):
    # 寫檔成功但推播失敗會造成永久漏報，所以狀態必須排在推播之後
    tmp_path, _, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    seen_before = main.state.load_seen(tmp_path / "seen.json")
    seen_before.discard("TSA:3105")
    main.state.save_seen(tmp_path / "seen.json", seen_before)
    monkeypatch.setattr(
        main, "collect_text_source",
        lambda cfg: ([], [cfg["source"], "A", "B", "C 新公告"], None),
    )

    def boom(text):
        raise RuntimeError("LINE 掛了")

    monkeypatch.setattr(main.notify, "push_line", boom)
    with pytest.raises(RuntimeError):
        main.run(bootstrap=False, today=date(2026, 9, 11))

    # seen 沒補回 3105、兩份快照也都沒吃掉那行新公告 → 下一輪還會重推
    assert "TSA:3105" not in main.state.load_seen(tmp_path / "seen.json")
    assert main.state.load_snapshot(tmp_path / "snapshot_airway.txt") == ["AIRWAY", "A", "B"]
    assert main.state.load_snapshot(tmp_path / "snapshot_tweccm.txt") == ["TWECCM", "A", "B"]


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
    monkeypatch.setattr(
        main, "collect_text_source",
        lambda cfg: ([], [cfg["source"], "A", "B", "新的一行"], None),
    )
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
    # 文字來源走的是 collect_text_source，不查 PARSERS；其餘每一筆都必須查得到
    checked = 0
    for cfg in main.SOURCES:
        if cfg["parser"] == "text":
            continue
        assert cfg["parser"] in main.PARSERS, cfg
        checked += 1
    assert checked == len(main.SOURCES) - 2      # 目前有兩筆 text 設定


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


def test_每月第一次成功執行會送心跳(env):
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    main.run(bootstrap=False, today=date(2026, 9, 11))
    assert any(t.startswith("💓") for t in pushed)


def test_同月第二次不再送心跳(env):
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    main.run(bootstrap=False, today=date(2026, 9, 11))
    pushed.clear()
    main.run(bootstrap=False, today=date(2026, 9, 12))
    assert not any(t.startswith("💓") for t in pushed)


def test_跨月會再送一次心跳(env):
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    main.run(bootstrap=False, today=date(2026, 9, 11))
    pushed.clear()
    main.run(bootstrap=False, today=date(2026, 10, 1))
    assert any(t.startswith("💓") for t in pushed)


def test_bootstrap不送心跳(env):
    tmp_path, pushed, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    assert pushed == []


def test_推播失敗那輪不送心跳也不記錄(env, monkeypatch):
    # 心跳排在 advance_state 之後，語意是「一個完整週期跑完了」
    tmp_path, _, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))
    seen = main.state.load_seen(tmp_path / "seen.json")
    seen.discard("TSA:3105")
    main.state.save_seen(tmp_path / "seen.json", seen)

    def boom(text):
        raise RuntimeError("LINE 掛了")

    monkeypatch.setattr(main.notify, "push_line", boom)
    with pytest.raises(RuntimeError):
        main.run(bootstrap=False, today=date(2026, 9, 11))
    assert main.state.load_heartbeat(tmp_path / "heartbeat.json") is None


def test_心跳推播失敗就不記錄以免下月缺一拍(env, monkeypatch):
    # save_heartbeat 必須排在心跳自己的 push_line 之後。順序反過來的話，
    # 心跳推播失敗那個月會被記成「已送」而永久缺一拍——正好製造這功能要防的假警報
    tmp_path, _, _ = env
    main.run(bootstrap=True, today=date(2026, 9, 10))

    def push(text):
        if text.startswith("💓"):
            raise RuntimeError("心跳送不出去")

    monkeypatch.setattr(main.notify, "push_line", push)
    with pytest.raises(RuntimeError):
        main.run(bootstrap=False, today=date(2026, 9, 11))

    assert main.state.load_heartbeat(tmp_path / "heartbeat.json") is None
    assert main.state.load_seen(tmp_path / "seen.json")          # 活動狀態仍已推進


def test_心跳狀態檔壞掉時當成該送(tmp_path, monkeypatch):
    # heartbeat.json 也會 commit 進 public repo。load_alerts 有 isinstance 守門、
    # should_alert 有 try/except，這裡不該是唯一裸奔的那個
    p = tmp_path / "heartbeat.json"
    for broken in ['[]', 'null', '"x"', '不是 json', '{"last": 202609}']:
        p.write_text(broken, encoding="utf-8")
        assert main.state.load_heartbeat(p) is None, broken


def test_run回傳failures供呼叫端判斷(env, monkeypatch):
    import requests
    monkeypatch.setattr(
        main.fetch, "get",
        _fake_fetch(ALL_OK, failures={"congress.tscva.org.tw": requests.ConnectionError("斷線")}),
    )
    failures = main.run(bootstrap=True, today=date(2026, 9, 10))
    assert [f[0] for f in failures] == ["TSCVA"]


def test_anthropic錯誤不會被標成程式錯誤():
    # 餘額用盡與月上限都會走到這裡。標成「程式錯誤」會把人引導去查程式碼，
    # 但實際上該先看帳單餘額
    class _FakeAnthropicError(Exception):
        pass
    _FakeAnthropicError.__module__ = "anthropic"

    reason = main._reason(_FakeAnthropicError("credit balance is too low"))
    assert "先查餘額" in reason
    assert "程式錯誤" not in reason


def test_全站皆失敗時以非零狀態結束(env, monkeypatch):
    # 告警是同站同壞法 7 天一次，第 2～7 天會變成「全綠燈、零訊息」，
    # 跟「今天真的沒有新活動」在 Actions 摘要頁上完全同形
    import requests

    def all_down(url, **kwargs):
        raise requests.ConnectionError("全掛")

    def text_down(cfg):
        raise requests.ConnectionError("全掛")

    monkeypatch.setattr(main.fetch, "get", all_down)
    # env fixture 把 collect_text_source 換成永遠成功的假貨，這裡要蓋回去，
    # 否則「全站皆失敗」其實只有六站失敗，門檻永遠碰不到
    monkeypatch.setattr(main, "collect_text_source", text_down)
    monkeypatch.setattr(main.sys, "argv", ["main"])
    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 1
