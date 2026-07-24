#!/usr/bin/env python3
"""依 raster 圖框抽取 Nasr ed2 的 figure。

與 extract_figures.py（Miller 專用）的前提相反：Nasr 第二版全書向量繪圖
物件為 0，每張圖都是完整的內嵌 raster，圖框本身就是精確的裁切邊界，
不需要 Miller 那套「從 caption 往上找內文邊界」的啟發式。

用法：
    python3 scripts/extract_figures_raster.py <PDF> <輸出目錄> [--chapters 8 9] [--dpi 200]
"""

import re

import fitz

# 每頁固定有兩張整頁尺寸的背景層，不是圖
BG_MIN_W, BG_MIN_H = 440, 640
# 小於這個尺寸的是裝飾碎塊（項目符號、logo）
MIN_RASTER = 20

# Nasr 用「Figure 8.1」全字，Miller 用「Fig. 28.3」。複數形 Figures 因為
# 「Figure」後面接的是 s 而非空白或數字，天然不會命中。
CAPTION_RE = re.compile(r"^Figure\s*(\d+)\.(\d+)")


def usable_rasters(page):
    """回傳頁面上真正屬於圖的 raster 框，濾掉背景層與碎塊。"""
    out = []
    for img in page.get_images():
        for r in page.get_image_rects(img[0]):
            if r.width > BG_MIN_W and r.height > BG_MIN_H:
                continue
            if r.width < MIN_RASTER or r.height < MIN_RASTER:
                continue
            out.append(r)
    return out


def find_captions(blocks):
    """從 text block 找出圖說。

    內文裡的交叉引用偶爾會出現在 block 開頭（實測 idx98 的
    「Figure 8.1. Figures 8.2-8.9 summarize…」），它用的是內文字體，
    真正的圖說不是。靠字體排除，實測全書零誤判。
    """
    out = []
    for b in blocks:
        m = CAPTION_RE.match(b["text"])
        if not m or b["is_body"]:
            continue
        out.append({
            "fig_id": f"{m.group(1)}.{m.group(2)}",
            "chapter": int(m.group(1)),
            "rect": b["rect"],
            "text": b["text"],
        })
    return out
