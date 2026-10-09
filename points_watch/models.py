"""點數促銷監測的資料結構。"""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Article:
    feed: str
    title: str
    url: str
    published: date | None
    summary: str

    @property
    def key(self) -> str:
        """「看過的文章」的鍵。

        必須含發布日：OMAAT 每個計畫共用一個固定網址，每次新促銷只改內容
        與 pubDate。只用 URL 的話，第一次之後就永遠被當成看過了。
        """
        return f"{self.url}|{self.published.isoformat() if self.published else ''}"


@dataclass(frozen=True)
class Promo:
    program: str            # sources.PROGRAMS 的代號
    kind: str               # "bonus"（加贈）| "discount"（折扣）
    percent: int            # 最高級距的百分比
    stated_cpp: float | None  # 文章寫的每點成本（美分）
    end_date: date | None
    up_to: bool             # 最高可達／分級／限定對象
    url: str

    @property
    def key(self) -> str:
        """「推過的促銷」的鍵。刻意不含 url 與 stated_cpp：
        同一促銷會被多家報導，也會以 last call 重發。"""
        end = self.end_date.isoformat() if self.end_date else ""
        return f"{self.program}|{self.kind}|{self.percent}|{end}"


@dataclass(frozen=True)
class Rated:
    promo: Promo
    cpp: float              # 採用的每點成本（美分，兩位小數）
    best_cpp: float         # 評等當下的歷史最佳
    grade: str              # "green" | "yellow" | "red"
    new_low: bool
    from_article: bool      # True＝採用文章報價而非公式計算值
