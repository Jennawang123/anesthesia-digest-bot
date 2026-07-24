"""章號查表填 target_page_id 的測試。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from map_nasr_figures import apply_map  # noqa: E402

TABLE = {
    "8": {"title": "Echocardiography", "notion_page_id": "page-echo"},
    "27": {"title": "TGA", "split": True, "options": [
        {"notion_title": "D-TGA", "notion_page_id": "page-dtga"},
        {"notion_title": "L-TGA", "notion_page_id": "page-ltga"}]},
}


def fig(fig_id, chapter, page_id=None):
    return {"fig_id": fig_id, "nasr_chapter": chapter,
            "target_page_id": page_id, "include": True}


def test_一般章直接填入page_id():
    figs = [fig("8.3", 8)]
    assert apply_map(figs, TABLE) == (1, [])
    assert figs[0]["target_page_id"] == "page-echo"


def test_split章不自動填並列入待人工分派():
    figs = [fig("27.1", 27), fig("27.2", 27)]
    assert apply_map(figs, TABLE) == (0, ["27.1", "27.2"])
    assert figs[0]["target_page_id"] is None


def test_已填過的不覆蓋():
    figs = [fig("8.3", 8, "手動指定的頁")]
    assert apply_map(figs, TABLE) == (0, [])
    assert figs[0]["target_page_id"] == "手動指定的頁"


def test_對照表沒有的章列入待人工分派():
    figs = [fig("99.1", 99)]
    assert apply_map(figs, TABLE) == (0, ["99.1"])
