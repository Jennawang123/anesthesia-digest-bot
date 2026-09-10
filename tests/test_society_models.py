"""Event 模型測試。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from society_watch.models import Event  # noqa: E402


def test_key_為來源加站方ID():
    e = Event(source="TSA", uid="3105", title="鎮靜課程",
              date_text="115/11/08", url="https://example.com")
    assert e.key == "TSA:3105"


def test_選填欄位預設值():
    e = Event(source="TSA", uid="3105", title="鎮靜課程",
              date_text="115/11/08", url="https://example.com")
    assert e.kind is None
    assert e.place is None
    assert e.minor is False
