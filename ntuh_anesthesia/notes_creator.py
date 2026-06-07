"""
建立 iCloud 記事（Apple Notes），自動同步到 iPhone
用暫存檔案傳入內容，避免 AppleScript 字串長度限制
"""

import subprocess
import tempfile
import os
from datetime import date, timedelta
from patient_extractor import Patient


def build_note_content(room: str, patients: list[Patient]) -> str:
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y/%m/%d")
    lines = [f"【{room}刀房】{tomorrow} 術前整理", ""]

    for i, p in enumerate(patients, 1):
        asa = f"ASA {p.asa_grade}" if p.asa_grade not in ("", "?") else "ASA ?"
        gender_zh = "男" if p.gender == "M" else "女"
        anest = f"  麻醉｜{p.anesthesiologist}" if p.anesthesiologist else ""

        lines.append("━" * 28)
        lines.append(f"{i}. {p.name}　{p.age}{gender_zh}　{asa}")
        lines.append(f"診斷｜{p.diagnosis}")
        if p.procedure:
            lines.append(f"術式｜{p.procedure}")
        lines.append(f"主治｜{p.attending}{anest}")
        lines.append("")
        lines.append("▶ 麻醉重點")

        if p.ai_summary and len(p.ai_summary) > 10:
            for l in p.ai_summary.strip().splitlines():
                lines.append(f"  {l}" if l.strip() else "")
        else:
            lines.append("  （AI 摘要與術前評估待取得）")

        lines.append("")

    return "\n".join(lines)


def create_note(title: str, content: str):
    # 寫入暫存檔避免 AppleScript 字串長度限制
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", encoding="utf-8", delete=False
    )
    tmp.write(content)
    tmp.flush()
    tmp.close()
    tmp_path = tmp.name

    safe_title = title.replace('"', '\\"').replace("\\", "\\\\")

    script = f'''
    set filePath to POSIX file "{tmp_path}"
    set noteBody to read filePath as «class utf8»
    set htmlBody to do shell script "echo " & quoted form of noteBody & " | sed 's/$/<br>/g'"
    tell application "Notes"
        tell account "iCloud"
            make new note with properties {{name:"{safe_title}", body:htmlBody}}
        end tell
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    os.unlink(tmp_path)

    if result.returncode != 0:
        # 備援：直接寫純文字
        plain_script = f'''
        set filePath to POSIX file "{tmp_path}_"
        '''
        # 備援：用 shorter AppleScript
        content_short = content[:8000]
        safe_body = content_short.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        backup_script = f'tell application "Notes" to tell account "iCloud" to make new note with properties {{name:"{safe_title}", body:"{safe_body}"}}'
        subprocess.run(["osascript", "-e", backup_script], capture_output=True)

    print(f"已建立 iCloud 記事：{title}")


def create_daily_note(room: str, patients: list[Patient]):
    tomorrow = (date.today() + timedelta(days=1)).strftime("%m/%d")
    title = f"【{room}刀房】{tomorrow} 術前整理"
    content = build_note_content(room, patients)
    create_note(title, content)
    return title
