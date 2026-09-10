"""學會活動的最小資料結構。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    """一則學會活動或公告。

    date_text 刻意保持各站原樣字串不做正規化：五站格式各異
    （民國年 115/11/08、ISO 2026-08-26、中文 2026 八月 23），
    系統既不排序也不比較日期，只原樣顯示，不轉換就不會轉錯。
    """

    source: str      # 來源代號：TSA / TSCVA / RAPM / PAIN / AIRWAY
    uid: str         # 站方穩定 ID（AIRWAY 例外，為標題 hash）
    title: str
    date_text: str
    url: str
    kind: str | None = None    # 站方分類
    place: str | None = None   # 活動地點，僅 TSA 有
    minor: bool = False        # True = 降級到通知的「其他公告」區

    @property
    def key(self) -> str:
        """去重用的唯一鍵。"""
        return f"{self.source}:{self.uid}"
