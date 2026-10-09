"""Haiku 把一篇文章的標題與摘要抽成結構化促銷。

回傳 None＝模型判定「不是買點促銷」（正常結果，文章記為已看過）。
拋 ExtractError＝回應壞掉或數值不合理（異常，文章不記為已看過、隔天重試、送告警）。
這兩者絕不可合併。
"""
import json
import os
import re
from datetime import date

from anthropic import Anthropic

from society_watch.llm import MODEL

from .models import Article, Promo
from .sources import PROGRAMS

PROMPT_TEMPLATE = """你是飯店與航空點數促銷的資料抽取器。以下是一篇部落格文章的標題與摘要。

判斷它是否在報導「單一計畫的官方買點／買哩程促銷」——也就是會員直接付現金向該計畫
購買點數或哩程本身，並在促銷期間獲得加贈或折扣。只追蹤這些計畫（左邊是代號）：
{programs}

以下一律不算（回 is_promo=false）：
- 兌換獎勵票／獎勵住宿時少扣點數的特價（award sale、Global Getaways、Promo Rewards）
- 訂房的 Points & Cash 折扣、房價促銷、住宿加贈點數
- 信用卡開卡禮或審查文、轉點加贈、購物入口加碼
- 一次列出多則優惠的彙整文
- 不在上列清單的計畫
- 已經結束的促銷（截止日早於今天）

今天是 {today}，文章發布於 {published}。
標題：{title}
摘要：{summary}
內文開頭：{body}

只輸出一個 JSON 物件，不要任何其他文字。
不是 → {{"is_promo": false}}
是 → {{"is_promo": true, "program": "<上列代號，原樣照抄>", "kind": "bonus" 或 "discount",
"percent": <整數>, "stated_cpp": <數字或 null>, "end_date": "YYYY-MM-DD" 或 null, "up_to": true 或 false}}

欄位規則：
- kind：買點加贈（例 100% bonus）填 bonus；價格折扣（例 40% off）填 discount。
- percent：分級促銷取最高級距的數字。
- stated_cpp：文中寫明的每點／每哩成本，單位美分（"0.5 cents each" → 0.5）。沒寫就 null，不要自己算。
- end_date：促銷截止日。文中只寫月日時，以今天與發布日推斷年份。沒寫就 null。
- up_to：出現 "up to"、分級、targeted、「視帳號而定」任一情況填 true。"""


class ExtractError(RuntimeError):
    """模型回應無法解析，或抽出的數值不合理。"""


def build_prompt(article: Article, today: date) -> str:
    programs = "\n".join(f"- {code}：{p['label']}" for code, p in PROGRAMS.items())
    return PROMPT_TEMPLATE.format(
        programs=programs,
        today=today.isoformat(),
        published=article.published.isoformat() if article.published else "不明",
        title=article.title,
        summary=article.summary,
        body=article.body or "（無）",
    )


def _program(value) -> str:
    """把模型回的 program 對回代號。

    2026-10-09 dry-run 實測：Haiku 對 Alaska 那篇回的不是代號 ALASKA，
    整篇因此被當成壞回應。這裡容忍大小寫與「回了計畫名稱而非代號」，
    但必須恰好對到一個計畫，否則照舊拋例外。
    """
    text = str(value).strip()
    if text.upper() in PROGRAMS:
        return text.upper()
    low = text.lower()
    hits = [code for code, p in PROGRAMS.items()
            if p["label"].lower() in low or any(k in low for k in p["keywords"])]
    if len(hits) != 1:
        raise ExtractError("program 不在追蹤清單")
    return hits[0]


def _number(value, low: float, high: float, what: str) -> float:
    # bool 是 int 的子類別，要先排除，否則 true 會被當成 1
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExtractError(f"{what} 不是數字")
    if not low <= value <= high:
        raise ExtractError(f"{what} 超出合理範圍")
    return value


def parse_response(raw: str, article: Article, today: date) -> Promo | None:
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ExtractError("Haiku 回應不含 JSON")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ExtractError("Haiku 回應無法解析為 JSON") from e
    if not isinstance(data, dict) or not isinstance(data.get("is_promo"), bool):
        raise ExtractError("Haiku 回應缺少 is_promo")
    if not data["is_promo"]:
        return None

    program = _program(data.get("program"))
    if data.get("kind") not in ("bonus", "discount"):
        raise ExtractError("kind 不是 bonus 或 discount")
    percent = _number(data.get("percent"), 1, 300, "percent")
    if percent != int(percent):
        raise ExtractError("percent 不是整數")

    stated = data.get("stated_cpp")
    if stated is not None:
        stated = float(_number(stated, 0.1, 10, "stated_cpp"))

    end = data.get("end_date")
    if end is not None:
        try:
            end = date.fromisoformat(end)
        except (TypeError, ValueError) as e:
            raise ExtractError("end_date 格式錯誤") from e
        if end < today:
            raise ExtractError("end_date 早於今天")

    if not isinstance(data.get("up_to"), bool):
        raise ExtractError("up_to 不是布林值")

    return Promo(program=program, kind=data["kind"], percent=int(percent),
                 stated_cpp=stated, end_date=end, up_to=data["up_to"], url=article.url)


def extract(article: Article, today: date) -> Promo | None:
    client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": build_prompt(article, today)}],
    )
    # 取第一個 text block，不假設 content[0] 就是文字
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
    try:
        return parse_response(text, article, today)
    except ExtractError:
        # 原始回應只印在 log，不放進例外訊息（訊息是告警節流的鍵，必須穩定）
        print(f"    Haiku 原始回應：{text!r}")
        raise
