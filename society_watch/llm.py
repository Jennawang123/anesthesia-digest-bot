"""Airway（Wix 無結構站）專用的 Haiku 抽取。

只有 diff 出現新增行時才呼叫，沒新增就完全不呼叫，成本趨近於零。
"""
import hashlib
import json
import os
import re

from anthropic import Anthropic

from .extract import AIRWAY_URL
from .models import Event

MODEL = "claude-haiku-4-5-20251001"

PROMPT_TEMPLATE = """以下是台灣呼吸道處理醫學會網站「最新資訊」頁新增的內容片段。
請判斷其中包含哪些「活動、課程或工作坊」公告。

請只輸出 JSON 陣列，每個元素包含：
- title：活動名稱（字串）
- date_text：活動日期，原樣照抄不要換算民國年或西元年（找不到就給空字串）
- is_event：是否為活動／課程／工作坊公告（布林值）。人事賀詞、得獎名單、宣傳影片請給 false。

不確定是不是活動時，一律給 is_event: true。

新增內容：
---
{content}
---
"""


def build_prompt(new_lines: list[str]) -> str:
    return PROMPT_TEMPLATE.format(content="\n".join(new_lines))


def parse_response(raw: str) -> list[Event]:
    """把模型回應解析成 Event。解析不出來回空 list，不拋例外。"""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()

    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

    events = []
    for item in items:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        events.append(Event(
            source="AIRWAY",
            # 該站無站方 ID，只能用標題 hash。已知限制：主辦方改標題會重推。
            uid=hashlib.sha1(title.encode("utf-8")).hexdigest()[:12],
            title=title,
            date_text=str(item.get("date_text", "")).strip(),
            url=AIRWAY_URL,
            minor=not item.get("is_event", True),
        ))
    return events


def classify(new_lines: list[str]) -> list[Event]:
    """呼叫 Haiku 判斷新增段落。沒有新增行就不呼叫 API。"""
    if not new_lines:
        return []
    client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": build_prompt(new_lines)}],
    )
    return parse_response(resp.content[0].text)
