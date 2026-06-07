"""debug: 擷取 CAPTCHA 區域並存檔，用來確認截圖是否正確"""
import json, os
import pyautogui
from PIL import ImageEnhance, ImageFilter

CALIBRATION_FILE = os.path.join(os.path.dirname(__file__), "calibration.json")

with open(CALIBRATION_FILE) as f:
    cal = json.load(f)

b = cal["window_bounds"]
bounds = (b["x"], b["y"], b["w"], b["h"])
fields = cal["fields"]

tl = fields["captcha_image_tl"]
br = fields["captcha_image_br"]

x1 = bounds[0] + int(bounds[2] * tl["rx"])
y1 = bounds[1] + int(bounds[3] * tl["ry"])
x2 = bounds[0] + int(bounds[2] * br["rx"])
y2 = bounds[1] + int(bounds[3] * br["ry"])

print(f"CAPTCHA 截圖區域: ({x1},{y1}) → ({x2},{y2})，大小 {x2-x1}x{y2-y1}")

# 截圖並存檔
shot = pyautogui.screenshot(region=(x1, y1, x2-x1, y2-y1))
shot.save("/tmp/captcha_raw.png")

# 加強對比後存檔
img = shot.convert("L")
img = ImageEnhance.Contrast(img).enhance(2.5)
img = img.filter(ImageFilter.SHARPEN)
img.save("/tmp/captcha_enhanced.png")

print("已存至 /tmp/captcha_raw.png 和 /tmp/captcha_enhanced.png")
print("請用以下指令查看：open /tmp/captcha_raw.png")
