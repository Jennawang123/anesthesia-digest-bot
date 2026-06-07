"""
病人資料自動擷取模組
校正時截取 AI / G 按鈕圖片，執行時用圖像識別定位按鈕，不依賴固定座標。
"""

import json
import os
import time
import subprocess
import pyautogui
import pyperclip
from dataclasses import dataclass

pyautogui.FAILSAFE = False


class AbortError(Exception):
    """AI tab 未開啟等需要立即中止整個程序的錯誤"""


CALIBRATION_FILE = os.path.join(os.path.dirname(__file__), "calibration.json")
TEMPLATE_DIR = os.path.dirname(__file__)


@dataclass
class Patient:
    room: str
    seq: str
    name: str
    mrn: str
    gender: str
    age: str
    diagnosis: str
    procedure: str
    attending: str
    anesthesiologist: str = ""
    asa_grade: str = ""
    ai_summary: str = ""
    preanesthesia_eval: str = ""


# ── 校正工具 ──────────────────────────────────────────────

def _load_cal():
    if os.path.exists(CALIBRATION_FILE):
        with open(CALIBRATION_FILE) as f:
            return json.load(f)
    return {"fields": {}}


def _save_cal(cal):
    with open(CALIBRATION_FILE, "w") as f:
        json.dump(cal, f, ensure_ascii=False, indent=2)


def _bounds(cal: dict):
    """動態取得 Citrix Viewer 視窗即時位置，失敗才回落到校正檔"""
    script = '''
tell application "System Events"
    tell process "Citrix Viewer"
        set pos to position of front window
        set sz to size of front window
        return ((item 1 of pos) as text) & "," & ((item 2 of pos) as text) & "," & ((item 1 of sz) as text) & "," & ((item 2 of sz) as text)
    end tell
end tell
'''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        try:
            parts = result.stdout.strip().split(",")
            return int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
        except Exception:
            pass
    b = cal["window_bounds"]
    return b["x"], b["y"], b["w"], b["h"]


def _abs(key: str, cal: dict, bounds: tuple):
    f = cal["fields"][key]
    bx, by, bw, bh = bounds
    return bx + int(bw * f["rx"]), by + int(bh * f["ry"])


def _capture_template(key: str, mx: int, my: int, w: int = 56, h: int = 24):
    """截取按鈕模板圖片（以按鈕中心為準）"""
    region = (mx - w // 2, my - h // 2, w, h)
    img = pyautogui.screenshot(region=region)
    path = os.path.join(TEMPLATE_DIR, f"{key}_template.png")
    img.save(path)
    print(f"    已截取模板：{key}_template.png")
    return path


def _record_point(prompt: str, cal: dict, key: str, bounds: tuple,
                  capture: bool = False):
    input(f"\n{prompt}：")
    mx, my = pyautogui.position()
    bx, by, bw, bh = bounds
    cal["fields"][key] = {
        "rx": (mx - bx) / bw,
        "ry": (my - by) / bh,
    }
    if capture:
        _capture_template(key, mx, my)
    print(f"  已記錄 {key}")


def _activate_citrix():
    """把 Citrix Viewer 視窗帶到前景，確保鍵盤事件送到 Citrix"""
    subprocess.run(
        ["osascript", "-e", 'tell application "Citrix Viewer" to activate'],
        capture_output=True
    )
    time.sleep(0.6)


def _click_page_body(bounds: tuple):
    """點擊網頁內容區（非按鈕處）以給予鍵盤焦點，確保 Ctrl+A+C 能擷取頁面文字

    位置：視窗左半中央（50% x, 20% y），應落在頁面標題列，遠離右側按鈕與底部資料列。
    """
    bx, by, bw, bh = bounds
    safe_x = bx + int(bw * 0.50)
    safe_y = by + int(bh * 0.20)
    pyautogui.click(safe_x, safe_y)
    time.sleep(0.4)


def _find_buttons(template_key: str, confidence: float = 0.60) -> list[tuple[int, int]]:
    """用圖像識別找出畫面上所有相同按鈕，回傳由上到下的中心座標列表"""
    path = os.path.join(TEMPLATE_DIR, f"{template_key}_template.png")
    if not os.path.exists(path):
        return []
    try:
        locations = list(pyautogui.locateAllOnScreen(path, confidence=confidence))
        centers = [pyautogui.center(loc) for loc in locations]
        return sorted(centers, key=lambda c: c.y)
    except Exception as e:
        print(f"    [圖像識別失敗 {template_key}]: {e}")
        return []


def calibrate_schedule_buttons():
    """一次性校正排程表按鈕與頁面按鈕座標，並截取 AI/G 按鈕模板圖片"""
    cal = _load_cal()
    bounds = _bounds(cal)

    print("\n=== 排程表按鈕校正 ===")
    print("請確認 Citrix 全螢幕，顯示手術排程查詢，至少有 2 筆病人資料")

    _record_point("請將滑鼠移到【第1列】的綠色 AI 按鈕中央",
                  cal, "row1_ai", bounds, capture=True)
    _record_point("請將滑鼠移到【第1列】的 G 彩色按鈕中央（不是 AI，是左邊那個）",
                  cal, "row1_gsv", bounds, capture=True)
    _record_point("請將滑鼠移到【第2列】的 AI 按鈕中央（計算行距備用）",
                  cal, "row2_ai", bounds, capture=False)

    print("\n=== AI 摘要頁複製按鈕校正 ===")
    print("請手動點開任一病人的 AI 按鈕，等 AI 摘要頁完整載入")
    input("AI 頁載入完成後按 Enter...")
    _record_point("請將滑鼠移到 AI 頁右上角的【複製】按鈕中央", cal, "ai_copy_btn", bounds)
    print("\n請關閉 AI 分頁（Ctrl+W），回到排程頁")
    input("回到排程頁後按 Enter...")

    print("\n=== 術前評估頁按鈕校正 ===")
    print("請手動點開任一病人的 G 按鈕，等術前評估頁載入")
    input("術前評估頁已載入後按 Enter...")
    _record_point("請將滑鼠移到左下角的【檢視】按鈕", cal, "eval_view_btn", bounds)

    print("\n請關閉術前評估分頁（Ctrl+W），回到排程頁")
    input("回到排程頁後按 Enter...")

    _save_cal(cal)
    print("\n排程按鈕校正完成！")
    return cal


def _need_schedule_cal(cal: dict) -> bool:
    needed = ["row1_ai", "row1_gsv", "row2_ai", "ai_copy_btn", "eval_view_btn"]
    if not all(k in cal.get("fields", {}) for k in needed):
        return True
    for key in ("row1_ai", "row1_gsv"):
        if not os.path.exists(os.path.join(TEMPLATE_DIR, f"{key}_template.png")):
            return True
    return False


# ── 擷取邏輯 ──────────────────────────────────────────────

def _click(x, y, wait=0.4):
    pyautogui.click(x, y)
    time.sleep(wait)


def _wait_for_page(seconds=6):
    time.sleep(seconds)


def _calc_row_coords(row_index: int, cal: dict, bounds: tuple):
    """行距計算法（圖像識別失敗時的備用）"""
    fields = cal["fields"]
    bx, by, bw, bh = bounds
    ai_ry_base = fields["row1_ai"]["ry"]
    row_delta_ry = fields["row2_ai"]["ry"] - ai_ry_base
    ai_x = bx + int(bw * fields["row1_ai"]["rx"])
    ai_y = by + int(bh * (ai_ry_base + row_index * row_delta_ry))
    gsv_x = bx + int(bw * fields["row1_gsv"]["rx"])
    gsv_y = by + int(bh * (fields["row1_gsv"]["ry"] + row_index * row_delta_ry))
    return (ai_x, ai_y), (gsv_x, gsv_y)


# 排程頁特有文字，用來過濾誤判
_SCHEDULE_MARKERS = ["G同AI", "手術排程", "排程查詢", "查詢開始日期", "麻醉醫師班"]
# AI 頁特有文字，偵測是否成功進入 AI tab
_AI_MARKER = "AI元件輔助運作"


def _poll_clipboard(bounds: tuple, max_wait: int = 90, min_len: int = 50) -> str:
    """每 3 秒點頁面主體 + Ctrl+A+C，直到剪貼簿有足夠內容且不是排程頁，或逾時"""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        _activate_citrix()
        _click_page_body(bounds)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.6)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(1.5)
        content = pyperclip.paste() or ""
        content = content.strip()
        is_schedule = any(m in content for m in _SCHEDULE_MARKERS)
        if len(content) >= min_len and not is_schedule:
            return content
        remaining = int(deadline - time.time())
        print(f"({remaining}s)", end="", flush=True)
        time.sleep(3)
    return (pyperclip.paste() or "").strip()


def _on_schedule(bounds: tuple) -> bool:
    """偵測當前頁面是否為排程頁（等 5s 頁面渲染後，點頁面主體再 Ctrl+A+C）"""
    time.sleep(5.0)
    pyperclip.copy("")
    _activate_citrix()
    _click_page_body(bounds)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.8)
    pyautogui.hotkey("ctrl", "c")
    time.sleep(2.0)
    content = (pyperclip.paste() or "")
    return any(m in content for m in _SCHEDULE_MARKERS)


def _close_until_schedule(bounds: tuple, max_tabs: int = 3):
    """持續關分頁直到回到排程頁，每次關後等 5s 讓頁面渲染"""
    for i in range(max_tabs):
        if _on_schedule(bounds):
            print(f"\n    [已回排程頁，關了{i}個分頁]", end="")
            return
        _activate_citrix()
        time.sleep(0.5)
        pyautogui.hotkey("ctrl", "w")
    if _on_schedule(bounds):
        print(f"\n    [已回排程頁，關了{max_tabs}個分頁]", end="")
    else:
        print(f"\n    [警告：關了{max_tabs}分頁，仍未偵測到排程頁]", end="")


def _extract_one(patient: Patient,
                 ai_xy: tuple, gsv_xy: tuple,
                 view_xy: tuple, copy_xy: tuple,
                 bounds: tuple) -> Patient:
    """擷取單一病人的 AI 摘要與術前評估"""
    ai_x,  ai_y   = ai_xy
    gsv_x, gsv_y  = gsv_xy
    view_x, view_y = view_xy
    copy_x, copy_y = copy_xy

    # ── A. AI 摘要：點 AI → 等 180s → 偵測頁面 → 複製按鈕 ──
    pyperclip.copy("")
    _activate_citrix()
    _click(ai_x, ai_y)
    print("\n    [等AI載入 180s]", end="", flush=True)
    time.sleep(180)

    # 偵測是否仍在排程頁（先點頁面主體給焦點，再 Ctrl+A+C）
    _activate_citrix()
    _click_page_body(bounds)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.8)
    pyautogui.hotkey("ctrl", "c")
    time.sleep(2.0)
    detect = (pyperclip.paste() or "")
    if any(m in detect for m in _SCHEDULE_MARKERS):
        print(f"\n    [AI] 仍在排程頁，AI tab 未開啟，中止程序")
        raise AbortError(f"{patient.name}：AI tab 未開啟（偵測到排程頁內容），請檢查後重新執行")

    # AI tab 確認開啟：點複製 → 等彈窗 → Alt+A 允許 → Enter 關確認框 → 讀剪貼簿
    # 注意：Alt+A 與 Enter 之間不再呼叫 _activate_citrix()，避免重新聚焦視窗干擾彈窗焦點
    pyperclip.copy("")
    _activate_citrix()
    _click(copy_x, copy_y)
    time.sleep(2.0)                  # 等「允許存取剪貼簿？」彈窗出現
    pyautogui.hotkey("alt", "a")     # 允許存取(A)
    time.sleep(1.5)
    pyautogui.press("enter")         # 關「已複製到剪貼簿！」確定框
    time.sleep(3.0)                  # 等 Citrix 同步到 Mac 剪貼簿
    patient.ai_summary = (pyperclip.paste() or "").strip()
    print(f"\n    [AI] {len(patient.ai_summary)} 字", end="")

    # 關 AI tab，偵測是否回排程頁
    _activate_citrix()
    time.sleep(0.5)
    pyautogui.hotkey("ctrl", "w")
    if not _on_schedule(bounds):
        print(f"\n    [警告：關AI tab後未回排程頁]", end="")

    # ── B. 術前評估：點 G → 等 13s → 點檢視 → Ctrl+A+C 輪詢 → 關分頁 ──
    pyperclip.copy("")
    _activate_citrix()
    _click(gsv_x, gsv_y)
    _wait_for_page(13)
    _activate_citrix()
    _click(view_x, view_y)
    time.sleep(10)
    patient.preanesthesia_eval = _poll_clipboard(bounds, max_wait=60, min_len=50)
    print(f"\n    [評估] {len(patient.preanesthesia_eval)} 字", end="")
    _close_until_schedule(bounds, max_tabs=3)

    return patient


def extract_all_patients_in_view(patients: list[Patient]) -> list[Patient]:
    cal = _load_cal()

    if _need_schedule_cal(cal):
        print("\n排程表按鈕尚未校正，進入校正模式...")
        cal = calibrate_schedule_buttons()

    bounds = _bounds(cal)
    fields = cal["fields"]
    bx, by, bw, bh = bounds

    # 從校正計算行距與 G 按鈕相對 AI 的偏移
    row_delta_y = int(bh * (fields["row2_ai"]["ry"] - fields["row1_ai"]["ry"]))
    gsv_dx = int(bw * (fields["row1_gsv"]["rx"] - fields["row1_ai"]["rx"]))
    gsv_dy = int(bh * (fields["row1_gsv"]["ry"] - fields["row1_ai"]["ry"]))
    view_xy = _abs("eval_view_btn", cal, bounds)
    copy_xy = _abs("ai_copy_btn",   cal, bounds)

    total = len(patients)
    print(f"\n請確認 Citrix 全螢幕，排程表捲到頂端顯示第一位病人")
    print(f"請將滑鼠移到【第一位病人 {patients[0].name} 的 AI 按鈕】中央")
    input("對準後按 Enter（不要移動滑鼠）...")
    first_ai_x, first_ai_y = pyautogui.position()
    print(f"  AI 基準: ({first_ai_x}, {first_ai_y})  行距: {row_delta_y}px  G偏移: ({gsv_dx}, {gsv_dy})")

    print(f"\n5 秒後開始自動擷取，請勿移動滑鼠！")
    for i in range(5, 0, -1):
        print(f"  {i}...", end=" ", flush=True)
        time.sleep(1)
    print("開始！")

    for i, patient in enumerate(patients):
        ai_xy  = (first_ai_x,          first_ai_y + i * row_delta_y)
        gsv_xy = (first_ai_x + gsv_dx, first_ai_y + gsv_dy + i * row_delta_y)
        print(f"\n  [{i+1}/{total}] {patient.name}  AI:{ai_xy}  G:{gsv_xy}", end="", flush=True)
        try:
            _extract_one(patient, ai_xy, gsv_xy, view_xy, copy_xy, bounds)
            ai_ok = "✓" if len(patient.ai_summary) > 20 else "✗"
            ev_ok = "✓" if len(patient.preanesthesia_eval) > 20 else "✗"
            print(f"\n  → AI:{ai_ok}  評估:{ev_ok}")
        except AbortError as e:
            print(f"\n\n{'='*50}")
            print(f"程序中止：{e}")
            print(f"{'='*50}")
            raise
        except Exception as e:
            print(f"\n  → 失敗：{e}")

    return patients
