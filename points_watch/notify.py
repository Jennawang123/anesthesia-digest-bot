"""四種 LINE 訊息的排版。純函式；實際推送用 society_watch.notify.push_line。"""
from datetime import date

from .models import Rated
from .sources import PROGRAMS

_ICON = {"green": "🟢", "yellow": "🟡"}
_ORDER = {"green": 0, "yellow": 1}


def _headline(program: str, kind: str, percent: int) -> str:
    info = PROGRAMS[program]
    verb = "買點" if info["unit"] == "點" else "買哩程"
    return f"{info['label']} {verb} {percent}% {'加贈' if kind == 'bonus' else '折扣'}"


def _md(d: date) -> str:
    return f"{d.month}/{d.day}"


def _format_one(r: Rated) -> str:
    p = r.promo
    unit = PROGRAMS[p.program]["unit"]
    if r.new_low:
        compare = f"🏆 新低，原最佳 {r.best_cpp:.2f}¢"
    elif r.cpp <= r.best_cpp:
        compare = "平歷史最佳"
    else:
        gap = round((r.cpp / r.best_cpp - 1) * 100)
        compare = f"歷史最佳 {r.best_cpp:.2f}¢，貴 {gap}%"

    price = f"每{unit} {r.cpp:.2f}¢（{compare}）"
    if r.new_low and p.up_to:
        # 分級／限定對象的新低不是人人拿得到，價格也是用最高級距算的，
        # 寫成既成事實會誤導（2026-10-09 Alaska 120% 那則）。
        price = f"若拿到最高級距為每{unit} {r.cpp:.2f}¢（🏆 低於原最佳 {r.best_cpp:.2f}¢）"
    lines = [f"{_ICON[r.grade]} {_headline(p.program, p.kind, p.percent)}", price]
    if r.from_article:
        lines.append("（依文章報價）")
    if p.up_to:
        lines.append("⚠️ 最高可達，需登入確認個人優惠")
    lines.append(f"截止 {_md(p.end_date)}" if p.end_date else "截止日未註明")
    lines.append(p.url)
    return "\n".join(lines)


def format_promos(rated: list[Rated]) -> str:
    """只接受 green／yellow；red 由呼叫端先濾掉。"""
    ordered = sorted(rated, key=lambda r: _ORDER[r.grade])   # sorted 是穩定排序
    return "💰 點數促銷\n\n" + "\n\n".join(_format_one(r) for r in ordered)


def format_reminder(entries: list[dict], today: date) -> str:
    blocks = []
    for e in entries:
        end = date.fromisoformat(e["end_date"])
        left = (end - today).days
        unit = PROGRAMS[e["program"]]["unit"]
        when = "今天截止" if left == 0 else f"剩 {left} 天"
        blocks.append("\n".join([
            f"🟢 {_headline(e['program'], e['kind'], e['percent'])}",
            f"每{unit} {e['cpp']:.2f}¢｜{_md(end)} 截止（{when}）",
            e["url"],
        ]))
    return "⏰ 促銷即將截止\n\n" + "\n\n".join(blocks)


def format_alert(failures: list[tuple[str, str]]) -> str:
    lines = ["⚠️ 點數促銷監測異常", ""]
    lines.extend(f"・{source}：{reason}" for source, reason in failures)
    return "\n".join(lines)


def format_heartbeat(feed_count: int, article_count: int, promo_count: int,
                     cub_listed: int | None = None, cub_matched: int | None = None) -> str:
    lines = [
        "💓 點數促銷監測運作正常",
        "",
        f"・監測來源：{feed_count} 個 RSS",
        f"・已判讀文章：{article_count} 篇",
        f"・已記錄促銷：{promo_count} 筆",
    ]
    if cub_listed is not None:
        # 初篩命中數長期為 0 是唯一看得出「銀行改了措辭、初篩漏掉」的地方
        lines.append(f"・國泰世華：清單 {cub_listed} 筆、初篩命中 {cub_matched} 筆")
    lines.extend([
        "",
        "（每週一則。若某一週沒收到，表示監測可能已停擺，請查看 GitHub Actions。）",
    ])
    return "\n".join(lines)
