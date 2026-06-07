"""截取登入表單右側區域，查看是否包含 CAPTCHA"""
import json, os
import pyautogui
import numpy as np

CALIBRATION_FILE = os.path.join(os.path.dirname(__file__), "calibration.json")
with open(CALIBRATION_FILE) as f:
    cal = json.load(f)

b = cal["window_bounds"]
bx, by, bw, bh = b["x"], b["y"], b["w"], b["h"]

# 擷取右半部登入表單區域
rx = int(bw * 0.50); ry = int(bh * 0.28)
rw = int(bw * 0.20); rh = int(bh * 0.20)
print(f"搜尋區域（螢幕絕對座標）: ({bx+rx},{by+ry}) 大小 {rw}x{rh}")

shot = pyautogui.screenshot(region=(bx + rx, by + ry, rw, rh))
shot.save("/tmp/region_check.png")

# 分析顏色
arr = np.array(shot)
r, g, b_ch = arr[:,:,0], arr[:,:,1], arr[:,:,2]
blue_mask = (b_ch.astype(int) - r.astype(int) > 30) & (b_ch > 100)
print(f"藍色像素數量: {blue_mask.sum()} / {arr.shape[0]*arr.shape[1]}")
print(f"B channel 平均: {b_ch.mean():.1f}, max: {b_ch.max()}")
print(f"R channel 平均: {r.mean():.1f}, max: {r.max()}")
print("已存至 /tmp/region_check.png")
