"""
台大麻醉術前資料自動整理
使用方式：
  python main.py            # 正常執行
  python main.py --calibrate # 重新校正座標
"""

import sys
import time
from portal_login import login, run_calibration
from schedule import navigate_to_schedule, set_date_and_room, parse_patient_list_from_clipboard
from patient_extractor import extract_all_patients_in_view
from claude_processor import summarize_all
from notes_creator import create_daily_note


def main():
    if "--calibrate" in sys.argv:
        run_calibration()
        return

    if "--recalibrate-schedule" in sys.argv:
        from patient_extractor import calibrate_schedule_buttons
        calibrate_schedule_buttons()
        return

    skip_login = "--skip-login" in sys.argv

    print("=" * 50)
    print("台大麻醉術前資料自動整理")
    print("=" * 50)

    if skip_login:
        print("\n（已跳過登入，從 Step 3 開始）")
        print("請確認 Citrix Viewer 已全螢幕，Portal 已登入")
        input("確認後按 Enter 繼續...")
    else:
        # Step 1: VDI 登入
        print("\n[Step 1] 開啟 VDI 並登入")
        print("請手動：")
        print("  1. 開啟 https://vdi.ntuh.gov.tw/logon/LogonPoint/index.html")
        print("  2. 輸入帳號密碼與 MoTP 驗證碼完成 VDI 登入")
        print("  3. 點擊 Ntuh-Portal_Edge，等待 Citrix Viewer 視窗開啟")
        print("  4. 將 Citrix Viewer 視窗【最大化/全螢幕】（重要！座標依全螢幕校正）")
        input("\nCitrix Viewer 已全螢幕開啟後按 Enter 繼續...")

        # Step 2: Portal 登入
        print("\n[Step 2] 自動登入 Portal（手術系統）...")
        login()
        time.sleep(2)

    # Step 3: 使用者手動篩選排程
    print("\n[Step 3] 請在 Citrix 手動操作：")
    print("  1. 點到「手術排程查詢」頁面")
    print("  2. 設定日期為【明天】")
    print("  3. 選擇你要的【開刀房號碼】")
    print("  4. 按搜尋，等病人清單出現")
    room = input("\n你查的是哪個開刀房號碼（例如 007，只用來命名記事）：").strip().zfill(3)
    input("  排程清單出現後按 Enter 繼續...")

    # Step 5: 解析病人清單
    print("\n[Step 5] 請複製排程表的病人清單...")
    patients = parse_patient_list_from_clipboard()
    print(f"解析到 {len(patients)} 位病人")

    if not patients:
        print("未解析到任何病人，請檢查複製內容格式。")
        sys.exit(1)

    for p in patients:
        print(f"  {p.room}-{p.seq} {p.name} {p.age}{p.gender} {p.diagnosis}")

    # Step 6: 逐一擷取 AI 摘要與術前評估
    print(f"\n[Step 6] 自動擷取每位病人資料（共 {len(patients)} 人）...")
    patients = extract_all_patients_in_view(patients)

    # Step 7: Claude API 整理
    print("\n[Step 7] Claude API 整理重點...")
    patients = summarize_all(patients)

    # Step 8: 建立 iCloud 記事
    print("\n[Step 8] 建立 iCloud 記事...")
    title = create_daily_note(room, patients)

    print(f"\n完成！已建立記事「{title}」，iPhone 將自動同步。")


if __name__ == "__main__":
    main()
