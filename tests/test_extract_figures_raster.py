"""extract_figures_raster 的純幾何函式測試。

全部用合成的 fitz.Rect，不開 PDF —— 幾何邏輯與檔案無關，
測試要能在沒有那本 45MB PDF 的機器上跑。
"""
import sys
from pathlib import Path

import fitz
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from extract_figures_raster import assign_rasters, find_captions, usable_rasters  # noqa: E402

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


def cap(fig_id, rect):
    return {"fig_id": fig_id, "chapter": int(fig_id.split(".")[0]),
            "rect": fitz.Rect(*rect), "text": f"Figure {fig_id} …"}


def test_圖在caption上方():
    # idx21 實測：圖 (65,72,352,491)、圖說 (60,499,440,530)
    got = assign_rasters([cap("1.1", (60, 499, 440, 530))],
                         [fitz.Rect(65, 72, 352, 491)])
    assert got["1.1"] == [fitz.Rect(65, 72, 352, 491)]


def test_圖在旁欄同高():
    # idx26 實測：圖在左欄 (54,73,295,230)、圖說在右欄頂 (307,69,445,101)
    got = assign_rasters([cap("2.1", (307, 69, 445, 101))],
                         [fitz.Rect(54, 73, 295, 230)])
    assert got["2.1"] == [fitz.Rect(54, 73, 295, 230)]


def test_多panel窄圖全部歸給同一個caption():
    # idx168 實測型態：Fig 15.1 有 8 個 panel，每個只有 59-73pt 寬，
    # 遠小於 385pt 的圖說寬度。門檻若相對圖說寬度，這些 panel 會全數落空。
    rects = [fitz.Rect(60, 83, 119, 165),
             fitz.Rect(139, 73, 205, 162),
             fitz.Rect(228, 73, 300, 278)]
    got = assign_rasters([cap("15.1", (54, 286, 439, 327))], rects)
    assert sorted(got["15.1"], key=lambda r: (r.y0, r.x0)) == \
        sorted(rects, key=lambda r: (r.y0, r.x0))


def test_寬圖配窄圖說也要配對成功():
    # 反向情形：圖比圖說寬。門檻若要求 raster 落在圖說跨距內，這種會落空。
    got = assign_rasters([cap("12.1", (60, 400, 200, 430))],
                         [fitz.Rect(55, 90, 445, 390)])
    assert got["12.1"] == [fitz.Rect(55, 90, 445, 390)]


def test_距離過遠的碎塊不配對():
    # idx88 實測：Fig 7.3 的圖說在 y=579，頁頂有個 23pt 寬的裝飾圖示，
    # 水平雖然對得上，但隔了大半頁，不該被當成這張圖的內容。
    got = assign_rasters([cap("7.3", (60, 579, 434, 600))],
                         [fitz.Rect(71, 77, 94, 105)])
    assert got["7.3"] == []


def test_同頁兩個caption各自取到自己的圖():
    # idx100 實測型態：上下各一組圖說
    got = assign_rasters(
        [cap("8.3", (54, 301, 445, 330)), cap("8.4", (54, 646, 445, 675))],
        [fitz.Rect(60, 80, 440, 295), fitz.Rect(60, 380, 440, 640)])
    assert got["8.3"] == [fitz.Rect(60, 80, 440, 295)]
    assert got["8.4"] == [fitz.Rect(60, 380, 440, 640)]


def test_沒有可配對的圖時回傳空清單():
    assert assign_rasters([cap("7.2", (54, 69, 445, 100))], []) == {"7.2": []}
