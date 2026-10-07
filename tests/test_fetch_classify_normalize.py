"""分類結果正規化測試。

daily_fetch_classify 在 import 時就建立 Anthropic client，所以先塞假金鑰
（建立 client 不會連線）。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("CLAUDE_API_KEY", "test-key")

import daily_fetch_classify as dfc  # noqa: E402


def test_正常輸入原樣通過():
    assignment, scores = dfc._normalize_classification(
        {"assignments": {"1": [1, 2], "3": [5]}, "scores": {"1": 8, "2": 6, "5": 9}}
    )
    assert assignment == {"1": [1, 2], "2": [], "3": [5], "4": [], "5": []}
    assert scores == {1: 8, 2: 6, 5: 9}


def test_字串索引轉成int():
    """9/21 的事故：Haiku 把索引回成字串，下游拿 int 跟 str 比大小就炸。"""
    assignment, _ = dfc._normalize_classification({"assignments": {"1": ["12", 3]}})
    assert assignment["1"] == [12, 3]


def test_轉不了的索引被丟掉():
    assignment, _ = dfc._normalize_classification(
        {"assignments": {"2": [4, "abc", None, 7]}}
    )
    assert assignment["2"] == [4, 7]


def test_主題值不是list視為空():
    assignment, _ = dfc._normalize_classification({"assignments": {"1": "3", "2": None}})
    assert assignment["1"] == [] and assignment["2"] == []


def test_assignments不是dict時五個主題都給空list():
    assignment, scores = dfc._normalize_classification({"assignments": [1, 2]})
    assert assignment == {k: [] for k in "12345"}
    assert scores == {}


def test_score的key或value轉不了就丟掉那一筆():
    _, scores = dfc._normalize_classification(
        {"scores": {"1": "8", "2": "high", "x": 5, "3": None}}
    )
    assert scores == {1: 8}


def test_正規化後的結果餵給classify不會炸(monkeypatch):
    articles = [{"title": f"t{i}", "journal": "J"} for i in range(1, 4)]
    monkeypatch.setattr(
        dfc, "_call1_classify_and_score",
        lambda arts: dfc._normalize_classification(
            {"assignments": {"1": ["1", "3"]}, "scores": {"1": "9"}}
        ),
    )
    monkeypatch.setattr(dfc, "_call2_hot_themes", lambda c: {k: None for k in "12345"})
    out = dfc.classify_articles(articles)
    assert [a["title"] for a in out["1"]["items"]] == ["t1", "t3"]
    assert out["1"]["items"][0]["score"] == 9
