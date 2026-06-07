"""測試自動偵測 CAPTCHA 是否正確"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from portal_login import load_calibration, ocr_captcha

cal = load_calibration()
b = cal["window_bounds"]
bounds = (b["x"], b["y"], b["w"], b["h"])

text = ocr_captcha(bounds, cal)
print(f"OCR 結果：{text!r}")
print("自動偵測截圖已存至 /tmp/captcha_detected.png")
