# HyRead HTML 筆記匯入按鍵 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓使用者在 `reading-notes-app` 前端直接上傳 HyRead 匯出的 HTML 檔案完成筆記匯入，取代目前手動跑 script 連正式環境資料庫的流程；同時修正解析邏輯，讓同一章節標題（`location`）底下的多筆劃線合併成一張卡片，而不是拆成多張。

**Architecture:** 後端 `reading-notes-server` 新增 `POST /notes/import/hyread` multipart 上傳端點，重用既有 `parse_hyread_html()`（修正為依 `location` 合併）與 `import_hyread_book()`（新增筆記去重），匯入後自動呼叫既有 `fetch_cover_url()` 補封面。前端 `reading-notes-app/index.html` 新增匯入按鍵，觸發檔案選取後用 `FormData` 上傳到新端點，顯示結果摘要並刷新列表。

**Tech Stack:** FastAPI + SQLAlchemy（Postgres/SQLite）、BeautifulSoup4、pytest + httpx（後端測試）；純 HTML/CSS/JS 前端。

---

## Task 1: `parse_hyread_html.py` 依 location 合併同章節劃線

**Files:**
- Modify: `reading-notes-server/scripts/parse_hyread_html.py`
- Test: `reading-notes-server/tests/test_parse_hyread_html.py`

- [ ] **Step 1: Write the failing test**

在 `reading-notes-server/tests/test_parse_hyread_html.py` 檔案末尾加入：

```python
def test_parse_hyread_html_merges_notes_with_same_location():
    from scripts.parse_hyread_html import parse_hyread_html

    html = """
    <div class='book-title'>測試書</div>
    <div class='book-data'>測試作者</div>
    <div class='note-container'>
      <div class='note-chapter'>時間財富的三大支柱</div>
      <div class='note-time'>2026/7/7 23:17</div>
      <div class='highlight-content-red'>理解、專注、掌控</div>
      <div class='note-text'></div>
    </div>
    <div class='note-container'>
      <div class='note-chapter'>時間財富的三大支柱</div>
      <div class='note-time'>2026/7/7 23:20</div>
      <div class='highlight-content-red'>集中專注力是指對真正重要的事物採取深度聚焦</div>
      <div class='note-text'></div>
    </div>
    <div class='note-container'>
      <div class='note-chapter'>關於時間</div>
      <div class='note-time'>2026/7/7 23:25</div>
      <div class='highlight-content-red'>這個洞察力是解決現代困境的基礎</div>
      <div class='note-text'></div>
    </div>
    """

    result = parse_hyread_html(html)

    assert len(result["notes"]) == 2

    first = result["notes"][0]
    assert first["location"] == "時間財富的三大支柱"
    assert first["content"] == "理解、專注、掌控\n\n集中專注力是指對真正重要的事物採取深度聚焦"
    assert first["highlighted_at"] == "2026-07-07T23:17:00"

    second = result["notes"][1]
    assert second["location"] == "關於時間"
    assert second["content"] == "這個洞察力是解決現代困境的基礎"
    assert second["highlighted_at"] == "2026-07-07T23:25:00"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "reading-notes-server" && python3 -m pytest tests/test_parse_hyread_html.py::test_parse_hyread_html_merges_notes_with_same_location -v`
Expected: FAIL — `assert 3 == 2`（目前每則劃線都是獨立卡片，尚未合併）

- [ ] **Step 3: 修改 `parse_hyread_html` 加入合併邏輯**

將 `reading-notes-server/scripts/parse_hyread_html.py` 整檔改為：

```python
from datetime import datetime

from bs4 import BeautifulSoup


def parse_hyread_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    title = soup.select_one(".book-title").get_text(strip=True)
    author = soup.select_one(".book-data").get_text(strip=True)
    cover_el = soup.select_one(".book-cover img")
    cover_url = cover_el["src"] if cover_el and cover_el.has_attr("src") else ""

    raw_notes = []
    for container in soup.select(".note-container"):
        chapter_el = container.select_one(".note-chapter")
        time_el = container.select_one(".note-time")
        highlight_el = container.select_one("[class^='highlight-content-']")
        note_text_el = container.select_one(".note-text")

        chapter = chapter_el.get_text(strip=True) if chapter_el else ""
        time_str = time_el.get_text(strip=True) if time_el else ""
        highlight_text = highlight_el.get_text(strip=True) if highlight_el else ""
        note_text = note_text_el.get_text(strip=True) if note_text_el else ""

        content = highlight_text
        if note_text:
            content = f"{highlight_text}\n\n{note_text}"

        raw_notes.append({
            "content": content,
            "location": chapter,
            "highlighted_at": _parse_time(time_str) if time_str else None,
        })

    notes = _merge_by_location(raw_notes)

    return {"title": title, "author": author, "cover_url": cover_url, "notes": notes}


def _merge_by_location(raw_notes: list) -> list:
    merged = []
    for note in raw_notes:
        if merged and merged[-1]["location"] == note["location"]:
            merged[-1]["content"] = f"{merged[-1]['content']}\n\n{note['content']}"
        else:
            merged.append(dict(note))
    return merged


def _parse_time(time_str: str) -> str:
    dt = datetime.strptime(time_str, "%Y/%m/%d %H:%M")
    return dt.isoformat()
```

`_merge_by_location` 依原始順序遍歷：相鄰筆記若 `location` 與前一則合併結果相同就串接 `content`（空行分隔），否則另開一則新的。合併後的 `highlighted_at` 保留該組第一筆的值（後續筆記不覆蓋）。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "reading-notes-server" && python3 -m pytest tests/test_parse_hyread_html.py -v`
Expected: PASS（含原本 `test_parse_hyread_html_extracts_book_and_notes`，因為該 fixture 裡兩則筆記 location 不同，不受合併邏輯影響）

- [ ] **Step 5: Commit**

```bash
cd "reading-notes-server"
git add scripts/parse_hyread_html.py tests/test_parse_hyread_html.py
git commit -m "fix: merge HyRead notes sharing the same chapter into one card"
```

---

## Task 2: `notes_db.py` 新增 `note_exists` 去重查詢

**Files:**
- Modify: `reading-notes-server/notes_db.py`
- Test: `reading-notes-server/tests/test_notes_db.py`

- [ ] **Step 1: Write the failing test**

在 `reading-notes-server/tests/test_notes_db.py` 檔案末尾加入：

```python
def test_note_exists_detects_exact_duplicate(notes_db):
    book_id = notes_db.insert_book(title="測試書")
    notes_db.insert_note(
        book_id=book_id, content="劃線內容", source="hyread",
        location="第一章", highlighted_at="2026-07-07T23:17:00",
    )

    assert notes_db.note_exists(book_id, "劃線內容", "2026-07-07T23:17:00") is True
    assert notes_db.note_exists(book_id, "不同內容", "2026-07-07T23:17:00") is False
    assert notes_db.note_exists(book_id, "劃線內容", "2026-07-08T00:00:00") is False


def test_note_exists_handles_null_highlighted_at(notes_db):
    book_id = notes_db.insert_book(title="測試書")
    notes_db.insert_note(book_id=book_id, content="沒有時間的筆記", source="manual", highlighted_at=None)

    assert notes_db.note_exists(book_id, "沒有時間的筆記", None) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "reading-notes-server" && python3 -m pytest tests/test_notes_db.py::test_note_exists_detects_exact_duplicate -v`
Expected: FAIL — `AttributeError: module 'notes_db' has no attribute 'note_exists'`

- [ ] **Step 3: 在 `notes_db.py` 加入 `note_exists`**

在 `reading-notes-server/notes_db.py` 的 `insert_note` 函式後面（`list_notes_by_book` 前面）加入：

```python
def note_exists(book_id: int, content: str, highlighted_at: Optional[str]) -> bool:
    with engine.begin() as conn:
        result = conn.execute(
            text("""SELECT COUNT(*) AS c FROM notes
                     WHERE book_id = :book_id AND content = :content
                     AND (highlighted_at = :highlighted_at
                          OR (highlighted_at IS NULL AND :highlighted_at IS NULL))"""),
            {"book_id": book_id, "content": content, "highlighted_at": highlighted_at},
        )
        return _rows(result)[0]["c"] > 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "reading-notes-server" && python3 -m pytest tests/test_notes_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd "reading-notes-server"
git add notes_db.py tests/test_notes_db.py
git commit -m "feat: add note_exists query for import deduplication"
```

---

## Task 3: `seed_import.import_hyread_book` 去重 + 回傳匯入統計

**Files:**
- Modify: `reading-notes-server/scripts/seed_import.py`
- Test: `reading-notes-server/tests/test_seed_import.py`

`import_hyread_book` 的回傳型別要從「單純 `book_id: int`」改成「統計資訊 `dict`」，因為之後 `POST /notes/import/hyread` 端點需要 `notes_imported` / `notes_skipped_duplicate` / `is_new_book` 才能組出回應摘要。這一步會同時更新既有 3 個測試對回傳值的使用方式。

- [ ] **Step 1: Write the failing test（新增去重案例）**

在 `reading-notes-server/tests/test_seed_import.py` 檔案末尾加入：

```python
def test_import_hyread_book_skips_duplicate_notes(notes_db):
    from scripts.seed_import import import_hyread_book

    parsed = {
        "title": "會重複匯入的書",
        "author": "",
        "notes": [
            {"content": "劃線甲", "location": "第一章", "highlighted_at": "2026-07-07T23:17:00"},
        ],
    }

    first_result = import_hyread_book(parsed)
    assert first_result["is_new_book"] is True
    assert first_result["notes_imported"] == 1
    assert first_result["notes_skipped_duplicate"] == 0

    second_result = import_hyread_book(parsed)
    assert second_result["is_new_book"] is False
    assert second_result["book_id"] == first_result["book_id"]
    assert second_result["notes_imported"] == 0
    assert second_result["notes_skipped_duplicate"] == 1

    notes = notes_db.list_notes_by_book(first_result["book_id"])
    assert len(notes) == 1
```

- [ ] **Step 2: 更新既有 3 個測試以配合新的回傳型別**

在同一檔案裡，把現有這 3 處對 `import_hyread_book` 回傳值的使用方式改掉：

```python
def test_import_hyread_book_creates_book_and_notes(notes_db):
    from scripts.seed_import import import_hyread_book

    parsed = {
        "title": "人生的五種財富",
        "author": "薩希. 布魯姆",
        "cover_url": "https://webcdn2.ebook.hyread.com.tw/bookcover/x.jpg",
        "notes": [
            {"content": "丟掉壞的記分板", "location": "人一生的旅程", "highlighted_at": "2026-07-07T23:17:00"},
        ],
    }

    result = import_hyread_book(parsed)
    book = notes_db.get_book(result["book_id"])
    assert book["title"] == "人生的五種財富"
    assert book["source_tag"] == "hyread"
    assert book["cover_url"] == "https://webcdn2.ebook.hyread.com.tw/bookcover/x.jpg"

    notes = notes_db.list_notes_by_book(result["book_id"])
    assert len(notes) == 1
    assert notes[0]["source"] == "hyread"
    assert notes[0]["location"] == "人一生的旅程"


def test_import_hyread_book_derives_started_and_finished_at_from_notes(notes_db):
    from scripts.seed_import import import_hyread_book

    parsed = {
        "title": "衝突的日常",
        "author": "作者",
        "notes": [
            {"content": "筆記一", "location": "第一章", "highlighted_at": "2026-07-07T23:17:00"},
            {"content": "筆記二", "location": "第二章", "highlighted_at": "2026-06-01T10:00:00"},
            {"content": "筆記三", "location": "第三章", "highlighted_at": "2026-07-20T08:30:00"},
            {"content": "筆記四", "location": "第四章", "highlighted_at": None},
        ],
    }

    result = import_hyread_book(parsed)
    book = notes_db.get_book(result["book_id"])
    assert book["started_at"] == "2026-06-01"
    assert book["finished_at"] == "2026-07-20"


def test_import_hyread_book_reuses_existing_book_by_title(notes_db):
    from scripts.seed_import import import_hyread_book

    parsed = {"title": "重複的書", "author": "", "notes": [{"content": "第一次", "location": "", "highlighted_at": None}]}
    result1 = import_hyread_book(parsed)

    parsed2 = {"title": "重複的書", "author": "", "notes": [{"content": "第二次", "location": "", "highlighted_at": None}]}
    result2 = import_hyread_book(parsed2)

    assert result1["book_id"] == result2["book_id"]
    assert result2["is_new_book"] is False
    assert len(notes_db.list_notes_by_book(result1["book_id"])) == 2
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd "reading-notes-server" && python3 -m pytest tests/test_seed_import.py -v`
Expected: FAIL — `TypeError: 'int' object is not subscriptable`（現有實作仍回傳 `int`）

- [ ] **Step 4: 修改 `import_hyread_book`**

把 `reading-notes-server/scripts/seed_import.py` 裡的 `import_hyread_book` 函式改為：

```python
def import_hyread_book(parsed: dict) -> dict:
    existing = db.find_book_by_title(parsed["title"])
    is_new_book = existing is None
    if existing:
        book_id = existing["id"]
    else:
        highlighted_ats = [
            note["highlighted_at"] for note in parsed["notes"] if note.get("highlighted_at")
        ]
        started_at = min(highlighted_ats).split("T")[0] if highlighted_ats else None
        finished_at = max(highlighted_ats).split("T")[0] if highlighted_ats else None
        book_id = db.insert_book(
            title=parsed["title"], author=parsed.get("author", ""), source_tag="hyread",
            started_at=started_at, finished_at=finished_at,
            cover_url=parsed.get("cover_url", ""),
        )

    notes_imported = 0
    notes_skipped_duplicate = 0
    for note in parsed["notes"]:
        if db.note_exists(book_id, note["content"], note.get("highlighted_at")):
            notes_skipped_duplicate += 1
            continue
        db.insert_note(
            book_id=book_id,
            content=note["content"],
            source="hyread",
            location=note.get("location", ""),
            highlighted_at=note.get("highlighted_at"),
        )
        notes_imported += 1

    return {
        "book_id": book_id,
        "is_new_book": is_new_book,
        "notes_imported": notes_imported,
        "notes_skipped_duplicate": notes_skipped_duplicate,
    }
```

`import_notion_seed` 保持不動。檔案最下面 `if __name__ == "__main__":` 區塊也保持不動（沒有使用 `import_hyread_book` 的回傳值，型別改變不影響它）。

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd "reading-notes-server" && python3 -m pytest tests/test_seed_import.py -v`
Expected: PASS（4 個測試全過）

- [ ] **Step 6: Commit**

```bash
cd "reading-notes-server"
git add scripts/seed_import.py tests/test_seed_import.py
git commit -m "feat: dedupe notes on hyread import and return import stats"
```

---

## Task 4: 後端匯入端點 `POST /notes/import/hyread`

**Files:**
- Modify: `reading-notes-server/requirements.txt`
- Modify: `reading-notes-server/notes_api.py`
- Test: `reading-notes-server/tests/test_notes_api.py`

FastAPI 要接收檔案上傳（`UploadFile`）需要 `python-multipart` 套件，目前 `requirements.txt` 沒有這個依賴。

- [ ] **Step 1: 加入 `python-multipart` 依賴並安裝**

把 `reading-notes-server/requirements.txt` 改為：

```
fastapi
uvicorn[standard]
sqlalchemy
psycopg2-binary
pytest
httpx
beautifulsoup4
certifi
python-multipart
```

Run: `cd "reading-notes-server" && python3 -m pip install -r requirements.txt`
Expected: 安裝成功（或顯示已滿足依賴）

- [ ] **Step 2: Write the failing tests**

在 `reading-notes-server/tests/test_notes_api.py` 檔案末尾加入：

```python
def test_import_hyread_creates_book_with_merged_notes(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    app = _fresh_app(tmp_path, monkeypatch)
    client = TestClient(app)

    html = """
    <div class='book-title'>時間財富</div>
    <div class='book-data'>作者</div>
    <div class='book-cover'><img src='https://example.com/existing-cover.jpg' /></div>
    <div class='note-container'>
      <div class='note-chapter'>時間財富的三大支柱</div>
      <div class='note-time'>2026/7/7 23:17</div>
      <div class='highlight-content-red'>理解、專注、掌控</div>
      <div class='note-text'></div>
    </div>
    <div class='note-container'>
      <div class='note-chapter'>時間財富的三大支柱</div>
      <div class='note-time'>2026/7/7 23:20</div>
      <div class='highlight-content-red'>集中專注力是指對真正重要的事物採取深度聚焦</div>
      <div class='note-text'></div>
    </div>
    """

    resp = client.post(
        "/notes/import/hyread",
        files={"file": ("notes.html", html, "text/html")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "時間財富"
    assert body["is_new_book"] is True
    assert body["notes_imported"] == 1
    assert body["notes_skipped_duplicate"] == 0
    assert body["cover_fetched"] is False

    detail = client.get(f"/notes/books/{body['book_id']}").json()
    assert len(detail["notes"]) == 1
    assert detail["notes"][0]["content"] == "理解、專注、掌控\n\n集中專注力是指對真正重要的事物採取深度聚焦"
    assert detail["cover_url"] == "https://example.com/existing-cover.jpg"


def test_import_hyread_rejects_non_hyread_html(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    app = _fresh_app(tmp_path, monkeypatch)
    client = TestClient(app)

    resp = client.post(
        "/notes/import/hyread",
        files={"file": ("notes.html", "<html><body>不是 HyRead 匯出檔</body></html>", "text/html")},
    )
    assert resp.status_code == 400
    assert "HyRead" in resp.json()["detail"]


def test_import_hyread_skips_duplicate_notes_on_reimport(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    app = _fresh_app(tmp_path, monkeypatch)
    client = TestClient(app)

    html = """
    <div class='book-title'>重複匯入書</div>
    <div class='book-data'>作者</div>
    <div class='note-container'>
      <div class='note-chapter'>第一章</div>
      <div class='note-time'>2026/7/7 23:17</div>
      <div class='highlight-content-red'>劃線內容</div>
      <div class='note-text'></div>
    </div>
    """

    client.post("/notes/import/hyread", files={"file": ("notes.html", html, "text/html")})
    resp = client.post("/notes/import/hyread", files={"file": ("notes.html", html, "text/html")})

    body = resp.json()
    assert body["is_new_book"] is False
    assert body["notes_imported"] == 0
    assert body["notes_skipped_duplicate"] == 1


def test_import_hyread_fetches_cover_when_missing(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    app = _fresh_app(tmp_path, monkeypatch)
    import notes_api
    monkeypatch.setattr(notes_api, "fetch_cover_url", lambda title, author="": "https://example.com/auto-cover.jpg")
    client = TestClient(app)

    html = """
    <div class='book-title'>沒有封面的書</div>
    <div class='book-data'>作者</div>
    <div class='note-container'>
      <div class='note-chapter'>第一章</div>
      <div class='note-time'>2026/7/7 23:17</div>
      <div class='highlight-content-red'>劃線內容</div>
      <div class='note-text'></div>
    </div>
    """

    resp = client.post("/notes/import/hyread", files={"file": ("notes.html", html, "text/html")})
    body = resp.json()
    assert body["cover_fetched"] is True

    detail = client.get(f"/notes/books/{body['book_id']}").json()
    assert detail["cover_url"] == "https://example.com/auto-cover.jpg"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd "reading-notes-server" && python3 -m pytest tests/test_notes_api.py -k import_hyread -v`
Expected: FAIL — `404 Not Found`（端點還不存在）

- [ ] **Step 4: 實作端點**

在 `reading-notes-server/notes_api.py` 開頭的 import 區塊，把：

```python
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

import notes_db as db
```

改為：

```python
from fastapi import APIRouter, HTTPException, Header, UploadFile, File
from pydantic import BaseModel

import notes_db as db
from scripts.fetch_book_cover import fetch_cover_url
from scripts.parse_hyread_html import parse_hyread_html
from scripts.seed_import import import_hyread_book
```

在檔案末尾（`search` 路由後面）加入：

```python
@router.post("/import/hyread")
async def import_hyread(file: UploadFile = File(...), x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    html = (await file.read()).decode("utf-8")

    try:
        parsed = parse_hyread_html(html)
    except AttributeError:
        raise HTTPException(status_code=400, detail="無法辨識此 HyRead HTML 格式，請確認是從 HyRead 匯出的劃線檔案")

    result = import_hyread_book(parsed)

    cover_fetched = False
    book = db.get_book(result["book_id"])
    if book and not book.get("cover_url"):
        try:
            cover_url = fetch_cover_url(book["title"], book.get("author", ""))
        except Exception:
            cover_url = None
        if cover_url:
            db.update_book(
                result["book_id"], title=book["title"], author=book.get("author", ""),
                category=book["category"], started_at=book.get("started_at"),
                finished_at=book.get("finished_at"), cover_url=cover_url,
                unfinished=book.get("unfinished", False),
            )
            cover_fetched = True

    return {
        "book_id": result["book_id"],
        "title": parsed["title"],
        "is_new_book": result["is_new_book"],
        "notes_imported": result["notes_imported"],
        "notes_skipped_duplicate": result["notes_skipped_duplicate"],
        "cover_fetched": cover_fetched,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd "reading-notes-server" && python3 -m pytest tests/test_notes_api.py -v`
Expected: PASS（全部案例，含既有的）

- [ ] **Step 6: Run 整個後端測試套件確認沒有其他地方壞掉**

Run: `cd "reading-notes-server" && python3 -m pytest -v`
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
cd "reading-notes-server"
git add requirements.txt notes_api.py tests/test_notes_api.py
git commit -m "feat: add POST /notes/import/hyread endpoint with auto cover fetch"
```

---

## Task 5: 前端匯入按鍵（`reading-notes-app/index.html`）

**Files:**
- Modify: `reading-notes-app/index.html`

- [ ] **Step 1: 加入按鍵與隱藏檔案輸入框的 CSS**

在 `reading-notes-app/index.html` 的 `<style>` 區塊裡，找到這一行：

```css
  #toggleAddBookBtn{background:var(--accent);color:#fff;border:none;padding:8px 14px;border-radius:6px;cursor:pointer;margin-bottom:16px}
```

在它後面加一行：

```css
  #importHyreadBtn{background:var(--accent);color:#fff;border:none;padding:8px 14px;border-radius:6px;cursor:pointer;margin-bottom:16px;margin-left:8px}
  #importHyreadBtn:disabled{opacity:0.6;cursor:default}
```

- [ ] **Step 2: 加入按鍵與檔案輸入框的 HTML**

找到這一行：

```html
  <button id="toggleAddBookBtn">+ 新增書籍</button>
```

改為：

```html
  <button id="toggleAddBookBtn">+ 新增書籍</button>
  <button id="importHyreadBtn">匯入 HyRead 筆記</button>
  <input type="file" id="importHyreadFile" accept=".html" style="display:none">
```

- [ ] **Step 3: 加入上傳邏輯的 JavaScript**

在 `<script>` 區塊末尾（`runSearch` 函式定義之後，`</script>` 之前）加入：

```javascript
const importHyreadBtn = document.getElementById('importHyreadBtn');
const importHyreadFile = document.getElementById('importHyreadFile');

importHyreadBtn.onclick = () => {
  importHyreadFile.click();
};

importHyreadFile.onchange = async () => {
  const file = importHyreadFile.files[0];
  if (!file) return;

  importHyreadBtn.disabled = true;
  importHyreadBtn.textContent = '匯入中...';

  try {
    const formData = new FormData();
    formData.append('file', file);
    const resp = await fetch(`${API}/notes/import/hyread`, {
      method: 'POST',
      headers: headers(),
      body: formData,
    });
    const body = await resp.json();
    if (!resp.ok) {
      alert(`匯入失敗：${body.detail || '未知錯誤'}`);
      return;
    }
    const coverMsg = body.cover_fetched ? '，已補上封面' : '';
    alert(`《${body.title}》匯入完成，新增 ${body.notes_imported} 則筆記，略過 ${body.notes_skipped_duplicate} 則重複${coverMsg}`);
    loadBooks();
  } catch (err) {
    alert('匯入失敗，請確認網路連線與後端網址設定');
    console.error('匯入 HyRead 筆記失敗', err);
  } finally {
    importHyreadBtn.disabled = false;
    importHyreadBtn.textContent = '匯入 HyRead 筆記';
    importHyreadFile.value = '';
  }
};
```

- [ ] **Step 4: 手動驗證（本機起後端 + 開瀏覽器測試上傳流程）**

Run（另開一個終端機視窗，啟動本機後端）：

```bash
cd "reading-notes-server" && DATA_DIR=/tmp/reading_notes_manual_test python3 -m uvicorn main:app --reload --port 8000
```

在瀏覽器打開 `reading-notes-app/index.html`（直接用檔案路徑開啟，或用任何本機靜態伺服器），在「後端 API 網址」欄位填入 `http://localhost:8000`，按「儲存」。

點擊「匯入 HyRead 筆記」按鍵，選取 `reading-notes-server/tests/fixtures/sample_hyread_export.html`。

Expected：
- 按鍵短暫顯示「匯入中...」後恢復
- 跳出 alert，內容類似「《人生的五種財富...》匯入完成，新增 2 則筆記，略過 0 則重複」
- 書籍列表出現新書籍卡片
- 點進書籍詳細頁，確認 2 則筆記內容正確

驗證完成後，可 `Ctrl+C` 關閉本機後端伺服器（`/tmp/reading_notes_manual_test` 是測試用資料庫，跟正式環境的 Render Postgres 無關，可留著或刪除）。

- [ ] **Step 5: Commit**

```bash
cd "reading-notes-app"
git add index.html
git commit -m "feat: add HyRead HTML note import button"
```

---

## Task 6: 部署

**Files:** 無新增檔案，此任務是操作步驟。

- [ ] **Step 1: 確認後端變更已推送，觸發 Render 自動部署**

Run: `cd "reading-notes-server" && git push`
Expected: push 成功；Render 後台會自動觸發重新部署（GitHub push 已設定自動部署）

- [ ] **Step 2: 手動部署前端到 Netlify**

依照既有慣例（見 `docs/superpowers/specs` 內對 Netlify 帳號的說明），手動把 `reading-notes-app` 資料夾拖拉到 Netlify 完成部署，因為目前前端沒有接 GitHub 自動部署。

- [ ] **Step 3: 在正式環境驗證一次**

在正式前端網址（`https://zingy-gingersnap-14bccb.netlify.app` 或使用者目前使用的網址）點擊「匯入 HyRead 筆記」，選取一份真實的 HyRead 匯出 HTML，確認匯入摘要與書籍詳細頁內容正確，且封面有自動補上（若原本沒有封面）。

---

## Self-Review Notes

- **Spec coverage**：同標題合併（Task 1）、去重（Task 2+3）、匯入端點含封面自動補齊（Task 4）、前端按鍵與摘要顯示（Task 5）、錯誤處理 400（Task 4 test）、測試範圍（貫穿 Task 1-4）均已對應到任務。
- **範圍邊界**：Task 1 的合併邏輯不回頭處理資料庫既有資料（沿用 spec 決定），未寫任何清理舊資料的 script。
- **型別一致性**：`import_hyread_book` 從回傳 `int` 改為回傳 `dict`，Task 3 已同步更新該檔案內全部既有測試與呼叫點；`notes_api.py` 呼叫處與新測試的欄位命名（`book_id` / `is_new_book` / `notes_imported` / `notes_skipped_duplicate`）在 Task 3、4 之間保持一致。
