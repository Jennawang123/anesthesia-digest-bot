"""
Claude API 整理每位病人的資料，產生麻醉重點摘要
"""

import anthropic
from config import ANTHROPIC_API_KEY
from patient_extractor import Patient

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """你是一位資深麻醉科主治醫師，正在幫住院醫師整理隔天手術病人的術前資訊。

請根據提供的 AI 病歷摘要與術前評估，用繁體中文輸出麻醉重點。

格式規則（嚴格遵守）：
- 純文字，禁止 markdown（禁止 ##、**、*、---）
- 依序輸出三個區塊，每塊之間空一行：

🔴 警示（每條一行，最多 4 條）
  → 過敏史、重大麻醉事件、困難插管史、高風險藥物
  → 若無則寫「🔴 無已知警示」

🟡 注意（每條一行，最多 6 條，每條 ≤25 字）
  → ASA 分級、重要共病、異常檢驗值、氣道評估、特殊用藥

⚪ 麻醉計畫（每條一行，最多 4 條）
  → 插管方式、監測、備血、術後疼痛

- 每條不超過 25 字，只寫關鍵數值與結論，不解釋原因
- 資料缺乏時直接寫「術前評估未填」，不要猜測或展開說明
"""


def summarize_patient(patient: Patient) -> str:
    user_content = f"""病人：{patient.name}，{patient.age}，{patient.gender}
病歷號：{patient.mrn}
手術：{patient.procedure}（{patient.diagnosis}）
主治醫師：{patient.attending}

=== AI 病歷摘要 ===
{patient.ai_summary or '（無資料）'}

=== 麻醉術前評估 ===
{patient.preanesthesia_eval or '（無資料）'}
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text


def summarize_all(patients: list[Patient]) -> list[Patient]:
    for i, p in enumerate(patients):
        print(f"  Claude 整理 [{i+1}/{len(patients)}] {p.name}...")
        try:
            p.asa_grade = _extract_asa(p.preanesthesia_eval)
            summary = summarize_patient(p)
            # 把 Claude 摘要附加到 ai_summary 欄位後方
            p.ai_summary = summary
        except Exception as e:
            p.ai_summary = f"[Claude API 失敗: {e}]"
    return patients


def _extract_asa(text: str) -> str:
    import re
    m = re.search(r"ASA\s*(\d)", text or "")
    return m.group(1) if m else "?"
