# 讀書筆記彙整 App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一個彙整 HyRead 劃線內容與 Notion 歷史讀書心得的筆記 app，可依書瀏覽、全文搜尋、手動新增/編輯/刪除筆記卡片，跨裝置同步。

**Architecture:** 新 repo `reading-notes-server`（FastAPI + SQLAlchemy，SQLite 本地/Postgres 正式環境，部署 Railway），沿用 `finance-server` 的檔案結構與慣例。前端為單一 HTML 檔案 PWA `reading-notes-app/index.html`（沿用 `finance-app` 的 vanilla JS + localStorage 存 API 位址/金鑰慣例），部署 Netlify。HyRead HTML 匯出與 Notion 歷史筆記都是一次性 / 手動觸發的匯入管線，不做成 app 內建上傳功能。

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / pytest / httpx / BeautifulSoup4；前端純 HTML/CSS/JS（無框架）。

**Spec:** `docs/superpowers/specs/2026-07-11-reading-notes-app-design.md`

---

## File Structure

```
reading-notes-server/                  (新 repo)
  main.py                              # FastAPI app, CORS, health check
  notes_api.py                         # 路由層 (books/notes/search)
  notes_db.py                          # SQLAlchemy engine + schema + CRUD 函式
  requirements.txt
  railway.json
  scripts/
    parse_hyread_html.py               # 解析 HyRead HTML 匯出
    split_notion_content.py            # 依 Markdown 標題切分 Notion 心得
    seed_import.py                     # 讀 seed JSON 寫入 DB (CLI)
    notion_seed.json                   # Notion 一次性匯入產出的 seed 資料 (Task 6 產出)
  tests/
    conftest.py
    test_notes_db.py
    test_notes_api.py
    test_parse_hyread_html.py
    test_split_notion_content.py
    test_seed_import.py
    fixtures/
      sample_hyread_export.html

reading-notes-app/                     (新 repo或資料夾，靜態前端)
  index.html                          # 唯一前端檔案
```

---

### Task 1: 後端骨架與資料庫 schema

**Files:**
- Create: `reading-notes-server/notes_db.py`
- Create: `reading-notes-server/requirements.txt`
- Create: `reading-notes-server/tests/conftest.py`
- Test: `reading-notes-server/tests/test_notes_db.py`

- [ ] **Step 1: 建立目錄與 requirements.txt**

```bash
mkdir -p "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server/tests/fixtures"
mkdir -p "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server/scripts"
```

`reading-notes-server/requirements.txt`:
```
fastapi
uvicorn[standard]
sqlalchemy
psycopg2-binary
pytest
httpx
beautifulsoup4
```

- [ ] **Step 2: 寫 conftest.py**

`reading-notes-server/tests/conftest.py`:
```python
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def notes_db(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sys.modules.pop("notes_db", None)
    sys.modules.pop("scripts.seed_import", None)
    import notes_db as db
    db.init_db()
    return db
```

- [ ] **Step 3: 寫失敗的 schema 測試**

`reading-notes-server/tests/test_notes_db.py`:
```python
def test_init_db_creates_tables(notes_db):
    from sqlalchemy import text

    with notes_db.engine.begin() as conn:
        conn.execute(text("SELECT * FROM books"))
        conn.execute(text("SELECT * FROM notes"))
```

- [ ] **Step 4: 執行測試確認失敗**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest tests/test_notes_db.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'notes_db'`

- [ ] **Step 5: 寫 notes_db.py（engine + schema）**

`reading-notes-server/notes_db.py`:
```python
import json
import logging
import os
from typing import Optional

from sqlalchemy import create_engine, text

CATEGORIES = ["房地產", "投資理財", "心靈成長", "能力培養"]


def _make_engine():
    url = os.environ.get("DATABASE_URL", "")
    if url:
        url = url.replace("postgres://", "postgresql://", 1)
        return create_engine(url, pool_pre_ping=True)
    data_dir = os.environ.get("DATA_DIR", "/tmp/reading_notes")
    os.makedirs(data_dir, exist_ok=True)
    return create_engine(f"sqlite:///{data_dir}/reading_notes.db")


engine = _make_engine()
IS_PG = engine.dialect.name == "postgresql"

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL, author TEXT DEFAULT '', category TEXT DEFAULT '[]',
    started_at TEXT, finished_at TEXT, source_tag TEXT NOT NULL DEFAULT 'manual'
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id),
    content TEXT NOT NULL, source TEXT NOT NULL, location TEXT DEFAULT '',
    highlighted_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS books (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL, author TEXT DEFAULT '', category TEXT DEFAULT '[]',
    started_at TEXT, finished_at TEXT, source_tag TEXT NOT NULL DEFAULT 'manual'
);
CREATE TABLE IF NOT EXISTS notes (
    id SERIAL PRIMARY KEY,
    book_id INTEGER NOT NULL REFERENCES books(id),
    content TEXT NOT NULL, source TEXT NOT NULL, location TEXT DEFAULT '',
    highlighted_at TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""


def init_db():
    schema = SCHEMA_PG if IS_PG else SCHEMA_SQLITE
    for stmt in schema.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        with engine.begin() as conn:
            conn.execute(text(stmt))
    logging.info("DB initialized (%s)", "PostgreSQL" if IS_PG else "SQLite")


def _rows(result) -> list:
    keys = list(result.keys())
    return [dict(zip(keys, row)) for row in result.fetchall()]
```

- [ ] **Step 6: 執行測試確認通過**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest tests/test_notes_db.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server"
git init
git add notes_db.py requirements.txt tests/conftest.py tests/test_notes_db.py
git commit -m "feat: scaffold reading-notes-server with DB schema"
```

---

### Task 2: Books / Notes CRUD 函式

**Files:**
- Modify: `reading-notes-server/notes_db.py`
- Test: `reading-notes-server/tests/test_notes_db.py`

- [ ] **Step 1: 寫失敗的測試（books）**

在 `test_notes_db.py` 加入：
```python
def test_insert_and_get_book(notes_db):
    book_id = notes_db.insert_book(
        title="我可能錯了", author="", category=["心靈成長"],
        started_at="2024-03-10", finished_at="2024-03-18", source_tag="notion",
    )
    book = notes_db.get_book(book_id)
    assert book["title"] == "我可能錯了"
    assert book["category"] == ["心靈成長"]
    assert book["source_tag"] == "notion"


def test_find_book_by_title(notes_db):
    notes_db.insert_book(title="富爸爸，窮爸爸")
    found = notes_db.find_book_by_title("富爸爸，窮爸爸")
    assert found is not None
    assert notes_db.find_book_by_title("不存在的書") is None


def test_list_books_filters_by_category_and_counts_notes(notes_db):
    b1 = notes_db.insert_book(title="書A", category=["心靈成長"])
    notes_db.insert_book(title="書B", category=["投資理財"])
    notes_db.insert_note(book_id=b1, content="心得1", source="manual")

    books = notes_db.list_books(category="心靈成長")
    assert len(books) == 1
    assert books[0]["title"] == "書A"
    assert books[0]["note_count"] == 1
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest tests/test_notes_db.py -v`
Expected: FAIL，`AttributeError: module 'notes_db' has no attribute 'insert_book'`（`test_list_books_filters_by_category_and_counts_notes` 之後還會因為 `insert_note` 尚未實作而失敗一次，屬預期中，留到 Step 7 一併解決）

- [ ] **Step 3: 實作 books 函式**

在 `notes_db.py` 尾端加入：
```python
def insert_book(title: str, author: str = "", category: Optional[list] = None,
                 started_at: Optional[str] = None, finished_at: Optional[str] = None,
                 source_tag: str = "manual") -> int:
    with engine.begin() as conn:
        result = conn.execute(
            text("""INSERT INTO books (title, author, category, started_at, finished_at, source_tag)
                     VALUES (:title, :author, :category, :started_at, :finished_at, :source_tag)"""),
            {"title": title, "author": author,
             "category": json.dumps(category or [], ensure_ascii=False),
             "started_at": started_at, "finished_at": finished_at, "source_tag": source_tag},
        )
        if IS_PG:
            book_id = conn.execute(text("SELECT lastval()")).scalar()
        else:
            book_id = result.lastrowid
    return book_id


def find_book_by_title(title: str) -> Optional[dict]:
    with engine.begin() as conn:
        result = conn.execute(text("SELECT * FROM books WHERE title = :title"), {"title": title})
        rows = _rows(result)
    return rows[0] if rows else None


def get_book(book_id: int) -> Optional[dict]:
    with engine.begin() as conn:
        result = conn.execute(text("SELECT * FROM books WHERE id = :id"), {"id": book_id})
        rows = _rows(result)
    if not rows:
        return None
    book = rows[0]
    book["category"] = json.loads(book["category"] or "[]")
    return book


def list_books(category: Optional[str] = None) -> list:
    with engine.begin() as conn:
        if category:
            result = conn.execute(
                text("SELECT * FROM books WHERE category LIKE :cat ORDER BY title"),
                {"cat": f"%{category}%"},
            )
        else:
            result = conn.execute(text("SELECT * FROM books ORDER BY title"))
        books = _rows(result)
        for b in books:
            b["category"] = json.loads(b["category"] or "[]")
            count_result = conn.execute(
                text("SELECT COUNT(*) AS c FROM notes WHERE book_id = :bid"), {"bid": b["id"]}
            )
            b["note_count"] = _rows(count_result)[0]["c"]
    return books
```

- [ ] **Step 4: 執行測試確認通過**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest tests/test_notes_db.py -v`
Expected: 2 個 book 測試 PASS，`test_list_books_filters_by_category_and_counts_notes` 仍 FAIL（`insert_note` 尚未實作，留到 Step 7 解決）

- [ ] **Step 5: 寫失敗的測試（notes）**

在 `test_notes_db.py` 加入：
```python
def test_insert_list_update_delete_note(notes_db):
    book_id = notes_db.insert_book(title="測試書")
    note_id = notes_db.insert_note(
        book_id=book_id, content="原文劃線", source="hyread",
        location="第一章", highlighted_at="2026-07-07T23:17:00",
    )

    notes = notes_db.list_notes_by_book(book_id)
    assert len(notes) == 1
    assert notes[0]["content"] == "原文劃線"
    assert notes[0]["location"] == "第一章"

    notes_db.update_note(note_id, content="修改後的內容", location="第二章")
    notes = notes_db.list_notes_by_book(book_id)
    assert notes[0]["content"] == "修改後的內容"
    assert notes[0]["location"] == "第二章"

    notes_db.delete_note(note_id)
    assert notes_db.list_notes_by_book(book_id) == []


def test_search_notes_matches_content_and_book_title(notes_db):
    book_id = notes_db.insert_book(title="心流的秘密")
    notes_db.insert_note(book_id=book_id, content="專注帶來心流狀態", source="manual")

    results = notes_db.search_notes("心流")
    assert len(results) == 1
    assert results[0]["book_title"] == "心流的秘密"

    results = notes_db.search_notes("不存在的關鍵字")
    assert results == []
```

- [ ] **Step 6: 執行測試確認失敗**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest tests/test_notes_db.py -v`
Expected: FAIL，`AttributeError: module 'notes_db' has no attribute 'insert_note'`

- [ ] **Step 7: 實作 notes 函式**

在 `notes_db.py` 尾端加入：
```python
def insert_note(book_id: int, content: str, source: str, location: str = "",
                 highlighted_at: Optional[str] = None) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            text("""INSERT INTO notes (book_id, content, source, location, highlighted_at)
                     VALUES (:book_id, :content, :source, :location, :highlighted_at)"""),
            {"book_id": book_id, "content": content, "source": source,
             "location": location, "highlighted_at": highlighted_at},
        )
        if IS_PG:
            note_id = conn.execute(text("SELECT lastval()")).scalar()
        else:
            note_id = result.lastrowid
    return note_id


def list_notes_by_book(book_id: int) -> list:
    with engine.begin() as conn:
        result = conn.execute(
            text("SELECT * FROM notes WHERE book_id = :bid ORDER BY highlighted_at, id"),
            {"bid": book_id},
        )
        return _rows(result)


def update_note(note_id: int, content: str, location: str = "") -> None:
    with engine.begin() as conn:
        conn.execute(
            text("""UPDATE notes SET content = :content, location = :location,
                     updated_at = CURRENT_TIMESTAMP WHERE id = :id"""),
            {"content": content, "location": location, "id": note_id},
        )


def delete_note(note_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM notes WHERE id = :id"), {"id": note_id})


def search_notes(query: str) -> list:
    with engine.begin() as conn:
        result = conn.execute(
            text("""SELECT notes.*, books.title AS book_title FROM notes
                     JOIN books ON books.id = notes.book_id
                     WHERE notes.content LIKE :q OR books.title LIKE :q
                     ORDER BY notes.highlighted_at DESC"""),
            {"q": f"%{query}%"},
        )
        return _rows(result)
```

- [ ] **Step 8: 執行測試確認通過**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest tests/test_notes_db.py -v`
Expected: PASS（全部通過）

- [ ] **Step 9: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server"
git add notes_db.py tests/test_notes_db.py
git commit -m "feat: add books/notes CRUD and search functions"
```

---

### Task 3: FastAPI 路由層與 auth

**Files:**
- Create: `reading-notes-server/notes_api.py`
- Create: `reading-notes-server/main.py`
- Create: `reading-notes-server/railway.json`
- Test: `reading-notes-server/tests/test_notes_api.py`

- [ ] **Step 1: 寫失敗的 API 測試**

`reading-notes-server/tests/test_notes_api.py`:
```python
import sys


def _fresh_app(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for mod in ("main", "notes_api", "notes_db"):
        sys.modules.pop(mod, None)
    import main
    return main.app


def test_create_and_list_books(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    app = _fresh_app(tmp_path, monkeypatch)
    client = TestClient(app)

    resp = client.post("/notes/books", json={"title": "書A", "category": ["心靈成長"]})
    assert resp.status_code == 200
    book_id = resp.json()["id"]

    resp = client.get("/notes/books")
    assert resp.status_code == 200
    books = resp.json()
    assert books[0]["title"] == "書A"

    resp = client.get(f"/notes/books/{book_id}")
    assert resp.status_code == 200
    assert resp.json()["notes"] == []


def test_note_crud_and_search(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    app = _fresh_app(tmp_path, monkeypatch)
    client = TestClient(app)

    book_id = client.post("/notes/books", json={"title": "心流的秘密"}).json()["id"]
    note_id = client.post(
        "/notes/notes",
        json={"book_id": book_id, "content": "專注帶來心流", "source": "manual", "location": "第一章"},
    ).json()["id"]

    resp = client.put(f"/notes/notes/{note_id}", json={"content": "修改後", "location": "第二章"})
    assert resp.status_code == 200

    resp = client.get("/notes/search", params={"q": "修改後"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.delete(f"/notes/notes/{note_id}")
    assert resp.status_code == 200
    assert client.get("/notes/search", params={"q": "修改後"}).json() == []


def test_auth_rejects_wrong_key(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("NOTES_API_KEY", "secret123")
    app = _fresh_app(tmp_path, monkeypatch)
    client = TestClient(app)

    resp = client.get("/notes/books")
    assert resp.status_code == 401

    resp = client.get("/notes/books", headers={"x-api-key": "secret123"})
    assert resp.status_code == 200
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest tests/test_notes_api.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: 寫 notes_api.py**

`reading-notes-server/notes_api.py`:
```python
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

import notes_db as db

router = APIRouter(prefix="/notes")

NOTES_API_KEY = os.environ.get("NOTES_API_KEY", "")


def _auth(x_api_key: Optional[str]):
    if NOTES_API_KEY and x_api_key != NOTES_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


class BookIn(BaseModel):
    title: str
    author: str = ""
    category: list[str] = []
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    source_tag: str = "manual"


class NoteIn(BaseModel):
    book_id: int
    content: str
    source: str = "manual"
    location: str = ""
    highlighted_at: Optional[str] = None


class NoteUpdate(BaseModel):
    content: str
    location: str = ""


@router.get("/books")
def get_books(category: Optional[str] = None, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return db.list_books(category)


@router.post("/books")
def post_book(book: BookIn, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    book_id = db.insert_book(**book.model_dump())
    return {"id": book_id}


@router.get("/books/{book_id}")
def get_book_detail(book_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    book = db.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    book["notes"] = db.list_notes_by_book(book_id)
    return book


@router.post("/notes")
def post_note(note: NoteIn, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    note_id = db.insert_note(note.book_id, note.content, note.source, note.location, note.highlighted_at)
    return {"id": note_id}


@router.put("/notes/{note_id}")
def put_note(note_id: int, note: NoteUpdate, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    db.update_note(note_id, note.content, note.location)
    return {"ok": True}


@router.delete("/notes/{note_id}")
def delete_note_route(note_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    db.delete_note(note_id)
    return {"ok": True}


@router.get("/search")
def search(q: str, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return db.search_notes(q)
```

- [ ] **Step 4: 寫 main.py**

`reading-notes-server/main.py`:
```python
import logging

logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from notes_api import router as notes_router
from notes_db import init_db

app = FastAPI(title="Reading Notes API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
app.include_router(notes_router)


@app.get("/")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: 寫 railway.json**

`reading-notes-server/railway.json`:
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

- [ ] **Step 6: 執行測試確認通過**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest tests/test_notes_api.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server"
git add notes_api.py main.py railway.json tests/test_notes_api.py
git commit -m "feat: add FastAPI routes for books/notes with API key auth"
```

---

### Task 4: HyRead HTML parser

**Files:**
- Create: `reading-notes-server/scripts/parse_hyread_html.py`
- Create: `reading-notes-server/tests/fixtures/sample_hyread_export.html`
- Test: `reading-notes-server/tests/test_parse_hyread_html.py`

- [ ] **Step 1: 建立測試用 fixture**

`reading-notes-server/tests/fixtures/sample_hyread_export.html`（節錄自使用者實際匯出的 HyRead HTML，含一則有個人註解、一則沒有）：
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
</head>
<body>
  <div class='body-container'>
    <div class='heading'>
      <div class='book-cover'>
        <img src='https://webcdn2.ebook.hyread.com.tw/bookcover/459592978626767837420251309110728.jpg' />
      </div>
      <div class='book-info-container'>
        <div class='book-title'>人生的五種財富:設計你的夢想人生, 時間、社會、心理、身體、金錢財富都豐收</div>
        <div class='book-data'>薩希. 布魯姆(Sahil Bloom)著;唐傑克譯．商業週刊 ．</div>
      </div>
    </div>
    <div class='note-container'>
  <div class='note-heading'>
    <div class='note-chapter'>人一生的旅程</div>
    <div class='note-time'>2026/7/7 23:17</div>
  </div>
  <div class='highlight-section'>
    <div class='highlight-mark-container'>
      <div class='highlight-mark-red'></div>
    </div>
    <div class='highlight-content-red'>
        丟掉壞的記分板，將生活重新放在另一個新的記分板上
    </div>
  </div>
  <div class='note-text'>

  </div>
</div>

<div class='note-container'>
  <div class='note-heading'>
    <div class='note-chapter'>千年智慧</div>
    <div class='note-time'>2026/7/7 23:27</div>
  </div>
  <div class='highlight-section'>
    <div class='highlight-mark-container'>
      <div class='highlight-mark-red'></div>
    </div>
    <div class='highlight-content-red'>
        你的富裕生活可能是由金錢來實現，但最終的幸福，是由其他一切來定義
    </div>
  </div>
  <div class='note-text'>
      我自己對這句話也很有感觸
  </div>
</div>

    <div class='footer'>來自高雄市立圖書館．HyRead．電子書</div>
  </div>
</body>
</html>
```

- [ ] **Step 2: 寫失敗的測試**

`reading-notes-server/tests/test_parse_hyread_html.py`:
```python
import os

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_hyread_export.html")


def test_parse_hyread_html_extracts_book_and_notes():
    from scripts.parse_hyread_html import parse_hyread_html

    with open(FIXTURE_PATH, encoding="utf-8") as f:
        html = f.read()

    result = parse_hyread_html(html)

    assert result["title"] == "人生的五種財富:設計你的夢想人生, 時間、社會、心理、身體、金錢財富都豐收"
    assert "薩希" in result["author"]
    assert len(result["notes"]) == 2

    first = result["notes"][0]
    assert first["location"] == "人一生的旅程"
    assert first["content"] == "丟掉壞的記分板，將生活重新放在另一個新的記分板上"
    assert first["highlighted_at"] == "2026-07-07T23:17:00"

    second = result["notes"][1]
    assert second["location"] == "千年智慧"
    assert "你的富裕生活可能是由金錢來實現" in second["content"]
    assert "我自己對這句話也很有感觸" in second["content"]
```

- [ ] **Step 3: 執行測試確認失敗**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest tests/test_parse_hyread_html.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'scripts'`

- [ ] **Step 4: 建立 scripts package 與 parser**

```bash
touch "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server/scripts/__init__.py"
```

`reading-notes-server/scripts/parse_hyread_html.py`:
```python
from datetime import datetime

from bs4 import BeautifulSoup


def parse_hyread_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    title = soup.select_one(".book-title").get_text(strip=True)
    author = soup.select_one(".book-data").get_text(strip=True)

    notes = []
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

        notes.append({
            "content": content,
            "location": chapter,
            "highlighted_at": _parse_time(time_str) if time_str else None,
        })

    return {"title": title, "author": author, "notes": notes}


def _parse_time(time_str: str) -> str:
    dt = datetime.strptime(time_str, "%Y/%m/%d %H:%M")
    return dt.isoformat()
```

- [ ] **Step 5: 執行測試確認通過**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest tests/test_parse_hyread_html.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server"
git add scripts/__init__.py scripts/parse_hyread_html.py tests/fixtures/sample_hyread_export.html tests/test_parse_hyread_html.py
git commit -m "feat: add HyRead HTML export parser"
```

---

### Task 5: Notion 心得分段函式 + seed 匯入 script

**Files:**
- Create: `reading-notes-server/scripts/split_notion_content.py`
- Create: `reading-notes-server/scripts/seed_import.py`
- Test: `reading-notes-server/tests/test_split_notion_content.py`
- Test: `reading-notes-server/tests/test_seed_import.py`

- [ ] **Step 1: 寫失敗的測試（split_notion_content）**

`reading-notes-server/tests/test_split_notion_content.py`:
```python
def test_split_notion_content_splits_on_h1_headings():
    from scripts.split_notion_content import split_notion_content

    markdown_text = (
        "# 你有的超能力：varsevarande 覺察\n"
        "當我們心在當下...第一段內容\n"
        "# 不要相信你的每個念頭\n"
        "念頭本身當然不構成問題...第二段內容\n"
    )

    notes = split_notion_content(markdown_text)

    assert len(notes) == 2
    assert notes[0]["location"] == "你有的超能力：varsevarande 覺察"
    assert "第一段內容" in notes[0]["content"]
    assert notes[1]["location"] == "不要相信你的每個念頭"
    assert "第二段內容" in notes[1]["content"]


def test_split_notion_content_ignores_preamble_without_heading():
    from scripts.split_notion_content import split_notion_content

    markdown_text = "沒有標題的前言\n# 主題一\n內容一\n"
    notes = split_notion_content(markdown_text)

    assert len(notes) == 1
    assert notes[0]["location"] == "主題一"
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest tests/test_split_notion_content.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'scripts.split_notion_content'`

- [ ] **Step 3: 實作 split_notion_content**

`reading-notes-server/scripts/split_notion_content.py`:
```python
import re


def split_notion_content(markdown_text: str) -> list:
    parts = re.split(r"(?m)^# (.+)$", markdown_text)
    notes = []
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if body:
            notes.append({"content": body, "location": heading})
    return notes
```

- [ ] **Step 4: 執行測試確認通過**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest tests/test_split_notion_content.py -v`
Expected: PASS

- [ ] **Step 5: 寫失敗的測試（seed_import）**

`reading-notes-server/tests/test_seed_import.py`:
```python
def test_import_hyread_book_creates_book_and_notes(notes_db):
    from scripts.seed_import import import_hyread_book

    parsed = {
        "title": "人生的五種財富",
        "author": "薩希. 布魯姆",
        "notes": [
            {"content": "丟掉壞的記分板", "location": "人一生的旅程", "highlighted_at": "2026-07-07T23:17:00"},
        ],
    }

    book_id = import_hyread_book(parsed)
    book = notes_db.get_book(book_id)
    assert book["title"] == "人生的五種財富"
    assert book["source_tag"] == "hyread"

    notes = notes_db.list_notes_by_book(book_id)
    assert len(notes) == 1
    assert notes[0]["source"] == "hyread"
    assert notes[0]["location"] == "人一生的旅程"


def test_import_hyread_book_reuses_existing_book_by_title(notes_db):
    from scripts.seed_import import import_hyread_book

    parsed = {"title": "重複的書", "author": "", "notes": [{"content": "第一次", "location": "", "highlighted_at": None}]}
    book_id_1 = import_hyread_book(parsed)

    parsed2 = {"title": "重複的書", "author": "", "notes": [{"content": "第二次", "location": "", "highlighted_at": None}]}
    book_id_2 = import_hyread_book(parsed2)

    assert book_id_1 == book_id_2
    assert len(notes_db.list_notes_by_book(book_id_1)) == 2


def test_import_notion_seed_creates_books_and_notes(notes_db):
    from scripts.seed_import import import_notion_seed

    seed = [
        {
            "title": "我可能錯了",
            "category": ["心靈成長"],
            "started_at": "2024-03-10",
            "finished_at": "2024-03-18",
            "notes": [
                {"content": "念頭本身當然不構成問題", "location": "不要相信你的每個念頭"},
            ],
        }
    ]

    import_notion_seed(seed)

    books = notes_db.list_books()
    assert len(books) == 1
    assert books[0]["title"] == "我可能錯了"
    assert books[0]["source_tag"] == "notion"

    notes = notes_db.list_notes_by_book(books[0]["id"])
    assert notes[0]["source"] == "notion"
    assert notes[0]["location"] == "不要相信你的每個念頭"
```

- [ ] **Step 6: 執行測試確認失敗**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest tests/test_seed_import.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'scripts.seed_import'`

- [ ] **Step 7: 實作 seed_import.py**

`reading-notes-server/scripts/seed_import.py`:
```python
import json
import sys

import notes_db as db


def import_hyread_book(parsed: dict) -> int:
    existing = db.find_book_by_title(parsed["title"])
    book_id = existing["id"] if existing else db.insert_book(
        title=parsed["title"], author=parsed.get("author", ""), source_tag="hyread",
    )
    for note in parsed["notes"]:
        db.insert_note(
            book_id=book_id,
            content=note["content"],
            source="hyread",
            location=note.get("location", ""),
            highlighted_at=note.get("highlighted_at"),
        )
    return book_id


def import_notion_seed(seed: list) -> None:
    for entry in seed:
        book_id = db.insert_book(
            title=entry["title"],
            category=entry.get("category", []),
            started_at=entry.get("started_at"),
            finished_at=entry.get("finished_at"),
            source_tag="notion",
        )
        for note in entry["notes"]:
            db.insert_note(
                book_id=book_id,
                content=note["content"],
                source="notion",
                location=note.get("location", ""),
                highlighted_at=entry.get("finished_at"),
            )


if __name__ == "__main__":
    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        seed = json.load(f)
    if isinstance(seed, dict) and "notes" in seed and "title" in seed:
        import_hyread_book(seed)
    else:
        import_notion_seed(seed)
```

- [ ] **Step 8: 執行測試確認通過**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest tests/test_seed_import.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server"
git add scripts/split_notion_content.py scripts/seed_import.py tests/test_split_notion_content.py tests/test_seed_import.py
git commit -m "feat: add Notion content splitter and seed import script"
```

---

### Task 6: 產生 Notion 歷史筆記 seed JSON（需要 Notion MCP 工具，非一般 coding 任務）

**這個任務必須由有 Notion MCP 工具存取權限的 agent 執行**（例如具備 `mcp__claude_ai_Notion__*` 工具的 Claude session），不能單靠一支獨立 Python script 完成，因為需要即時呼叫 Notion API。

**Files:**
- Create: `reading-notes-server/scripts/notion_seed.json`

- [ ] **Step 1: 查詢「閱讀清單」資料庫所有書籍**

呼叫 `mcp__claude_ai_Notion__notion-query-data-sources`：
```json
{
  "data": {
    "data_source_urls": ["collection://1e6086fa-03f6-4535-81da-38c6a9a52624"],
    "query": "SELECT * FROM \"collection://1e6086fa-03f6-4535-81da-38c6a9a52624\""
  }
}
```
回傳每本書的 `url`（頁面連結）、`書名`、`種類`（JSON 字串陣列）、`date:開始閱讀日:start`、`date:完成閱讀日:start`。

- [ ] **Step 2: 逐本書抓取頁面內文**

對每本書的 `url`，呼叫 `mcp__claude_ai_Notion__notion-fetch`，取得 `<content>` 區塊內的 Markdown 全文。

- [ ] **Step 3: 用 split_notion_content 切分內文**

對每本書抓到的 Markdown 全文，呼叫 Task 5 寫好的 `split_notion_content(markdown_text)`，取得 `notes` 陣列（`content` + `location`）。若某本書頁面完全沒有 `#` 標題（純短評），將整頁全文當成單一筆記，`location` 設為空字串。

- [ ] **Step 4: 組成 seed JSON 並寫檔**

依下列 schema 組合所有書籍，寫入 `reading-notes-server/scripts/notion_seed.json`：
```json
[
  {
    "title": "我可能錯了",
    "category": ["心靈成長"],
    "started_at": "2024-03-10",
    "finished_at": "2024-03-18",
    "notes": [
      {"content": "...", "location": "你有的超能力：varsevarande 覺察"},
      {"content": "...", "location": "不要相信你的每個念頭"}
    ]
  }
]
```

- [ ] **Step 5: 執行匯入**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server"
PYTHONPATH=. python3 scripts/seed_import.py scripts/notion_seed.json
```

- [ ] **Step 6: 驗證**

啟動 API（`uvicorn main:app --reload`），呼叫 `GET /notes/books`，確認書籍數量與 Notion「閱讀清單」資料庫筆數一致。

- [ ] **Step 7: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server"
git add scripts/notion_seed.json
git commit -m "data: import Notion historical reading notes seed"
```

---

### Task 7: 匯入使用者現有的 HyRead HTML 匯出檔

**Files:**
- Modify: `reading-notes-server/scripts/seed_import.py`（新增 CLI 支援直接讀 HyRead HTML）

- [ ] **Step 1: 擴充 seed_import.py CLI，支援直接吃 .html 檔**

修改 `reading-notes-server/scripts/seed_import.py` 的 `__main__` 區塊：
```python
if __name__ == "__main__":
    path = sys.argv[1]
    if path.endswith(".html"):
        from scripts.parse_hyread_html import parse_hyread_html

        with open(path, encoding="utf-8") as f:
            html = f.read()
        import_hyread_book(parse_hyread_html(html))
    else:
        with open(path, encoding="utf-8") as f:
            seed = json.load(f)
        if isinstance(seed, dict) and "notes" in seed and "title" in seed:
            import_hyread_book(seed)
        else:
            import_notion_seed(seed)
```

- [ ] **Step 2: 執行既有測試確認沒有壞掉**

Run: `cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server" && python3 -m pytest -v`
Expected: PASS（全部）

- [ ] **Step 3: 匯入使用者提供的實際 HyRead HTML 檔**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server"
PYTHONPATH=. python3 scripts/seed_import.py "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Desktop/260711_人生的五種財富_設計你的夢想人生, 時間、社會、心理、身體、金錢財富都豐收_notes_by_chapter.html"
```

- [ ] **Step 4: 驗證**

啟動 API，呼叫 `GET /notes/books`，確認「人生的五種財富」這本書出現，且 `note_count` 為該書實際劃線則數。

- [ ] **Step 5: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server"
git add scripts/seed_import.py
git commit -m "feat: support importing HyRead HTML export directly via CLI"
```

---

### Task 8: 前端骨架 + 書籍列表

**Files:**
- Create: `reading-notes-app/index.html`

- [ ] **Step 1: 建立目錄與初版 index.html**

```bash
mkdir -p "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-app"
```

`reading-notes-app/index.html`:
```html
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>讀書筆記</title>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display",sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;margin:0}
  .container{max-width:720px;margin:0 auto;padding:20px}
  h1{font-size:22px;font-weight:600}
  .settings{display:flex;gap:8px;margin-bottom:16px}
  .settings input{flex:1;background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:8px;border-radius:6px}
  .settings button{background:#334155;color:#e2e8f0;border:none;padding:8px 12px;border-radius:6px;cursor:pointer}
  .filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}
  .filters button{background:#1e293b;color:#94a3b8;border:1px solid #334155;padding:6px 12px;border-radius:16px;cursor:pointer;font-size:13px}
  .filters button.active{background:#0ea5e9;color:#fff;border-color:#0ea5e9}
  .book-card{background:#1e293b;border-radius:10px;padding:14px 16px;margin-bottom:10px;cursor:pointer}
  .book-card .title{font-size:16px;font-weight:600}
  .book-card .meta{font-size:13px;color:#94a3b8;margin-top:4px}
</style>
</head>
<body>
<div class="container">
  <h1>讀書筆記</h1>

  <div class="settings">
    <input id="apiUrlInput" placeholder="後端 API 網址，例如 https://xxx.up.railway.app">
    <input id="apiKeyInput" placeholder="API Key（若有設定）">
    <button id="saveSettingsBtn">儲存</button>
  </div>

  <div class="filters" id="filters"></div>

  <div id="bookList"></div>
</div>

<script>
let API = localStorage.getItem('api_url') || '';
let KEY = localStorage.getItem('api_key') || '';
document.getElementById('apiUrlInput').value = API;
document.getElementById('apiKeyInput').value = KEY;

document.getElementById('saveSettingsBtn').onclick = () => {
  API = document.getElementById('apiUrlInput').value.replace(/\/$/, '');
  KEY = document.getElementById('apiKeyInput').value;
  localStorage.setItem('api_url', API);
  localStorage.setItem('api_key', KEY);
  loadBooks();
};

function headers() {
  return KEY ? {'x-api-key': KEY} : {};
}

const CATEGORIES = ["房地產", "投資理財", "心靈成長", "能力培養"];
let activeCategory = null;

function renderFilters() {
  const el = document.getElementById('filters');
  el.innerHTML = '';
  const allBtn = document.createElement('button');
  allBtn.textContent = '全部';
  allBtn.className = activeCategory === null ? 'active' : '';
  allBtn.onclick = () => { activeCategory = null; loadBooks(); };
  el.appendChild(allBtn);

  CATEGORIES.forEach(cat => {
    const btn = document.createElement('button');
    btn.textContent = cat;
    btn.className = activeCategory === cat ? 'active' : '';
    btn.onclick = () => { activeCategory = cat; loadBooks(); };
    el.appendChild(btn);
  });
}

async function loadBooks() {
  renderFilters();
  if (!API) return;
  const url = activeCategory
    ? `${API}/notes/books?category=${encodeURIComponent(activeCategory)}`
    : `${API}/notes/books`;
  const resp = await fetch(url, {headers: headers()});
  const books = await resp.json();
  const listEl = document.getElementById('bookList');
  listEl.innerHTML = '';
  books.forEach(book => {
    const card = document.createElement('div');
    card.className = 'book-card';
    card.innerHTML = `
      <div class="title">${book.title}</div>
      <div class="meta">${book.author || ''} ・ ${book.note_count} 則筆記 ・ ${book.source_tag}</div>
    `;
    card.onclick = () => { window.location.href = `book.html?id=${book.id}`; };
    listEl.appendChild(card);
  });
}

loadBooks();
</script>
</body>
</html>
```

- [ ] **Step 2: 手動驗證**

用瀏覽器直接打開 `reading-notes-app/index.html`（`file://` 開啟即可，或起一個簡單 http server：`python3 -m http.server 8080`），在「後端 API 網址」欄位填入本機跑的後端網址（例如先在另一個終端機執行 `cd reading-notes-server && uvicorn main:app --reload --port 8000`，網址填 `http://localhost:8000`），點「儲存」，確認分類篩選按鈕能正確篩出 Task 6/7 匯入的書籍，且卡片顯示書名/作者/筆記數/來源。

- [ ] **Step 3: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-app"
git init
git add index.html
git commit -m "feat: add reading notes frontend skeleton with book list"
```

---

### Task 9: 書籍詳細頁（筆記卡片 + 來源標籤）

**Files:**
- Create: `reading-notes-app/book.html`

- [ ] **Step 1: 寫 book.html**

`reading-notes-app/book.html`:
```html
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>書籍筆記</title>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display",sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;margin:0}
  .container{max-width:720px;margin:0 auto;padding:20px}
  a.back{color:#94a3b8;text-decoration:none;font-size:14px}
  h1{font-size:20px;font-weight:600;margin:8px 0 2px}
  .author{color:#94a3b8;font-size:14px;margin-bottom:20px}
  .note-card{background:#1e293b;border-radius:10px;padding:14px 16px;margin-bottom:10px}
  .note-card .meta{display:flex;justify-content:space-between;font-size:12px;color:#64748b;margin-bottom:6px}
  .source-tag{padding:2px 8px;border-radius:10px;font-size:11px}
  .source-hyread{background:#0ea5e930;color:#38bdf8}
  .source-notion{background:#a855f730;color:#c084fc}
  .source-manual{background:#33415530;color:#94a3b8}
  .note-content{white-space:pre-wrap;line-height:1.6}
</style>
</head>
<body>
<div class="container">
  <a class="back" href="index.html">← 回書籍列表</a>
  <h1 id="bookTitle"></h1>
  <div class="author" id="bookAuthor"></div>
  <div id="noteList"></div>
</div>

<script>
const API = localStorage.getItem('api_url') || '';
const KEY = localStorage.getItem('api_key') || '';
function headers() { return KEY ? {'x-api-key': KEY} : {}; }

const params = new URLSearchParams(window.location.search);
const bookId = params.get('id');

async function loadBook() {
  const resp = await fetch(`${API}/notes/books/${bookId}`, {headers: headers()});
  const book = await resp.json();
  document.getElementById('bookTitle').textContent = book.title;
  document.getElementById('bookAuthor').textContent = book.author || '';

  const listEl = document.getElementById('noteList');
  listEl.innerHTML = '';
  book.notes.forEach(note => {
    const card = document.createElement('div');
    card.className = 'note-card';
    card.innerHTML = `
      <div class="meta">
        <span>${note.location || ''}</span>
        <span class="source-tag source-${note.source}">${note.source}</span>
      </div>
      <div class="note-content">${note.content}</div>
    `;
    listEl.appendChild(card);
  });
}

loadBook();
</script>
</body>
</html>
```

- [ ] **Step 2: 手動驗證**

在 `index.html` 點一本書，確認跳到 `book.html?id=X`，該書所有筆記卡片依 `highlighted_at` 排序顯示，每張卡片右上角有正確的來源標籤顏色（hyread 藍 / notion 紫 / manual 灰）。

- [ ] **Step 3: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-app"
git add book.html
git commit -m "feat: add book detail page showing note cards with source tags"
```

---

### Task 10: 全文搜尋

**Files:**
- Modify: `reading-notes-app/index.html`

- [ ] **Step 1: 在 index.html 加入搜尋框與結果渲染**

在 `<div class="filters" id="filters"></div>` 上方加入：
```html
<div style="margin-bottom:16px;">
  <input id="searchInput" placeholder="搜尋筆記內容或書名..." style="width:100%;box-sizing:border-box;background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:8px;border-radius:6px">
</div>
<div id="searchResults"></div>
```

在 `<script>` 內加入：
```javascript
const searchInput = document.getElementById('searchInput');
let searchTimer = null;
searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(runSearch, 300);
});

async function runSearch() {
  const q = searchInput.value.trim();
  const resultsEl = document.getElementById('searchResults');
  const filtersEl = document.getElementById('filters');
  const listEl = document.getElementById('bookList');

  if (!q) {
    resultsEl.innerHTML = '';
    filtersEl.style.display = '';
    listEl.style.display = '';
    return;
  }
  filtersEl.style.display = 'none';
  listEl.style.display = 'none';

  const resp = await fetch(`${API}/notes/search?q=${encodeURIComponent(q)}`, {headers: headers()});
  const notes = await resp.json();
  resultsEl.innerHTML = '';
  notes.forEach(note => {
    const card = document.createElement('div');
    card.className = 'book-card';
    card.innerHTML = `
      <div class="title">${note.book_title}</div>
      <div class="meta">${note.location || ''}</div>
      <div style="margin-top:6px;white-space:pre-wrap;">${note.content}</div>
    `;
    card.onclick = () => { window.location.href = `book.html?id=${note.book_id}`; };
    resultsEl.appendChild(card);
  });
}
```

- [ ] **Step 2: 手動驗證**

在搜尋框輸入 Task 6/7 匯入資料中出現過的關鍵字（例如「心流」或「記分板」），確認 300ms 後跳出跨書搜尋結果，書籍列表與分類按鈕暫時隱藏；清空搜尋框後恢復原本列表。

- [ ] **Step 3: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-app"
git add index.html
git commit -m "feat: add cross-book full-text search"
```

---

### Task 11: 手動新增 / 編輯 / 刪除筆記卡片

**Files:**
- Modify: `reading-notes-app/book.html`

- [ ] **Step 1: 加入新增筆記表單**

在 `book.html` 的 `<div id="noteList"></div>` 上方加入：
```html
<div class="note-card" id="addNoteForm">
  <input id="newNoteContent" placeholder="筆記內容" style="width:100%;box-sizing:border-box;background:#0f172a;border:1px solid #334155;color:#e2e8f0;padding:8px;border-radius:6px;margin-bottom:8px">
  <input id="newNoteLocation" placeholder="章節/主題（可空）" style="width:100%;box-sizing:border-box;background:#0f172a;border:1px solid #334155;color:#e2e8f0;padding:8px;border-radius:6px;margin-bottom:8px">
  <button id="addNoteBtn" style="background:#0ea5e9;color:#fff;border:none;padding:8px 14px;border-radius:6px;cursor:pointer">新增筆記</button>
</div>
```

- [ ] **Step 2: 加入新增/編輯/刪除的 JS 邏輯**

修改 `book.html` 的 `<script>`，把 note-card 渲染改成可編輯/刪除，並加上新增邏輯：
```javascript
document.getElementById('addNoteBtn').onclick = async () => {
  const content = document.getElementById('newNoteContent').value.trim();
  const location = document.getElementById('newNoteLocation').value.trim();
  if (!content) return;
  await fetch(`${API}/notes/notes`, {
    method: 'POST',
    headers: {...headers(), 'Content-Type': 'application/json'},
    body: JSON.stringify({book_id: Number(bookId), content, source: 'manual', location}),
  });
  document.getElementById('newNoteContent').value = '';
  document.getElementById('newNoteLocation').value = '';
  loadBook();
};

function renderNoteCard(note) {
  const card = document.createElement('div');
  card.className = 'note-card';
  card.innerHTML = `
    <div class="meta">
      <span>${note.location || ''}</span>
      <span class="source-tag source-${note.source}">${note.source}</span>
    </div>
    <div class="note-content" data-view>${note.content}</div>
    <textarea data-edit style="display:none;width:100%;box-sizing:border-box;background:#0f172a;border:1px solid #334155;color:#e2e8f0;padding:8px;border-radius:6px;min-height:80px">${note.content}</textarea>
    <div style="margin-top:8px;display:flex;gap:8px;">
      <button data-action="edit" style="background:#334155;color:#e2e8f0;border:none;padding:4px 10px;border-radius:6px;cursor:pointer">編輯</button>
      <button data-action="save" style="display:none;background:#0ea5e9;color:#fff;border:none;padding:4px 10px;border-radius:6px;cursor:pointer">儲存</button>
      <button data-action="delete" style="background:#7f1d1d;color:#fecaca;border:none;padding:4px 10px;border-radius:6px;cursor:pointer">刪除</button>
    </div>
  `;

  const viewEl = card.querySelector('[data-view]');
  const editEl = card.querySelector('[data-edit]');
  const editBtn = card.querySelector('[data-action="edit"]');
  const saveBtn = card.querySelector('[data-action="save"]');
  const deleteBtn = card.querySelector('[data-action="delete"]');

  editBtn.onclick = () => {
    viewEl.style.display = 'none';
    editEl.style.display = 'block';
    editBtn.style.display = 'none';
    saveBtn.style.display = 'inline-block';
  };

  saveBtn.onclick = async () => {
    await fetch(`${API}/notes/notes/${note.id}`, {
      method: 'PUT',
      headers: {...headers(), 'Content-Type': 'application/json'},
      body: JSON.stringify({content: editEl.value, location: note.location || ''}),
    });
    loadBook();
  };

  deleteBtn.onclick = async () => {
    if (!confirm('確定要刪除這則筆記嗎？')) return;
    await fetch(`${API}/notes/notes/${note.id}`, {method: 'DELETE', headers: headers()});
    loadBook();
  };

  return card;
}
```

修改 `loadBook()` 內的渲染迴圈，改用 `renderNoteCard`：
```javascript
  book.notes.forEach(note => {
    listEl.appendChild(renderNoteCard(note));
  });
```
（取代原本用 `card.innerHTML` 直接組字串的區塊）

- [ ] **Step 3: 手動驗證**

在書籍詳細頁：
1. 新增一則手動筆記，確認出現在列表且 source-tag 顯示 `manual`
2. 點「編輯」→ 修改內容 →「儲存」，確認內容更新
3. 點「刪除」→ 確認彈出確認對話框，確認後該筆記從列表消失

- [ ] **Step 4: Commit**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-app"
git add book.html
git commit -m "feat: add manual note create/edit/delete UI"
```

---

### Task 12: 部署設定

**Files:**
- Modify: `reading-notes-server/main.py`（確認 CORS 允許前端網域，MVP 用 `*` 已足夠不需修改）
- 無新檔案；此任務為操作步驟

- [ ] **Step 1: 部署後端到 Railway**

於 Railway 建立新專案，連接 `reading-notes-server` repo，設定環境變數：
- `NOTES_API_KEY`：自訂一組金鑰字串（用於前端 API Key 欄位）
- （若使用 Railway Postgres add-on）`DATABASE_URL` 會自動注入，否則後端會退回本機 SQLite（資料存在容器內，重新部署可能遺失，建議正式使用時加 Postgres add-on）

部署完成後記下對外網址（例如 `https://reading-notes-server-production.up.railway.app`）。

- [ ] **Step 2: 部署前端到 Netlify**

將 `reading-notes-app` 資料夾部署到 Netlify（拖拉部署或連接 repo，無需 build step，直接 publish 該資料夾）。

- [ ] **Step 3: 手動驗證**

打開部署後的 Netlify 網址，填入 Railway 後端網址與 `NOTES_API_KEY`，確認書籍列表、搜尋、新增/編輯/刪除都能正常運作。

- [ ] **Step 4: Commit（如有設定檔變動）**

```bash
cd "/Users/wangyingyu/Library/Mobile Documents/com~apple~CloudDocs/Jenna_agent/reading-notes-server"
git add -A
git commit -m "chore: finalize deployment configuration" --allow-empty
```

---

## v2 待辦（本計畫不含）

- 隨機回顧模式
- 間隔重複提醒
