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

# 配對時要求的最小重疊比例
MIN_OVERLAP = 0.3
# 圖與圖說的垂直間隙上限（頁高的比例）。超過就不是同一張圖，
# 用來擋掉頁頂的裝飾圖示被下方的圖說認領。
MAX_GAP = 0.6


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


def _overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _score(cap_rect, r, page_height):
    """caption 與 raster 的配對距離；不成立回傳 None。

    兩種擺法各判一次：
      下方型 —— 圖在 caption 上方，水平方向重疊夠多，距離取垂直間隙。
      旁欄型 —— 圖與 caption 垂直方向重疊夠多、水平不重疊，距離取水平間隙。

    重疊門檻一律相對於「較窄／較矮的那一方」。這點踩過兩次：門檻相對
    caption 寬度時，Fig 15.1 的 8 個窄 panel 全數落空；改成要求 raster
    落在 caption 跨距內時，換成寬圖配窄圖說的 Fig 9.1、12.1、27.7、31.6
    落空。相對較窄一方兩種情形都成立。
    """
    if r.y1 <= cap_rect.y0 + 2:
        h = _overlap(r.x0, r.x1, cap_rect.x0, cap_rect.x1)
        if h > MIN_OVERLAP * min(r.width, cap_rect.width):
            gap = cap_rect.y0 - r.y1
            if gap < MAX_GAP * page_height:
                return gap

    v = _overlap(r.y0, r.y1, cap_rect.y0, cap_rect.y1)
    if v > MIN_OVERLAP * min(r.height, cap_rect.height):
        if _overlap(r.x0, r.x1, cap_rect.x0, cap_rect.x1) <= 0:
            return abs(cap_rect.x0 - r.x1) if r.x1 <= cap_rect.x0 \
                else abs(r.x0 - cap_rect.x1)
    return None


def assign_rasters(captions, rasters, page_height=720):
    """把 raster 分派給 caption，回傳 {fig_id: [rect, ...]}。

    每個 raster 只歸給距離最近的那個 caption —— 同頁有兩三個圖說時
    （實測 22 頁），不這樣做會讓上下兩組圖被同一個圖說吃掉。
    多 panel 圖則是同一個 caption 收到多個 rect，稍後取聯集。
    """
    out = {c["fig_id"]: [] for c in captions}
    for r in rasters:
        best, best_score = None, None
        for c in captions:
            s = _score(c["rect"], r, page_height)
            if s is None:
                continue
            if best_score is None or s < best_score:
                best, best_score = c["fig_id"], s
        if best is not None:
            out[best].append(r)
    return out
