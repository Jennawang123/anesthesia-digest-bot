"""截取整個 Citrix 視窗並標示目前校正到的驗證碼區域"""
import json, os
import pyautogui
from PIL import ImageDraw

CALIBRATION_FILE = os.path.join(os.path.dirname(__file__), "calibration.json")
with open(CALIBRATION_FILE) as f:
    cal = json.load(f)

b = cal["window_bounds"]
bx, by, bw, bh = b["x"], b["y"], b["w"], b["h"]

# 截整個視窗
shot = pyautogui.screenshot(region=(bx, by, bw, bh))

# 畫出目前驗證碼校正區域（紅框）
fields = cal["fields"]
tl = fields["captcha_image_tl"]
br = fields["captcha_image_br"]
x1 = int(bw * tl["rx"]); y1 = int(bh * tl["ry"])
x2 = int(bw * br["rx"]); y2 = int(bh * br["ry"])

draw = ImageDraw.Draw(shot)
draw.rectangle([x1, y1, x2, y2], outline="red", width=3)

shot.save("/tmp/citrix_window.png")
print(f"視窗大小：{bw}x{bh}")
print(f"紅框（目前驗證碼範圍）：({x1},{y1}) → ({x2},{y2})")
print("已存至 /tmp/citrix_window.png")
