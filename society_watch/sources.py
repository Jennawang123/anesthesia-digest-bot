"""監測來源設定表。全部經 2026-09-10 實抓驗證。"""
from datetime import date

# 疼痛醫學會的 AJAX fragment endpoint（從頁面 JS 的 $("#main_content").load(...) 挖出，
# 實測免 cookie、免 session 可直接抓）。非公開 API，改版風險高於其他四站。
PAIN_ENDPOINT = (
    "https://pain.org.tw/index.php/educlass_page/educlass_page1_content/33/1/8/0"
)

SOURCES = [
    {
        "source": "TSA",
        "label": "台灣麻醉醫學會",
        "url": "https://www.anesth.org.tw/events/index.asp",
        "parser": "tsa",
    },
    {
        "source": "TSCVA",
        "label": "心臟胸腔暨血管麻醉醫學會",
        # 用 /news 完整列表，不用首頁摘要（兩者 class 不同，詳見 extract.parse_tscva）
        "url": "https://congress.tscva.org.tw/news",
        "parser": "tscva",
    },
    {
        "source": "RAPM",
        "label": "區域麻醉暨疼痛醫學會",
        "url": "https://rapm.org.tw/news-list/2",
        "parser": "rapm",
        "kind": "學會活動",
    },
    {
        "source": "RAPM",
        "label": "區域麻醉暨疼痛醫學會",
        "url": "https://rapm.org.tw/news-list/5",
        "parser": "rapm",
        "kind": "友會活動",
    },
    {
        "source": "PAIN",
        "label": "台灣疼痛醫學會",
        # ⚠️ 這個 url 只是佔位：collect() 對 PAIN 走的是 pain_urls(today)，
        # 不讀這個欄位。若日後有人把 collect() 統一改成讀 cfg["url"]（很自然的
        # 簡化），PAIN 會靜默退回只抓當年，跨年防護消失。改之前先看 pain_urls。
        "url": PAIN_ENDPOINT,
        "parser": "pain",
    },
    {
        "source": "AIRWAY",
        "label": "台灣呼吸道處理醫學會",
        "url": "https://www.tsamairway.org.tw/最新資訊",
        "parser": "airway",
    },
]

# 通知訊息裡的分組順序與顯示名稱
LABELS = {s["source"]: s["label"] for s in SOURCES}


# 相對於當前年份要抓的年份位移。
# +1 是主要目的：該列表「年份 scoped」且預設只回當年，明年度活動一旦公告
#    不會出現在預設頁面，只抓當年會漏報。
# -1 補的是跨年單向死角：視窗只往前滑，12/31 當天執行之後才上架、掛在去年
#    年份下的項目，1/1 起就再也抓不到，那是永久漏報而非延遲。多一次 HTTP 而已。
PAIN_YEAR_OFFSETS = (-1, 0, 1)


def pain_urls(today: date) -> list[str]:
    """疼痛醫學會要抓去年／今年／明年三份，合併後由呼叫端去重。"""
    return [f"{PAIN_ENDPOINT}?yy={today.year + n}" for n in PAIN_YEAR_OFFSETS]
