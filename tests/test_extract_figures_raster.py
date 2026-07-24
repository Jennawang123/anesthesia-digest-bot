"""extract_figures_raster 的純幾何函式測試。

全部用合成的 fitz.Rect，不開 PDF —— 幾何邏輯與檔案無關，
測試要能在沒有那本 45MB PDF 的機器上跑。
"""
import sys
from pathlib import Path

import fitz
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from extract_figures_raster import find_captions, usable_rasters  # noqa: E402

PAGE = fitz.Rect(0, 0, 480.5, 720)


class FakePage:
    """只提供 usable_rasters 需要的介面：rect、get_images、get_image_rects。"""

    def __init__(self, rects):
        self._rects = rects
        self.rect = PAGE

    def get_images(self):
        return [(i,) for i in range(len(self._rects))]

    def get_image_rects(self, xref):
        return [self._rects[xref]]


def test_濾掉整頁背景層():
    page = FakePage([
        fitz.Rect(0, 0, 480.5, 720),      # 背景層
        fitz.Rect(0, 0, 480.5, 720),      # 第二層背景
        fitz.Rect(65, 72, 352, 491),      # 真正的圖
    ])
    assert usable_rasters(page) == [fitz.Rect(65, 72, 352, 491)]


def test_濾掉過小的碎塊():
    page = FakePage([
        fitz.Rect(60, 60, 75, 75),        # 15x15，太小
        fitz.Rect(54, 73, 295, 230),      # 真正的圖
    ])
    assert usable_rasters(page) == [fitz.Rect(54, 73, 295, 230)]


def test_沒有可用圖時回傳空清單():
    assert usable_rasters(FakePage([fitz.Rect(0, 0, 480.5, 720)])) == []


def block(text, rect, is_body=False):
    """模擬 extract_figures.text_blocks() 的輸出格式。"""
    return {"text": text, "rect": fitz.Rect(*rect), "is_body": is_body}


def test_抓出圖說並拆出章號與編號():
    caps = find_captions([
        block("Figure 8.3 Subxiphoid short-axis sweep.", (54, 301, 445, 330)),
    ])
    assert len(caps) == 1
    assert caps[0]["fig_id"] == "8.3"
    assert caps[0]["chapter"] == 8
    assert caps[0]["rect"] == fitz.Rect(54, 301, 445, 330)


def test_排除內文字體的交叉引用():
    caps = find_captions([
        block("Figure 8.1. Figures 8.2-8.9 summarize the images.",
              (60, 213, 440, 240), is_body=True),
        block("Figure 8.1 Transducer locations for standard TTE windows.",
              (60, 69, 440, 100)),
    ])
    assert [c["fig_id"] for c in caps] == ["8.1"]
    assert caps[0]["rect"].y0 == 69


def test_複數形的Figures不算圖說():
    assert find_captions([block("Figures 2.1 and 2.2 illustrate this.",
                                (60, 100, 440, 130))]) == []


def test_Table與Box不算圖說():
    assert find_captions([
        block("Table 1.1 Cardiovascular embryologic structure.", (54, 69, 377, 82)),
        block("Box 3.2 Preoperative checklist.", (54, 200, 377, 220)),
    ]) == []
