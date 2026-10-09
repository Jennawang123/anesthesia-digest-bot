"""告警文字與節流送出。"""
import json
import sys
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import alerts  # noqa: E402

TODAY = date(2026, 10, 9)


class _Plain(ValueError):
    pass


def test_reason_plain_types_use_their_message():
    assert alerts.reason(_Plain("RSS 無法解析"), plain=(_Plain,)) == "RSS 無法解析"


def test_reason_network():
    assert alerts.reason(requests.ConnectionError("boom")) == "連線失敗 ConnectionError"


def test_reason_anthropic_points_at_billing():
    err = type("APIStatusError", (Exception,), {"__module__": "anthropic._exceptions"})("x")
    assert alerts.reason(err).startswith("Anthropic API 問題（先查餘額與月上限）")


def test_reason_everything_else_is_a_code_bug():
    assert alerts.reason(KeyError("x")) == "程式錯誤（需改 code）KeyError"


def test_send_due_pushes_once_and_throttles(tmp_path):
    path = tmp_path / "alert_state.json"
    pushed = []
    failures = [("omaat", "連線失敗 ConnectionError")]
    assert alerts.send_due(failures, path, TODAY, pushed.append) == 1
    assert pushed[0].startswith("⚠️ 點數促銷監測異常")
    assert alerts.send_due(failures, path, date(2026, 10, 10), pushed.append) == 0
    assert len(pushed) == 1
    assert alerts.send_due(failures, path, date(2026, 10, 16), pushed.append) == 1


def test_send_due_keys_by_source_and_reason(tmp_path):
    path = tmp_path / "alert_state.json"
    pushed = []
    alerts.send_due([("a／抽取", "原因一"), ("a／抽取", "原因二")], path, TODAY, pushed.append)
    assert set(json.loads(path.read_text(encoding="utf-8"))) == {"a／抽取｜原因一", "a／抽取｜原因二"}
    assert alerts.send_due([("a／抽取", "原因一")], path, date(2026, 10, 10), pushed.append) == 0


def test_send_due_nothing_to_send_does_not_create_file(tmp_path):
    path = tmp_path / "alert_state.json"
    assert alerts.send_due([], path, TODAY, lambda t: None) == 0
    assert not path.exists()
