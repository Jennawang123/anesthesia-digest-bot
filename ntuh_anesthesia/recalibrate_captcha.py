"""只重新校正驗證碼圖片的截圖範圍"""
import json, os
import pyautogui

CALIBRATION_FILE = os.path.join(os.path.dirname(__file__), "calibration.json")

with open(CALIBRATION_FILE) as f:
    cal = json.load(f)

b = cal["window_bounds"]
bounds = (b["x"], b["y"], b["w"], b["h"])

print("請確認 Citrix 顯示 Portal 登入頁（有驗證碼圖片）")
print("注意：要指的是顯示亂碼文字的【彩色圖片】，不是下面的輸入框\n")

input("請將滑鼠移到驗證碼【彩色圖片】的左上角，按 Enter：")
mx, my = pyautogui.position()
tl_rx = (mx - bounds[0]) / bounds[2]
tl_ry = (my - bounds[1]) / bounds[3]

input("請將滑鼠移到驗證碼【彩色圖片】的右下角，按 Enter：")
mx, my = pyautogui.position()
br_rx = (mx - bounds[0]) / bounds[2]
br_ry = (my - bounds[1]) / bounds[3]

cal["fields"]["captcha_image_tl"] = {"rx": tl_rx, "ry": tl_ry}
cal["fields"]["captcha_image_br"] = {"rx": br_rx, "ry": br_ry}

with open(CALIBRATION_FILE, "w") as f:
    json.dump(cal, f, ensure_ascii=False, indent=2)

print(f"\n已更新驗證碼座標：TL({tl_rx:.4f},{tl_ry:.4f}) BR({br_rx:.4f},{br_ry:.4f})")
print("完成後請執行 debug_captcha.py 確認截圖正確")
