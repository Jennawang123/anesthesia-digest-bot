"""RSS 來源、追蹤的計畫、標題關鍵字篩選。

關鍵字層只求「不漏」：寧可多放幾篇給 Haiku 判否（一篇不到一分錢），
也不要在這層把真促銷擋掉——被擋掉的不會有任何訊號。
"""
import re

# 主 feed 才抓得到。Loyalty Lobby 的 /tag/…/feed/ 與 ?s=…&feed=rss2
# 會被 Cloudflare 回 403（2026-10-09 實測）。
FEEDS = [
    {"name": "loyaltylobby", "url": "https://loyaltylobby.com/feed/"},
    {"name": "omaat", "url": "https://onemileatatime.com/feed/"},
    {"name": "frequentmiler", "url": "https://frequentmiler.com/feed/"},
]

# 每個 feed 預設抓幾頁。Loyalty Lobby 一頁只有 14 篇約兩天份，
# 只抓一頁的話 Actions 延遲或單日失敗就會漏文。
DEFAULT_PAGES = 2

PROGRAMS = {
    "IHG":        {"label": "IHG", "unit": "點", "keywords": ["ihg"]},
    "CHOICE":     {"label": "Choice", "unit": "點", "keywords": ["choice privileges", "choice points", "choice hotels"]},
    "LIFEMILES":  {"label": "LifeMiles", "unit": "哩", "keywords": ["lifemiles"]},
    "AEROPLAN":   {"label": "Aeroplan", "unit": "哩", "keywords": ["aeroplan"]},
    "UNITED":     {"label": "United", "unit": "哩", "keywords": ["mileageplus", "united miles", "united mileage"]},
    "ALASKA":     {"label": "Alaska", "unit": "哩", "keywords": ["alaska", "atmos"]},
    "AA":         {"label": "AAdvantage", "unit": "哩", "keywords": ["aadvantage", "american airlines miles", "american miles"]},
    "FLYINGBLUE": {"label": "Flying Blue", "unit": "哩", "keywords": ["flying blue"]},
    "VIRGIN":     {"label": "Virgin Atlantic", "unit": "哩", "keywords": ["virgin atlantic", "virgin points", "flying club"]},
}

# 刻意不含 sale：2026-10-09 dry-run 實測，「IHG 12% Off Points & Cash Sale」
# 與「Global Getaways Award Sale」都靠 sale 混進來，後者還被 Haiku 誤判成
# 買哩程 50% 折扣。這兩篇的摘要都沒有 buy／purchase，而四篇真的買點文都有。
_BUY = re.compile(r"\b(buy|buying|purchas\w*)\b", re.I)
# transfer：轉點加贈常同時出現計畫名與 bonus／sale，但不是買點
_SKIP = re.compile(r"\(expired\)|\btransfer\b", re.I)
_KEYWORDS = [k for p in PROGRAMS.values() for k in p["keywords"]]


def is_candidate(title: str, summary: str = "") -> bool:
    """是否值得送給 Haiku：標題命中計畫名、標題或摘要有購買字眼、標題不含排除字。"""
    if _SKIP.search(title) or not (_BUY.search(title) or _BUY.search(summary)):
        return False
    lowered = title.lower()
    return any(k in lowered for k in _KEYWORDS)


def feed_urls(feed: dict, pages: int) -> list[str]:
    return [feed["url"]] + [f"{feed['url']}?paged={n}" for n in range(2, pages + 1)]
