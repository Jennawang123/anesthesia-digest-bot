"""國泰世華轉點加碼的 LINE 訊息排版。純函式；夥伴一律是 cub_store 存的 dict。"""
from datetime import date

# 使用者原本想追的兩家：固定排最前、標 ⭐、給燈號。其餘夥伴只列事實不評等——
# 要評等就得假設小樹點一點值多少錢，那因人而異。
_STARRED = {"EVA": "長榮", "ASIAMILES": "亞洲萬里通"}
_STAR_ORDER = list(_STARRED)


def _lamp(percent: int) -> str:
    if percent >= 15:
        return "🟢 15% 以上"
    if percent >= 10:
        return "🟡 10–14%"
    return "⚪ 低於 10%"


def _md(text) -> str | None:
    try:
        d = date.fromisoformat(text or "")
    except (TypeError, ValueError):
        return None
    return f"{d.month}/{d.day}"


def _period(p: dict) -> str:
    start, end = _md(p.get("start")), _md(p.get("end"))
    if start and end:
        return f"{start}–{end}"
    if end:
        return f"至 {end}"
    if start:
        return f"{start} 起"
    return "期間未註明"


def _ordered(partners: list[dict]) -> list[dict]:
    def rank(p: dict):
        program = p.get("program")
        if program in _STARRED:
            return (0, _STAR_ORDER.index(program), 0)
        percent = p.get("percent")
        return (1, 0, -percent) if isinstance(percent, int) else (2, 0, 0)
    return sorted(partners, key=rank)    # 穩定排序：同分維持傳入順序


def _head(p: dict, with_lamp: bool) -> str:
    starred = p.get("program") in _STARRED
    line = f"{'⭐' if starred else '・'}{' ' if starred else ''}{p['name']}"
    percent = p.get("percent")
    if isinstance(percent, int):
        line += f"｜{percent}%"
        if starred and with_lamp:
            line += f"（{_lamp(percent)}）"
    return line


def _needs_bonus_line(p: dict) -> bool:
    # 「每次轉換加贈 30%」已經被標題行的「｜30%」說完了；
    # 「滿 1 萬里送 800」這種階梯式的才需要另起一行。
    percent = p.get("percent")
    return not (isinstance(percent, int) and f"{percent}%" in p["bonus"])


def _block(p: dict, with_lamp: bool, with_period: bool, with_cap: bool) -> list[str]:
    lines = [_head(p, with_lamp)]
    if _needs_bonus_line(p):
        lines.append(f"  {p['bonus']}")
    if with_period:
        lines.append(f"  {_period(p)}")
    if p.get("registration"):
        lines.append(f"  需登錄：{p['registration']}")
    if with_cap and p.get("cap"):
        lines.append(f"  上限：{p['cap']}")
    return lines


def format_campaign(title: str, url: str, partners: list[dict], updated: bool = False) -> str:
    lines = ["✈️ 國泰世華小樹點轉點加碼" + ("（內容更新）" if updated else ""), title, ""]
    for p in _ordered(partners):
        lines.extend(_block(p, with_lamp=True, with_period=True, with_cap=True))

    present = {p.get("program") for p in partners}
    missing = [label for code, label in _STARRED.items() if code not in present]
    lines.append("")
    if missing:
        lines.append(f"{'、'.join(missing)}：本次未參加")
    lines.append(url)
    return "\n".join(lines)


def format_reminder(title: str, url: str, end: date, partners: list[dict], today: date) -> str:
    left = (end - today).days
    when = "今天截止" if left == 0 else f"剩 {left} 天"
    lines = ["⏰ 國泰世華轉點加碼即將截止", f"{end.month}/{end.day} 截止（{when}）", ""]
    for p in _ordered(partners):
        lines.extend(_block(p, with_lamp=False, with_period=False, with_cap=False))
    lines.extend(["", url])
    return "\n".join(lines)
