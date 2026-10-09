"""國泰世華活動清單與活動頁的解析。純函式，不碰網路。

清單端點是活動專區的前端在載入時呼叫的，不是公開 API。改版時這裡的每個
失敗都必須是明確的例外——回空 list 會跟「今年沒辦活動」長得一樣。
"""
import html
import json
import re
from dataclasses import dataclass

LIST_URL = ("https://www.cathay-cube.com.tw/cathaybk/personal/event/overview/"
            "credit-card.model.list.json")
SITE = "https://www.cathay-cube.com.tw"
_CONTENT_PREFIX = "/content/cub-aem-cs/zh-tw"

MIN_PAGE_CHARS = 200
# 活動頁元件樹裡會放人看得到的文字的鍵名（2026-10-09 實測）
_TEXT_KEYS = ("text", "title", "content", "subTitle", "description")

# 初篩只求不漏：149 筆命中 3 筆，其中 1 筆是真的，其餘交給 Haiku 判否
_TOPIC = re.compile("里程|哩程|里數|哩數|積分")
_ACTION = re.compile("轉換|兌換|加碼|加贈")

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


class CubError(ValueError):
    """國泰世華這條線的資料異常。訊息會進告警與節流鍵，必須短而穩定。"""


@dataclass(frozen=True)
class Campaign:
    path: str       # campaignPath 原值
    url: str        # 公開網址
    title: str      # jcr:title
    blurb: str      # campaignTitle + campaignContent + subtitle
    modified: str   # cq:lastModified 原字串

    @property
    def key(self) -> str:
        """「判讀過」的鍵。含最後修改時間：銀行事後改了活動內容就會重新判讀。"""
        return f"{self.path}|{self.modified}"


def _clean(text: str) -> str:
    plain = html.unescape(_TAG.sub(" ", text)).replace("\xa0", " ")
    return _SPACE.sub(" ", plain).strip()


def public_url(path: str) -> str:
    if path.startswith(_CONTENT_PREFIX):
        path = path[len(_CONTENT_PREFIX):]
    if path.endswith(".html"):
        path = path[:-len(".html")]
    return SITE + path


def page_json_url(campaign: Campaign) -> str:
    return campaign.url + ".model.json"


def parse_list(text: str) -> list[Campaign]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise CubError("活動清單不是 JSON") from e
    items = data.get("campaigns") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise CubError("活動清單為空或結構改變")

    campaigns = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("campaignPath")
        props = item.get("campaignProps")
        if not isinstance(path, str) or not isinstance(props, dict):
            continue
        title = props.get("jcr:title")
        if not isinstance(title, str) or not title.strip():
            continue
        blurb = " ".join(
            _clean(props[k]) for k in ("campaignTitle", "campaignContent", "subtitle")
            if isinstance(props.get(k), str)
        )
        modified = props.get("cq:lastModified")
        campaigns.append(Campaign(
            path=path, url=public_url(path), title=_clean(title), blurb=blurb,
            modified=modified if isinstance(modified, str) else "",
        ))
    if not campaigns:
        raise CubError("活動清單結構改變")
    return campaigns


def is_candidate(campaign: Campaign) -> bool:
    blob = f"{campaign.title} {campaign.blurb}"
    return bool(_TOPIC.search(blob) and _ACTION.search(blob))


def _find_main(node):
    if isinstance(node, dict):
        if "cub-main" in str(node.get(":type", "")):
            return node
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        found = _find_main(child)
        if found is not None:
            return found
    return None


def _strings(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _TEXT_KEYS and isinstance(value, str):
                if value.strip():
                    yield _clean(value)
            else:
                yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def page_text(text: str) -> str:
    """活動頁的 .model.json → 內文純文字（依元件樹順序串接）。"""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise CubError("活動頁不是 JSON") from e
    main = _find_main(data)
    if main is None:
        raise CubError("活動頁找不到內文")
    plain = " ".join(s for s in _strings(main) if s)
    if len(plain) < MIN_PAGE_CHARS:
        raise CubError("活動頁內文過短")
    return plain
