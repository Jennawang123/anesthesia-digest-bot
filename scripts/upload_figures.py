#!/usr/bin/env python3
"""把抽好的圖上傳 Notion，插入目標 sub-page 的對應內文位置。

每張圖插在 manifest 指定的 target_section 小節末尾，讀筆記時圖就在旁邊。
沒指定小節的落回「二、圖表」區塊。只做插入，不刪除或改寫既有內容。
manifest 的 uploaded_block_id 作為防重複依據，可安全重跑。

用法：
    python3 scripts/upload_figures.py figures/ch28 [--dry-run]

需要 .env 內的 NOTION_TOKEN（internal integration，需 Read/Update/Insert 權限，
且目標頁面已分享給該 integration）。
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"
FIGURE_HEADING = "二、圖表"


def load_token():
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("NOTION_TOKEN="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return os.environ.get("NOTION_TOKEN")


def block_text(b):
    t = b["type"]
    return "".join(r["plain_text"] for r in b[t].get("rich_text", []))


def outline(blocks):
    """回傳 [(索引, 文字, 層級)] 的小節骨架。

    各章筆記寫小標的方式不一致：有的用 heading_3，有的直接用整行粗體的
    paragraph（Ch43 型）。整行粗體是乾淨的判別方式 —— 內文條列與臨床重點
    段落都不是粗體。粗體小標視為比 heading_3 更低一級。
    """
    out = []
    for i, b in enumerate(blocks):
        t = b["type"]
        if t.startswith("heading_"):
            out.append((i, block_text(b).strip(), int(t.split("_")[1])))
        elif t == "paragraph":
            rt = b["paragraph"]["rich_text"]
            if rt and all(r["annotations"]["bold"] for r in rt):
                out.append((i, block_text(b).strip(), 4))
    return out


def section_names(blocks):
    """可作為圖片歸屬對象的小節名稱（heading_3 與粗體小標）。"""
    return [text for _, text, lvl in outline(blocks) if lvl >= 3 and text]


class Notion:
    def __init__(self, token):
        self.h = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION}

    def _check(self, r, what):
        if not r.ok:
            raise RuntimeError(f"{what} 失敗 {r.status_code}: {r.text[:300]}")
        return r.json()

    def _retry(self, call, what):
        """整批跑幾百次呼叫時，逾時、SSL 中斷與 429 幾乎必然出現，
        一次失敗就中斷整章並不划算。call 每次重試都重新建立請求。"""
        delay = 2
        for attempt in range(5):
            try:
                r = call()
                if r.status_code in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"HTTP {r.status_code}")
                return self._check(r, what)
            except (requests.RequestException, RuntimeError) as e:
                if attempt == 4:
                    raise
                print(f"    （{what} 重試 {attempt + 1}/4：{str(e)[:60]}）",
                      flush=True)
                time.sleep(delay)
                delay *= 2

    def _get(self, url, what, **kw):
        return self._retry(
            lambda: requests.get(url, headers=self.h, timeout=60, **kw), what)

    def children(self, block_id):
        """列出 block 的子項，處理分頁。"""
        out, cursor = [], None
        while True:
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            data = self._get(f"{API}/blocks/{block_id}/children",
                             "列出 blocks", params=params)
            out += data["results"]
            if not data.get("has_more"):
                return out
            cursor = data["next_cursor"]

    def find_heading(self, page_id, text):
        """找指定標題 block；找不到回傳 None。"""
        for b in self.children(page_id):
            if not b["type"].startswith("heading_"):
                continue
            plain = "".join(r["plain_text"] for r in b[b["type"]]["rich_text"])
            if plain.strip() == text:
                return b["id"]
        return None

    def section_end(self, page_id, heading_text, blocks=None):
        """回傳該小節最後一個 block 的 id —— 圖要插在這之後，才會落在
        對應內文的末尾而不是下一節開頭。小節結束於同級或更高級的小標。"""
        if blocks is None:
            blocks = self.children(page_id)
        marks = outline(blocks)
        hit = next((m for m in marks if m[1] == heading_text), None)
        if hit is None:
            return None

        start, _, level = hit
        end = next((i for i, _, lvl in marks if i > start and lvl <= level),
                   len(blocks))
        return blocks[end - 1]["id"]

    def delete(self, block_id):
        self._check(requests.delete(f"{API}/blocks/{block_id}",
                                    headers=self.h, timeout=30), "刪除 block")

    def upload(self, path: Path):
        """Notion File Upload API 兩步：建立 upload → 送出檔案。"""
        created = self._retry(
            lambda: requests.post(
                f"{API}/file_uploads",
                headers={**self.h, "Content-Type": "application/json"},
                json={"filename": path.name, "content_type": "image/png"},
                timeout=60),
            "建立 file upload")

        def send():
            # 重試要重新開檔，用過的 file handle 已經讀到結尾
            with path.open("rb") as fh:
                return requests.post(
                    created["upload_url"], headers=self.h,
                    files={"file": (path.name, fh, "image/png")}, timeout=300)

        sent = self._retry(send, "上傳檔案")
        if sent.get("status") != "uploaded":
            raise RuntimeError(f"上傳狀態異常：{sent.get('status')}")
        return sent["id"]

    def insert_images(self, page_id, after_block_id, items):
        """在指定 block 之後插入 image blocks，一次送出以保留順序。"""
        children = [{
            "object": "block",
            "type": "image",
            "image": {
                "type": "file_upload",
                "file_upload": {"id": upload_id},
                "caption": [{"type": "text", "text": {"content": caption[:2000]}}],
            },
        } for upload_id, caption in items]

        body = {"children": children}
        if after_block_id:
            body["after"] = after_block_id
        self._retry(
            lambda: requests.patch(
                f"{API}/blocks/{page_id}/children",
                headers={**self.h, "Content-Type": "application/json"},
                json=body, timeout=120),
            "插入 image block")

        # PATCH 的回傳不只包含新建的 block，不能直接拿來當 id 來源。
        # 重新列出頁面，用圖說比對出實際的 block id。
        return self.image_ids_by_caption(page_id)

    def image_ids_by_caption(self, page_id):
        """回傳 {圖說: block_id}，用於確認插入結果。"""
        out = {}
        for b in self.children(page_id):
            if b["type"] != "image":
                continue
            cap = "".join(r["plain_text"] for r in b["image"].get("caption", []))
            out[cap] = b["id"]
        return out

    def add_heading(self, page_id, text):
        data = self._check(
            requests.patch(f"{API}/blocks/{page_id}/children",
                           headers={**self.h, "Content-Type": "application/json"},
                           json={"children": [{
                               "object": "block", "type": "heading_2",
                               "heading_2": {"rich_text": [
                                   {"type": "text", "text": {"content": text}}]},
                           }]}, timeout=60),
            "建立圖表標題")
        return data["results"][0]["id"]


def caption_for(fig):
    """圖說 = 原文 caption + 書本頁碼。"""
    page = f"（p. {fig['book_page']}）" if fig.get("book_page") else ""
    return f"{fig['caption']}{page}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("figures_dir")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    d = Path(args.figures_dir)
    manifest_path = d / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    todo = [f for f in manifest
            if f.get("include") and f.get("target_page_id")
            and not f.get("uploaded_block_id")]
    if not todo:
        print("沒有待上傳的圖（可能都上傳過了）。")
        return

    # 以 (sub-page, 歸屬小節) 分組。沒指定小節的落回「二、圖表」區塊。
    by_page = {}
    for f in todo:
        key = (f["target_page_id"], f.get("target_section") or FIGURE_HEADING)
        by_page.setdefault(key, []).append(f)

    print(f"待上傳 {len(todo)} 張，分佈於 {len(by_page)} 個位置：")
    for (pid, sect), figs in by_page.items():
        print(f"  {pid[:8]}… 「{sect}」← {', '.join('Fig ' + f['fig_id'] for f in figs)}")
    if args.dry_run:
        print("\n--dry-run，未實際寫入。")
        return

    token = load_token()
    if not token:
        sys.exit("找不到 NOTION_TOKEN（請寫進 .env）。")
    notion = Notion(token)

    for (pid, sect), figs in by_page.items():
        # 插在小節最後一個 block 之後，圖才會落在該段內文末尾。
        anchor = notion.section_end(pid, sect)
        if not anchor:
            if sect != FIGURE_HEADING:
                print(f"  ⚠ 找不到小節「{sect}」，改放「{FIGURE_HEADING}」區塊")
            anchor = notion.find_heading(pid, FIGURE_HEADING)
        if not anchor:
            print(f"  {pid[:8]}… 沒有「{FIGURE_HEADING}」區塊，建立一個")
            anchor = notion.add_heading(pid, FIGURE_HEADING)

        items = []
        for f in figs:
            print(f"  上傳 Fig {f['fig_id']} …", end=" ", flush=True)
            items.append((notion.upload(d / f["png"]), caption_for(f)))
            print("完成")

        by_caption = notion.insert_images(pid, anchor, items)
        done = 0
        for f in figs:
            bid = by_caption.get(caption_for(f))
            if bid:
                f["uploaded_block_id"] = bid
                done += 1
            else:
                print(f"  ⚠ Fig {f['fig_id']} 插入後找不到對應 block，請人工確認")
        # 每篇寫回一次，中途失敗也不會重複上傳已完成的部分
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  已插入 {done}/{len(figs)} 張到 {pid[:8]}…")

    print("完成。")


if __name__ == "__main__":
    main()
