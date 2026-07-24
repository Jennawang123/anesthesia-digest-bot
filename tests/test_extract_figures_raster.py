"""extract_figures_raster 的純幾何函式測試。

全部用合成的 fitz.Rect，不開 PDF —— 幾何邏輯與檔案無關，
測試要能在沒有那本 45MB PDF 的機器上跑。
"""
import sys
from pathlib import Path

import fitz
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from extract_figures_raster import usable_rasters  # noqa: E402

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
