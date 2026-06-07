"""
手術排程導航模組
登入後導航至手術排程查詢，篩選日期與開刀房，解析病人清單
"""

import time
import re
import subprocess
import pyautogui
import pyperclip

pyautogui.FAILSAFE = False
from datetime import date, timedelta

from portal_login import get_citrix_window_bounds, abs_pos, load_calibration
from patient_extractor import Patient  # noqa: F401

pyautogui.PAUSE = 0.4


def get_tomorrow_str():
    tomorrow = date.today() + timedelta(days=1)
    return tomorrow.strftime("%Y/%m/%d")


def navigate_to_schedule():
    """
    從手術系統主選單點入手術排程查詢
    需要校正：手術排程查詢的選單位置
    """
    cal = load_calibration()
    bounds = get_citrix_window_bounds()
    fields = cal.get("fields", {})

    if "schedule_menu" not in fields:
        print("\n=== 手術排程選單校正 ===")
        print("請確認已登入手術系統，畫面顯示主選單")
        input("請將滑鼠移到「手術排程查詢」選項並按 Enter：")
        mx, my = pyautogui.position()
        rx = (mx - bounds[0]) / bounds[2]
        ry = (my - bounds[1]) / bounds[3]
        fields["schedule_menu"] = {"rx": rx, "ry": ry}

        import json, os
        from portal_login import CALIBRATION_FILE
        with open(CALIBRATION_FILE, "w") as f:
            json.dump(cal, f, ensure_ascii=False, indent=2)
        print("已儲存選單座標")

    f = fields["schedule_menu"]
    x, y = abs_pos(f["rx"], f["ry"], bounds)
    pyautogui.click(x, y)
    time.sleep(3)
    print("已進入手術排程查詢")


def set_date_and_room(room_number: str):
    """
    設定查詢日期（明天）與開刀房號，並執行搜尋
    需要校正：日期欄、開刀房下拉、搜尋按鈕
    """
    cal = load_calibration()
    bounds = get_citrix_window_bounds()
    fields = cal.get("fields", {})

    needed = ["date_start_field", "room_dropdown", "search_button"]
    if not all(k in fields for k in needed):
        print("\n=== 手術排程篩選欄位校正 ===")
        print("請確認畫面顯示手術排程查詢頁面")

        prompts = [
            ("date_start_field", "請移到「查詢開始日期」欄位並按 Enter"),
            ("room_dropdown", "請移到「手術房間」下拉選單並按 Enter"),
            ("search_button", "請移到搜尋（放大鏡）按鈕並按 Enter"),
        ]
        for key, prompt in prompts:
            input(f"\n{prompt}：")
            mx, my = pyautogui.position()
            rx = (mx - bounds[0]) / bounds[2]
            ry = (my - bounds[1]) / bounds[3]
            fields[key] = {"rx": rx, "ry": ry}
            print(f"  已記錄 {key}")

        import json
        from portal_login import CALIBRATION_FILE
        with open(CALIBRATION_FILE, "w") as f:
            json.dump(cal, f, ensure_ascii=False, indent=2)

    def click(key):
        fld = fields[key]
        x, y = abs_pos(fld["rx"], fld["ry"], bounds)
        pyautogui.click(x, y)
        time.sleep(0.4)

    tomorrow = get_tomorrow_str()

    # 設定開始與結束日期
    click("date_start_field")
    pyautogui.hotkey("ctrl", "a")
    pyautogui.typewrite(tomorrow, interval=0.05)
    time.sleep(0.3)

    # 開刀房：點下拉後輸入房號
    click("room_dropdown")
    time.sleep(0.5)
    pyautogui.typewrite(str(room_number), interval=0.08)
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(0.5)

    click("search_button")
    time.sleep(3)
    print(f"已搜尋 {tomorrow} 開刀房 {room_number}")


def parse_patient_list_from_clipboard() -> list[Patient]:
    """
    讓使用者在排程頁全選複製，解析病人清單
    """
    print("\n請在排程表全選（Ctrl+A）並複製（Ctrl+C），完成後按 Enter...")
    input()
    text = pyperclip.paste()

    # 除錯：印出前 800 字元讓開發者確認格式
    print("\n--- 複製到的內容（前800字）---")
    print(repr(text[:800]))
    print("---")

    return _parse_schedule_text(text)


def _parse_schedule_text(text: str) -> list[Patient]:
    """
    解析從排程表複製的純文字。
    每位病人跨兩行：
      行1：...  MM/DD   RRR SS 姓名 病房 病歷號
      行2：  [MF] age 診斷  術式  主治醫師 ...
    """
    patients = []
    lines = text.splitlines()

    i = 0
    while i < len(lines):
        line = lines[i]

        # 找含日期 + 房號 + 序號 + 姓名 + 病歷號的行
        m1 = re.search(
            r'(\d{2}/\d{2})\s+(\d{3})\s+(\d{2})\s+(\S+)\s+\S+\s+(\d{5,8})',
            line
        )
        if m1:
            date  = m1.group(1)
            room  = m1.group(2)
            seq   = m1.group(3)
            name  = m1.group(4)
            mrn   = m1.group(5)

            gender = age = diagnosis = procedure = attending = ""

            # 找下一個非空行作為第二行
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines):
                line2 = lines[j]
                m2 = re.match(r'\s*([MF])\s+(\d+y\d+m)\s+(.*)', line2)
                if m2:
                    gender = m2.group(1)
                    age    = m2.group(2)
                    rest   = m2.group(3).strip()

                    # 欄位以 2+ 空白分隔：
                    # parts[0] = 診斷（＋術式，單空白相連）
                    # parts[1] = 主治醫師 + G/S/V AI 按鈕文字
                    # parts[2] = 麻醉醫師
                    parts = re.split(r'\s{2,}', rest)
                    diag_proc_raw = parts[0].strip() if len(parts) > 0 else ""
                    attending_raw = parts[1].strip() if len(parts) > 1 else ""
                    anesthesiologist = re.sub(r'\s*(G|S|V)同.*', '', parts[2].strip()).strip() if len(parts) > 2 else ""

                    # 主治醫師：去掉後方的 G/S/V 按鈕文字
                    attending = re.sub(r'\s*(G|S|V)同.*', '', attending_raw).strip()

                    # 診斷與術式：以第一個中文字元為分界
                    zh_match = re.search(r'[一-鿿（(]', diag_proc_raw)
                    if zh_match and zh_match.start() > 0:
                        diagnosis = diag_proc_raw[:zh_match.start()].strip()
                        procedure = diag_proc_raw[zh_match.start():].strip()
                    else:
                        diagnosis = diag_proc_raw
                        procedure = ""

                    i = j  # 跳過已消耗的第二行

            patients.append(Patient(
                room=room, seq=seq, name=name, mrn=mrn,
                gender=gender, age=age,
                diagnosis=diagnosis, procedure=procedure,
                attending=attending,
                anesthesiologist=anesthesiologist,
            ))

        i += 1

    return patients
