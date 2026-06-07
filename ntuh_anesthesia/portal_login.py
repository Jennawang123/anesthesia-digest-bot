"""
Portal 登入模組
在 Citrix Viewer 視窗內自動填入帳號/密碼/CAPTCHA，選手術系統登入
"""

import time
import json
import os
import pyautogui
import pyperclip
from PIL import Image, ImageFilter, ImageEnhance
import pytesseract
import subprocess

from config import PORTAL_ACCOUNT, PORTAL_PASSWORD

CALIBRATION_FILE = os.path.join(os.path.dirname(__file__), "calibration.json")

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.4


def get_citrix_window_bounds():
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
            x, y, w, h = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
            print(f"  [Citrix 視窗] x={x}, y={y}, w={w}, h={h}")
            return x, y, w, h
        except Exception:
            pass
    # fallback：讀校正檔
    cal = load_calibration()
    if cal and "window_bounds" in cal:
        b = cal["window_bounds"]
        return b["x"], b["y"], b["w"], b["h"]
    raise RuntimeError("尚未校正，請先執行 --calibrate")


def calibrate_window_bounds():
    """讓使用者點擊 Citrix 視窗的左上角與右下角來確定視窗範圍"""
    print("\n請將 Citrix Viewer 視窗移到你習慣的位置（建議全螢幕或固定大小）")
    print("接下來請依指示將滑鼠移到指定位置後按 Enter")
    input("\n請將滑鼠移到 Citrix Viewer 視窗的【左上角】後按 Enter：")
    x1, y1 = pyautogui.position()
    input("請將滑鼠移到 Citrix Viewer 視窗的【右下角】後按 Enter：")
    x2, y2 = pyautogui.position()
    bounds = {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1}
    print(f"視窗範圍：{bounds}")
    return bounds


def abs_pos(rel_x_ratio, rel_y_ratio, bounds):
    """將視窗內相對比例座標轉為螢幕絕對座標"""
    x, y, w, h = bounds
    return x + int(w * rel_x_ratio), y + int(h * rel_y_ratio)


def load_calibration():
    if os.path.exists(CALIBRATION_FILE):
        with open(CALIBRATION_FILE) as f:
            return json.load(f)
    return None


def save_calibration(data):
    with open(CALIBRATION_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_calibration():
    """
    互動式校正：讓使用者點擊各欄位，記錄座標比例。
    只需執行一次。
    """
    print("=== 座標校正模式 ===")
    print("請確認 Citrix Viewer 已開啟並顯示 Portal 登入頁面")
    input("準備好後按 Enter...")

    window_bounds = calibrate_window_bounds()
    bounds = (window_bounds["x"], window_bounds["y"], window_bounds["w"], window_bounds["h"])
    print(f"Citrix 視窗：x={bounds[0]}, y={bounds[1]}, w={bounds[2]}, h={bounds[3]}")

    fields = [
        ("account_field", "請將滑鼠移到「帳號」輸入框並按 Enter"),
        ("password_field", "請將滑鼠移到「密碼」輸入框並按 Enter"),
        ("captcha_field", "請將滑鼠移到「驗證碼」輸入框並按 Enter"),
        ("surgery_radio", "請將滑鼠移到「手術系統」Radio 按鈕並按 Enter"),
        ("login_button", "請將滑鼠移到「登入」按鈕並按 Enter"),
        ("captcha_image_tl", "請將滑鼠移到驗證碼圖片【左上角】並按 Enter"),
        ("captcha_image_br", "請將滑鼠移到驗證碼圖片【右下角】並按 Enter"),
    ]

    calibration = {"window_bounds": window_bounds, "window_w": bounds[2], "window_h": bounds[3], "fields": {}}

    for key, prompt in fields:
        input(f"\n{prompt}：")
        mx, my = pyautogui.position()
        rx = (mx - bounds[0]) / bounds[2]
        ry = (my - bounds[1]) / bounds[3]
        calibration["fields"][key] = {"rx": rx, "ry": ry}
        print(f"  已記錄 {key}: ({rx:.4f}, {ry:.4f})")

    save_calibration(calibration)
    print("\n校正完成，已儲存至 calibration.json")
    return calibration


def prompt_captcha():
    """用系統彈窗輸入 CAPTCHA，蓋過 Citrix 全螢幕不需切換視窗"""
    script = '''
    set r to display dialog "請看 Citrix 畫面，輸入驗證碼（藍底文字）：" ¬
        default answer "" ¬
        with title "台大麻醉 - 驗證碼" ¬
        buttons {"確認"} default button "確認"
    return text returned of r
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    # 備援：terminal 輸入
    print("\n  → 請輸入驗證碼：", end="", flush=True)
    return input().strip()


def login(max_captcha_retries=5):
    """執行 Portal 登入，失敗時自動重試 CAPTCHA"""
    cal = load_calibration()
    if cal is None:
        print("尚未校正，進入校正模式...")
        cal = run_calibration()

    bounds = get_citrix_window_bounds()

    def click(field):
        f = cal["fields"][field]
        x, y = abs_pos(f["rx"], f["ry"], bounds)
        pyautogui.click(x, y)
        time.sleep(0.3)

    def type_text(field, text):
        click(field)
        pyautogui.hotkey("ctrl", "a")
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")

    for attempt in range(1, max_captcha_retries + 1):
        print(f"登入嘗試 {attempt}/{max_captcha_retries}...")

        type_text("account_field", PORTAL_ACCOUNT)
        type_text("password_field", PORTAL_PASSWORD)

        captcha_text = prompt_captcha()

        type_text("captcha_field", captcha_text)
        click("surgery_radio")
        time.sleep(0.2)
        click("login_button")
        time.sleep(3)

        # 若頁面仍在登入頁（有驗證碼欄位），視為失敗
        # 否則視為成功
        check = pyautogui.screenshot(region=(bounds[0], bounds[1], bounds[2], bounds[3]))
        from PIL import ImageStat
        # 簡單判斷：登入成功後頁面顏色分布會不同
        # 直接讓使用者確認比較可靠
        print("  已送出登入，請確認 Citrix 畫面是否進入系統...")
        result = input("  登入成功了嗎？(y/n)：").strip().lower()
        if result == "y":
            print("  登入成功")
            return True

        print("  重試...")
        time.sleep(1)

    raise RuntimeError("登入失敗超過重試上限")


if __name__ == "__main__":
    import sys
    if "--calibrate" in sys.argv:
        run_calibration()
    else:
        login()
