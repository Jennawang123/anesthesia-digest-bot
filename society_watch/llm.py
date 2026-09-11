"""無結構頁面（AIRWAY 的 Wix 站、TWECCM 首頁）共用的 Haiku 抽取。

只有 diff 出現新增行時才呼叫，沒新增就完全不呼叫，成本趨近於零。

來源代號、學會名稱、頁面網址一律由呼叫端傳進來，模組內不寫死任何一站：
寫死的話第二個來源的事件會掛上第一個來源的 source 與 url，
去重命名空間與通知分組全部錯位，而且看起來完全正常。
"""
import hashlib
import json
import os
import re

from anthropic import Anthropic

from .models import Event

MODEL = "claude-haiku-4-5"   # 完整 model id，不加日期後綴

# 單次送給模型的新增行上限。整頁被判為新增（改版、頁面搬家）時，
# 與其花錢送一大包進去、還可能被 max_tokens 截斷成半截 JSON，
# 不如當成異常拋出去告警——快照不會前進，人看過再說。
MAX_NEW_LINES = 60

class LLMResponseError(RuntimeError):
    """Haiku 回應無法解析，或新增量異常。

    刻意拋出而非回空 list：呼叫端（main.collect）的 except 會把它記成
    該來源失敗 → 送告警 → **不更新快照** → 下一輪重試。
    若改回空 list，「模型回垃圾」與「模型判定沒有活動」在呼叫端完全同形，
    快照照樣前進，那批公告就永久漏掉且無人知曉。
    """


PROMPT_TEMPLATE = """以下是{society}網站新增的內容片段。
請判斷其中包含哪些「活動、課程或工作坊」公告。

請只輸出 JSON 陣列，每個元素包含：
- title：活動名稱（字串）
- date_text：活動日期。**只取日期本身**，不要含時間、星期、時區，也不要含
  「時間：」這類標籤與 emoji。年份原樣照抄，不要在民國年與西元年之間換算。
  找不到就給空字串。
  例：「📅 時間：115年2月7日（星期六）08:30-12:30」→「115年2月7日」
  例：「🗓️ 上課時間： 2026年6月13日（六）10:00 - 11:00 (GMT+8)」→「2026年6月13日」
- is_event：是否為活動／課程／工作坊公告（布林值）。人事賀詞、得獎名單、宣傳影片請給 false。

不確定是不是活動時，一律給 is_event: true。

新增內容：
---
{content}
---
"""


def build_prompt(new_lines: list[str], society: str) -> str:
    return PROMPT_TEMPLATE.format(society=society, content="\n".join(new_lines))


def parse_response_checked(raw: str, source: str, url: str) -> tuple[list[Event], bool]:
    """回傳（事件清單, 是否成功解析出 JSON 陣列）。

    第二個值是關鍵：合法的空陣列與垃圾回應都會產出空清單，
    只有這裡分得出來，不能把這個資訊丟掉。
    """
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()

    start = text.find("[")
    if start == -1:
        return [], False
    try:
        # 用 raw_decode 而非貪婪 regex：模型若在陣列後又寫了含 [ ] 的散文，
        # 貪婪比對會抓到過寬的區間而整包解析失敗。
        items, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return [], False
    if not isinstance(items, list):
        return [], False

    events = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        events.append(Event(
            source=source,
            # 文字來源無站方 ID，只能用標題 hash。已知限制：主辦方改標題會重推。
            # hash 不含 source，但 Event.key 是 "{source}:{uid}"，
            # 兩個文字來源的去重命名空間仍然分得開。
            uid=hashlib.sha1(title.encode("utf-8")).hexdigest()[:12],
            title=title,
            date_text=str(item.get("date_text", "")).strip(),
            url=url,
            minor=not item.get("is_event", True),
        ))
    return events, True


def parse_response(raw: str, source: str, url: str) -> list[Event]:
    """薄包裝，維持「解析不出來回空 list」的既有契約。"""
    return parse_response_checked(raw, source, url)[0]


def classify(new_lines: list[str], source: str, society: str, url: str) -> list[Event]:
    """呼叫 Haiku 判斷新增段落。沒有新增行就不呼叫 API。

    source 是來源代號（進 Event.key 的去重命名空間），society 是給模型看的
    學會名稱，url 是事件要連去的頁面。三者都不可省略成預設值——
    少傳一個就會靜默套到另一站身上。
    """
    if not new_lines:
        return []
    if len(new_lines) > MAX_NEW_LINES:
        raise LLMResponseError(
            f"新增 {len(new_lines)} 行超過上限 {MAX_NEW_LINES}，疑似整頁改版"
        )

    client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": build_prompt(new_lines, society)}],
    )
    # 取第一個 text block，不假設 content[0] 就是文字
    # （日後若換成預設開 thinking 的模型，content[0] 會是 thinking block）
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")

    events, ok = parse_response_checked(text, source, url)
    if not ok:
        raise LLMResponseError("Haiku 回應無法解析為 JSON 陣列")
    return events
