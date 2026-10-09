"""Haiku 把國泰世華活動頁的內文抽成各夥伴的加贈內容。

回傳 None＝模型判定不是轉點加碼（正常，活動記為已判讀）。
拋 CubError＝回應壞掉或數值不合理（異常，不記為已判讀、隔天重試、送告警）。
"""
import json
import os
import re
from dataclasses import dataclass
from datetime import date

from anthropic import Anthropic

from society_watch.llm import MODEL

from .cub import Campaign, CubError

TEXT_MAX = 6000   # 2026 年的加碼頁約 3,000 字

PROMPT_TEMPLATE = """你是信用卡點數活動的資料抽取器。以下是國泰世華銀行一個活動頁的標題與內文。

判斷它是否為「小樹點(信用卡)轉換航空里程或飯店積分的限時加碼活動」——也就是在指定期間內轉換，
會比平常多拿到里程或積分。以下都不算（回 is_transfer_bonus=false）：
- 只列出常態兌換比率、沒有期間限定的額外加贈
- 刷卡消費回饋、累積消費加碼、抽獎、門票或行李運送優惠

今天是 {today}。
標題：{title}
內文：{text}

只輸出一個 JSON 物件，不要任何其他文字。
不是 → {{"is_transfer_bonus": false}}
是 → {{"is_transfer_bonus": true, "partners": [{{"name": "...", "bonus": "...", "percent": 0,
"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "registration": null, "cap": null}}]}}

每個有額外加贈的航空或飯店夥伴各一筆，欄位規則：
- name：頁面上的夥伴名稱，原文照抄（例「亞洲萬里通」「洲際優悅會」）。
- bonus：加贈內容，一句話，20 字以內（例「每次轉換加贈 30%」「滿 1 萬里送 800、滿 2 萬里送 1,600」）。
- percent：加贈百分比，整數。頁面寫百分比就照填；寫「滿 X 送 Y」時用 Y÷X×100 取整（滿 10,000 送 800 → 8）；無法換算填 null。
- start、end：該夥伴自己的加贈期間，只取日期不要時分；頁面沒寫填 null。
- registration：需要事先登錄時，寫出登錄期間與名額，一句話（例「10/28 16:00–10/30 23:59，限量 2,000 名」）；不需登錄填 null。
- cap：回饋上限，一句話（例「每正卡戶 1,600 里」）；寫明無上限或沒提到都填 null。
同一頁的抽獎活動不是夥伴，不要列。"""

_EVA = re.compile(r"長榮|\bEVA\b", re.I)
_ASIA = re.compile(r"亞洲萬里通|asia\s*miles", re.I)


@dataclass(frozen=True)
class Partner:
    name: str
    bonus: str
    percent: int | None
    start: date | None
    end: date | None
    registration: str | None
    cap: str | None

    @property
    def program(self) -> str | None:
        """長榮／亞萬／其他。由名稱判定，不問模型。"""
        if _EVA.search(self.name):
            return "EVA"
        if _ASIA.search(self.name):
            return "ASIAMILES"
        return None

    def as_dict(self) -> dict:
        return {
            "name": self.name, "program": self.program, "bonus": self.bonus,
            "percent": self.percent,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "registration": self.registration, "cap": self.cap,
        }


def build_prompt(campaign: Campaign, text: str, today: date) -> str:
    return PROMPT_TEMPLATE.format(
        today=today.isoformat(), title=campaign.title, text=text[:TEXT_MAX])


def _required(value, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CubError(f"加碼判讀：{what} 空白")
    return value.strip()


def _optional(value, what: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CubError(f"加碼判讀：{what} 不是文字")
    return value.strip() or None


def _day(value, what: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as e:
        raise CubError(f"加碼判讀：{what} 日期格式錯誤") from e


def _percent(value) -> int | None:
    if value is None:
        return None
    # bool 是 int 的子類別，要先排除
    if isinstance(value, bool) or not isinstance(value, int):
        raise CubError("加碼判讀：percent 不是整數")
    if not 1 <= value <= 300:
        raise CubError("加碼判讀：percent 超出合理範圍")
    return value


def _partner(item) -> Partner:
    if not isinstance(item, dict):
        raise CubError("加碼判讀：夥伴不是物件")
    start, end = _day(item.get("start"), "start"), _day(item.get("end"), "end")
    if start and end and end < start:
        raise CubError("加碼判讀：end 早於 start")
    return Partner(
        name=_required(item.get("name"), "name"),
        bonus=_required(item.get("bonus"), "bonus"),
        percent=_percent(item.get("percent")),
        start=start, end=end,
        registration=_optional(item.get("registration"), "registration"),
        cap=_optional(item.get("cap"), "cap"),
    )


def parse_response(raw: str) -> list[Partner] | None:
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise CubError("加碼判讀：Haiku 回應不含 JSON")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise CubError("加碼判讀：Haiku 回應無法解析為 JSON") from e
    if not isinstance(data, dict) or not isinstance(data.get("is_transfer_bonus"), bool):
        raise CubError("加碼判讀：缺少 is_transfer_bonus")
    if not data["is_transfer_bonus"]:
        return None
    partners = data.get("partners")
    if not isinstance(partners, list) or not partners:
        raise CubError("加碼判讀：partners 為空")
    return [_partner(item) for item in partners]


def extract(campaign: Campaign, text: str, today: date) -> list[Partner] | None:
    client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": build_prompt(campaign, text, today)}],
    )
    reply = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
    try:
        return parse_response(reply)
    except CubError:
        # 原始回應只印在 log，不放進例外訊息（訊息是告警節流鍵，必須穩定）
        print(f"    Haiku 原始回應：{reply!r}")
        raise
