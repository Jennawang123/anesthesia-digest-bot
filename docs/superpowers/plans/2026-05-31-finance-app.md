# 個人財務 PWA + LINE Bot 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立個人財務管理系統：LINE bot 每月解析銀行 PDF 對帳單，PWA 顯示支出/收支/總資產三個頁面。

**Architecture:** 擴充現有 `line-claude-bot`（Railway 部署的 FastAPI），新增 `/finance/*` REST API 與 SQLite 資料庫（Railway Volume）；前端為單一 `finance-app/index.html`（PWA，IndexedDB 本地快取 + Railway API）。LINE bot 新增「處理對帳單」指令，透過 IMAP 從 Gmail 下載 PDF、用 `pypdf` 解密、用 Claude API 解析交易並分類。

**Tech Stack:** Python 3.12, FastAPI, SQLite, pypdf, imaplib, yfinance, anthropic SDK, Vanilla JS PWA (IndexedDB, Chart.js)

---

## 系統概覽

```
[LINE Bot 指令：處理對帳單]
  └→ IMAP 下載 Gmail PDF 附件
  └→ pypdf 解密（密碼=身分證號）
  └→ Claude API 解析交易 + 分類
  └→ 回傳預覽給使用者確認
  └→ 確認後 POST /finance/transactions

[PWA finance-app/index.html]
  Tab 1 支出   ← GET /finance/transactions
  Tab 2 收支   ← GET /finance/income + /finance/transactions
  Tab 3 總資產 ← GET /finance/assets + yfinance 即時股價

[Railway 後端]
  finance_db.py   → SQLite（Railway Volume: /data/finance.db）
  finance_api.py  → FastAPI router /finance/*
  gmail_fetcher.py → IMAP + PDF download
  pdf_parser.py   → pypdf + Claude 解析
  stock_prices.py → yfinance 台股/美股
```

---

## 支出類別

```python
CATEGORIES = ["餐飲", "房租", "日常", "娛樂", "教育", "旅遊", "長期規劃", "贈與"]
```

---

## 資料庫 Schema

```sql
-- 交易記錄
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,           -- YYYY-MM-DD
    merchant TEXT NOT NULL,       -- 商家名稱
    amount INTEGER NOT NULL,      -- 新台幣，正數=支出
    currency TEXT DEFAULT 'TWD',  -- TWD / USD / JPY 等
    category TEXT NOT NULL,       -- 8個類別之一
    bank TEXT NOT NULL,           -- 國泰/永豐/第一/其他
    card_last4 TEXT,              -- 卡末4碼
    note TEXT DEFAULT '',
    is_travel INTEGER DEFAULT 0,  -- 1=旅遊（外幣自動標記）
    created_at TEXT DEFAULT (datetime('now'))
);

-- 每月收入
CREATE TABLE income (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year_month TEXT NOT NULL,     -- YYYY-MM
    source TEXT NOT NULL,         -- 薪資/獎金/其他
    amount INTEGER NOT NULL,
    note TEXT DEFAULT ''
);

-- 持股
CREATE TABLE holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL,         -- TW / US
    ticker TEXT NOT NULL,         -- 2330 / AAPL
    name TEXT NOT NULL,           -- 台積電 / Apple
    shares REAL NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 負債
CREATE TABLE liabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,           -- 信貸 / 質押借款
    name TEXT NOT NULL,
    balance INTEGER NOT NULL,     -- 剩餘本金
    monthly_payment INTEGER,      -- 月繳金額（信貸用）
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 現金/存款
CREATE TABLE cash_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,           -- 帳戶名稱
    balance INTEGER NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 淨資產歷史（每月快照）
CREATE TABLE net_worth_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year_month TEXT NOT NULL,
    total_assets INTEGER NOT NULL,
    total_liabilities INTEGER NOT NULL,
    net_worth INTEGER NOT NULL
);
```

---

## 檔案結構

```
line-claude-bot/
  main.py              ← 修改：掛載 finance router，新增 bot 指令處理
  finance_db.py        ← 新建：SQLite 所有 CRUD 操作
  finance_api.py       ← 新建：FastAPI router /finance/*
  gmail_fetcher.py     ← 新建：IMAP 連線 + 下載 PDF 附件
  pdf_parser.py        ← 新建：pypdf 解密 + Claude 解析交易
  stock_prices.py      ← 新建：yfinance 台股/美股即時價格
  requirements.txt     ← 修改：新增 pypdf yfinance
  test_finance_db.py   ← 新建：DB 操作測試
  test_pdf_parser.py   ← 新建：解析邏輯測試

finance-app/
  index.html           ← 新建：PWA 單檔（含 JS/CSS）
  manifest.json        ← 新建：PWA manifest
```

---

## 環境變數（Railway）

```
# 現有
LINE_CHANNEL_ACCESS_TOKEN=...
LINE_CHANNEL_SECRET=...
ANTHROPIC_API_KEY=...

# 新增
GMAIL_USER=jennawang123123@gmail.com
GMAIL_APP_PASSWORD=...        # Gmail App Password（開啟2步驟驗證後產生）
PDF_PASSWORD_ID=...           # 身分證號碼（用於解密銀行 PDF）
FINANCE_API_KEY=...           # 自訂 API key，PWA 呼叫後端用（隨機產生）
DATA_DIR=/data                # Railway Volume 掛載點
```

---

## Phase 1：資料庫與 API 骨架

### Task 1：finance_db.py — SQLite CRUD

**Files:**
- Create: `line-claude-bot/finance_db.py`
- Create: `line-claude-bot/test_finance_db.py`

- [ ] **Step 1: 寫失敗測試**

```python
# test_finance_db.py
import os, pytest
os.environ["DATA_DIR"] = "/tmp/test_finance"

from finance_db import FinanceDB

@pytest.fixture
def db(tmp_path):
    d = FinanceDB(str(tmp_path / "test.db"))
    d.init()
    return d

def test_insert_and_list_transactions(db):
    db.insert_transaction({
        "date": "2026-05-01",
        "merchant": "麥當勞",
        "amount": 125,
        "currency": "TWD",
        "category": "餐飲",
        "bank": "永豐",
        "card_last4": "9908",
        "note": "",
        "is_travel": 0,
    })
    rows = db.list_transactions(year_month="2026-05")
    assert len(rows) == 1
    assert rows[0]["merchant"] == "麥當勞"

def test_update_transaction_category(db):
    db.insert_transaction({"date":"2026-05-01","merchant":"Netflix","amount":330,
                           "currency":"TWD","category":"日常","bank":"國泰","card_last4":"2465","note":"","is_travel":0})
    rows = db.list_transactions(year_month="2026-05")
    db.update_category(rows[0]["id"], "娛樂")
    updated = db.list_transactions(year_month="2026-05")
    assert updated[0]["category"] == "娛樂"

def test_income_crud(db):
    db.upsert_income("2026-05", "薪資", 80000)
    income = db.list_income("2026-05")
    assert income[0]["amount"] == 80000

def test_holdings_crud(db):
    db.upsert_holding("TW", "2330", "台積電", 100)
    holdings = db.list_holdings()
    assert holdings[0]["ticker"] == "2330"

def test_liabilities_crud(db):
    db.upsert_liability("信貸", "玉山信貸", 500000, monthly_payment=23405)
    liabs = db.list_liabilities()
    assert liabs[0]["balance"] == 500000
```

- [ ] **Step 2: 執行確認失敗**

```bash
cd line-claude-bot && python3 -m pytest test_finance_db.py -v
# Expected: ModuleNotFoundError: No module named 'finance_db'
```

- [ ] **Step 3: 實作 finance_db.py**

```python
# finance_db.py
import sqlite3
import os
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    merchant TEXT NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT DEFAULT 'TWD',
    category TEXT NOT NULL,
    bank TEXT NOT NULL,
    card_last4 TEXT DEFAULT '',
    note TEXT DEFAULT '',
    is_travel INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS income (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year_month TEXT NOT NULL,
    source TEXT NOT NULL,
    amount INTEGER NOT NULL,
    note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    shares REAL NOT NULL,
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(market, ticker)
);
CREATE TABLE IF NOT EXISTS liabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    balance INTEGER NOT NULL,
    monthly_payment INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(name)
);
CREATE TABLE IF NOT EXISTS cash_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    balance INTEGER NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS net_worth_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year_month TEXT NOT NULL UNIQUE,
    total_assets INTEGER NOT NULL,
    total_liabilities INTEGER NOT NULL,
    net_worth INTEGER NOT NULL
);
"""

class FinanceDB:
    def __init__(self, path: Optional[str] = None):
        data_dir = os.environ.get("DATA_DIR", "/data")
        os.makedirs(data_dir, exist_ok=True)
        self.path = path or os.path.join(data_dir, "finance.db")

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def insert_transaction(self, tx: dict) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO transactions (date,merchant,amount,currency,category,bank,card_last4,note,is_travel) "
                "VALUES (:date,:merchant,:amount,:currency,:category,:bank,:card_last4,:note,:is_travel)",
                tx
            )
            return cur.lastrowid

    def insert_transactions_batch(self, txs: list[dict]) -> list[int]:
        return [self.insert_transaction(tx) for tx in txs]

    def list_transactions(self, year_month: Optional[str] = None) -> list[dict]:
        with self._conn() as conn:
            if year_month:
                rows = conn.execute(
                    "SELECT * FROM transactions WHERE date LIKE ? ORDER BY date DESC",
                    (f"{year_month}%",)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM transactions ORDER BY date DESC").fetchall()
            return [dict(r) for r in rows]

    def update_category(self, tx_id: int, category: str):
        with self._conn() as conn:
            conn.execute("UPDATE transactions SET category=? WHERE id=?", (category, tx_id))

    def update_note(self, tx_id: int, note: str):
        with self._conn() as conn:
            conn.execute("UPDATE transactions SET note=? WHERE id=?", (note, tx_id))

    def delete_transaction(self, tx_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM transactions WHERE id=?", (tx_id,))

    def upsert_income(self, year_month: str, source: str, amount: int, note: str = ""):
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM income WHERE year_month=? AND source=?", (year_month, source)
            ).fetchone()
            if existing:
                conn.execute("UPDATE income SET amount=?,note=? WHERE id=?", (amount, note, existing["id"]))
            else:
                conn.execute("INSERT INTO income (year_month,source,amount,note) VALUES (?,?,?,?)",
                             (year_month, source, amount, note))

    def list_income(self, year_month: Optional[str] = None) -> list[dict]:
        with self._conn() as conn:
            if year_month:
                rows = conn.execute("SELECT * FROM income WHERE year_month=?", (year_month,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM income ORDER BY year_month DESC").fetchall()
            return [dict(r) for r in rows]

    def upsert_holding(self, market: str, ticker: str, name: str, shares: float):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO holdings (market,ticker,name,shares) VALUES (?,?,?,?) "
                "ON CONFLICT(market,ticker) DO UPDATE SET name=excluded.name, shares=excluded.shares, updated_at=datetime('now')",
                (market, ticker, name, shares)
            )

    def list_holdings(self) -> list[dict]:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM holdings ORDER BY market,ticker").fetchall()]

    def upsert_liability(self, type_: str, name: str, balance: int, monthly_payment: int = 0):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO liabilities (type,name,balance,monthly_payment) VALUES (?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET balance=excluded.balance, monthly_payment=excluded.monthly_payment, updated_at=datetime('now')",
                (type_, name, balance, monthly_payment)
            )

    def list_liabilities(self) -> list[dict]:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM liabilities").fetchall()]

    def upsert_cash(self, name: str, balance: int):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO cash_accounts (name,balance) VALUES (?,?) "
                "ON CONFLICT(name) DO UPDATE SET balance=excluded.balance, updated_at=datetime('now')",
                (name, balance)
            )

    def list_cash(self) -> list[dict]:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM cash_accounts").fetchall()]

    def save_net_worth_snapshot(self, year_month: str, assets: int, liabilities: int):
        net = assets - liabilities
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO net_worth_history (year_month,total_assets,total_liabilities,net_worth) VALUES (?,?,?,?) "
                "ON CONFLICT(year_month) DO UPDATE SET total_assets=excluded.total_assets, "
                "total_liabilities=excluded.total_liabilities, net_worth=excluded.net_worth",
                (year_month, assets, liabilities, net)
            )

    def list_net_worth_history(self) -> list[dict]:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM net_worth_history ORDER BY year_month").fetchall()]

    def monthly_summary(self, year_month: str) -> dict:
        txs = self.list_transactions(year_month)
        by_category: dict[str, int] = {}
        for tx in txs:
            by_category[tx["category"]] = by_category.get(tx["category"], 0) + tx["amount"]
        total_expense = sum(tx["amount"] for tx in txs)
        income_rows = self.list_income(year_month)
        total_income = sum(r["amount"] for r in income_rows)
        return {
            "year_month": year_month,
            "total_expense": total_expense,
            "total_income": total_income,
            "balance": total_income - total_expense,
            "by_category": by_category,
        }
```

- [ ] **Step 4: 執行確認通過**

```bash
python3 -m pytest test_finance_db.py -v
# Expected: 5 passed
```

- [ ] **Step 5: Commit**

```bash
git add line-claude-bot/finance_db.py line-claude-bot/test_finance_db.py
git commit -m "feat: add FinanceDB with SQLite CRUD for transactions/income/holdings/liabilities"
```

---

### Task 2：finance_api.py — FastAPI REST Router

**Files:**
- Create: `line-claude-bot/finance_api.py`

- [ ] **Step 1: 實作 finance_api.py**

```python
# finance_api.py
import os
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from finance_db import FinanceDB

router = APIRouter(prefix="/finance")
db = FinanceDB()

FINANCE_API_KEY = os.environ.get("FINANCE_API_KEY", "")

def _auth(x_api_key: str = Header(None)):
    if FINANCE_API_KEY and x_api_key != FINANCE_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

# --- Transactions ---

class TransactionIn(BaseModel):
    date: str
    merchant: str
    amount: int
    currency: str = "TWD"
    category: str
    bank: str
    card_last4: str = ""
    note: str = ""
    is_travel: int = 0

class CategoryUpdate(BaseModel):
    category: str

class NoteUpdate(BaseModel):
    note: str

@router.get("/transactions")
def get_transactions(year_month: Optional[str] = None, x_api_key: str = Header(None)):
    _auth(x_api_key)
    return db.list_transactions(year_month)

@router.post("/transactions")
def post_transaction(tx: TransactionIn, x_api_key: str = Header(None)):
    _auth(x_api_key)
    new_id = db.insert_transaction(tx.model_dump())
    return {"id": new_id}

@router.post("/transactions/batch")
def post_transactions_batch(txs: list[TransactionIn], x_api_key: str = Header(None)):
    _auth(x_api_key)
    ids = db.insert_transactions_batch([t.model_dump() for t in txs])
    return {"ids": ids, "count": len(ids)}

@router.patch("/transactions/{tx_id}/category")
def patch_category(tx_id: int, body: CategoryUpdate, x_api_key: str = Header(None)):
    _auth(x_api_key)
    db.update_category(tx_id, body.category)
    return {"ok": True}

@router.patch("/transactions/{tx_id}/note")
def patch_note(tx_id: int, body: NoteUpdate, x_api_key: str = Header(None)):
    _auth(x_api_key)
    db.update_note(tx_id, body.note)
    return {"ok": True}

@router.delete("/transactions/{tx_id}")
def delete_transaction(tx_id: int, x_api_key: str = Header(None)):
    _auth(x_api_key)
    db.delete_transaction(tx_id)
    return {"ok": True}

@router.get("/summary/{year_month}")
def get_summary(year_month: str, x_api_key: str = Header(None)):
    _auth(x_api_key)
    return db.monthly_summary(year_month)

# --- Income ---

class IncomeIn(BaseModel):
    year_month: str
    source: str
    amount: int
    note: str = ""

@router.get("/income")
def get_income(year_month: Optional[str] = None, x_api_key: str = Header(None)):
    _auth(x_api_key)
    return db.list_income(year_month)

@router.post("/income")
def post_income(inc: IncomeIn, x_api_key: str = Header(None)):
    _auth(x_api_key)
    db.upsert_income(inc.year_month, inc.source, inc.amount, inc.note)
    return {"ok": True}

# --- Holdings ---

class HoldingIn(BaseModel):
    market: str   # TW or US
    ticker: str
    name: str
    shares: float

@router.get("/holdings")
def get_holdings(x_api_key: str = Header(None)):
    _auth(x_api_key)
    return db.list_holdings()

@router.post("/holdings")
def post_holding(h: HoldingIn, x_api_key: str = Header(None)):
    _auth(x_api_key)
    db.upsert_holding(h.market, h.ticker, h.name, h.shares)
    return {"ok": True}

# --- Liabilities ---

class LiabilityIn(BaseModel):
    type: str
    name: str
    balance: int
    monthly_payment: int = 0

@router.get("/liabilities")
def get_liabilities(x_api_key: str = Header(None)):
    _auth(x_api_key)
    return db.list_liabilities()

@router.post("/liabilities")
def post_liability(l: LiabilityIn, x_api_key: str = Header(None)):
    _auth(x_api_key)
    db.upsert_liability(l.type, l.name, l.balance, l.monthly_payment)
    return {"ok": True}

# --- Cash ---

class CashIn(BaseModel):
    name: str
    balance: int

@router.get("/cash")
def get_cash(x_api_key: str = Header(None)):
    _auth(x_api_key)
    return db.list_cash()

@router.post("/cash")
def post_cash(c: CashIn, x_api_key: str = Header(None)):
    _auth(x_api_key)
    db.upsert_cash(c.name, c.balance)
    return {"ok": True}

# --- Net Worth ---

@router.get("/networth/history")
def get_networth_history(x_api_key: str = Header(None)):
    _auth(x_api_key)
    return db.list_net_worth_history()

class NetWorthSnapshotIn(BaseModel):
    year_month: str
    total_assets: int
    total_liabilities: int

@router.post("/networth/snapshot")
def post_networth_snapshot(s: NetWorthSnapshotIn, x_api_key: str = Header(None)):
    _auth(x_api_key)
    db.save_net_worth_snapshot(s.year_month, s.total_assets, s.total_liabilities)
    return {"ok": True}

# --- Stock Prices ---

@router.get("/stock-price")
def get_stock_price(ticker: str, market: str, x_api_key: str = Header(None)):
    _auth(x_api_key)
    from stock_prices import get_price
    price = get_price(ticker, market)
    return {"ticker": ticker, "market": market, "price": price}
```

- [ ] **Step 2: 在 main.py 掛載 router 並初始化 DB**

修改 `line-claude-bot/main.py`，在 `app = FastAPI()` 之後加入：

```python
# main.py 頂部新增 import
from finance_api import router as finance_router
from finance_db import FinanceDB

# app = FastAPI() 之後加入
_db = FinanceDB()
_db.init()
app.include_router(finance_router)
```

- [ ] **Step 3: Commit**

```bash
git add line-claude-bot/finance_api.py line-claude-bot/main.py
git commit -m "feat: add /finance/* REST API router with auth"
```

---

### Task 3：stock_prices.py — 台股/美股即時價格

**Files:**
- Create: `line-claude-bot/stock_prices.py`

- [ ] **Step 1: 新增 yfinance 到 requirements.txt**

```
fastapi
uvicorn[standard]
anthropic
httpx
pytest
pytest-asyncio
pypdf
yfinance
```

- [ ] **Step 2: 實作 stock_prices.py**

```python
# stock_prices.py
import yfinance as yf
import logging

def get_price(ticker: str, market: str) -> float:
    """
    market: 'TW' or 'US'
    TW ticker: '2330' → yfinance uses '2330.TW'
    US ticker: 'AAPL' → yfinance uses 'AAPL'
    Returns price in local currency (TWD for TW, USD for US).
    Returns 0.0 on failure.
    """
    yf_ticker = f"{ticker}.TW" if market == "TW" else ticker
    try:
        data = yf.Ticker(yf_ticker)
        hist = data.history(period="1d")
        if hist.empty:
            logging.warning("yfinance: no data for %s", yf_ticker)
            return 0.0
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        logging.error("yfinance error for %s: %s", yf_ticker, e)
        return 0.0
```

- [ ] **Step 3: 手動測試**

```bash
cd line-claude-bot
python3 -c "from stock_prices import get_price; print(get_price('2330','TW')); print(get_price('AAPL','US'))"
# Expected: 台積電現價（約700-1000）, Apple現價（約200+）
```

- [ ] **Step 4: Commit**

```bash
git add line-claude-bot/stock_prices.py line-claude-bot/requirements.txt
git commit -m "feat: add stock price fetcher for TW/US markets via yfinance"
```

---

## Phase 2：Gmail PDF 解析管線

### Task 4：gmail_fetcher.py — IMAP 下載 PDF 附件

**Files:**
- Create: `line-claude-bot/gmail_fetcher.py`

**前置條件：**
1. Gmail 帳號開啟「兩步驟驗證」
2. 產生「應用程式密碼」→ 設為 Railway 環境變數 `GMAIL_APP_PASSWORD`
3. Gmail 設定 → 轉寄和 POP/IMAP → 啟用 IMAP

- [ ] **Step 1: 實作 gmail_fetcher.py**

```python
# gmail_fetcher.py
import imaplib
import email
import os
import re
import logging
from datetime import datetime, timedelta

GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

# 銀行寄件人關鍵字（IMAP FROM 搜尋）
BANK_SENDERS = {
    "國泰": "cathaybk",
    "永豐": "banksinopac",
    "第一": "firstbank",
}

def fetch_bank_pdfs(since_days: int = 45) -> list[dict]:
    """
    Returns list of: {bank, filename, data: bytes}
    Searches emails from the last `since_days` days.
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise ValueError("GMAIL_USER and GMAIL_APP_PASSWORD env vars required")

    since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
    results = []

    with imaplib.IMAP4_SSL("imap.gmail.com") as imap:
        imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        imap.select("INBOX")

        for bank_name, sender_keyword in BANK_SENDERS.items():
            _, msg_ids = imap.search(
                None,
                f'(FROM "{sender_keyword}" SINCE {since_date})'
            )
            for msg_id in msg_ids[0].split():
                _, data = imap.fetch(msg_id, "(RFC822)")
                msg = email.message_from_bytes(data[0][1])
                for part in msg.walk():
                    if part.get_content_type() == "application/pdf":
                        filename = part.get_filename() or f"{bank_name}_statement.pdf"
                        pdf_bytes = part.get_payload(decode=True)
                        results.append({
                            "bank": bank_name,
                            "filename": filename,
                            "data": pdf_bytes,
                        })
                        logging.info("Found PDF: bank=%s filename=%s size=%d", bank_name, filename, len(pdf_bytes))

    return results
```

- [ ] **Step 2: Commit**

```bash
git add line-claude-bot/gmail_fetcher.py
git commit -m "feat: add IMAP Gmail PDF fetcher for bank statements"
```

---

### Task 5：pdf_parser.py — 解密 + Claude 解析交易

**Files:**
- Create: `line-claude-bot/pdf_parser.py`
- Create: `line-claude-bot/test_pdf_parser.py`

- [ ] **Step 1: 寫解析邏輯測試**

```python
# test_pdf_parser.py
from pdf_parser import parse_transactions_from_text

# 永豐格式的文字範例
SAMPLE_SINOPAC = """
2026/05/31  麥當勞                   60
2026/05/30  全聯福利中心             320
2026/05/29  NETFLIX                  330
2026/05/28  COLES 5587             1,653
"""

# 國泰格式的文字範例
SAMPLE_CATHAY = """
05/28  餐飲                          125
05/27  便利商店                       45
05/26  TfNSW Opal Fare               23
"""

def test_parse_sinopac():
    txs = parse_transactions_from_text(SAMPLE_SINOPAC, bank="永豐", year_month="2026-05")
    assert len(txs) == 4
    assert txs[0]["merchant"] == "麥當勞"
    assert txs[0]["amount"] == 60
    assert txs[3]["is_travel"] == 1  # 外幣商家

def test_parse_foreign_merchant():
    txs = parse_transactions_from_text(SAMPLE_CATHAY, bank="國泰", year_month="2026-05")
    opal = next(t for t in txs if "Opal" in t["merchant"])
    assert opal["is_travel"] == 1
```

- [ ] **Step 2: 確認測試失敗**

```bash
python3 -m pytest test_pdf_parser.py -v
# Expected: ImportError
```

- [ ] **Step 3: 實作 pdf_parser.py**

```python
# pdf_parser.py
import os
import re
import json
import logging
import anthropic
from pypdf import PdfReader
from io import BytesIO

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
PDF_PASSWORD = os.environ.get("PDF_PASSWORD_ID", "")

CATEGORIES = ["餐飲", "房租", "日常", "娛樂", "教育", "旅遊", "長期規劃", "贈與"]

# 外幣/英文商家 → 自動標記旅遊
FOREIGN_PATTERN = re.compile(r"[A-Za-z]{3,}")

claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def extract_pdf_text(pdf_bytes: bytes, password: str = "") -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    if reader.is_encrypted:
        result = reader.decrypt(password or PDF_PASSWORD)
        if result == 0:
            raise ValueError("PDF decryption failed — wrong password")
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def _is_foreign_merchant(merchant: str) -> bool:
    return bool(FOREIGN_PATTERN.search(merchant))


def parse_transactions_from_text(text: str, bank: str, year_month: str) -> list[dict]:
    """Use Claude to extract and categorize transactions from PDF text."""
    year = year_month[:4]

    prompt = f"""以下是{bank}信用卡{year_month}對帳單文字。
請提取所有消費交易，輸出 JSON 陣列，每筆格式：
{{"date":"YYYY-MM-DD","merchant":"商家名稱","amount":金額整數,"currency":"TWD","category":"類別"}}

類別只能選以下之一：{', '.join(CATEGORIES)}
- 麥當勞/全家/7-11/餐廳/咖啡等 → 餐飲
- 房租/管理費 → 房租
- Netflix/Spotify/KTV/電影 → 娛樂
- 書店/補習/學費 → 教育
- 英文商家名稱（COLES/Opal/USD消費等）→ 旅遊
- 保費/定存/投資 → 長期規劃
- 禮品/包裹/婚喪 → 贈與
- 其他 → 日常

year={year}，若對帳單只有月日，補足年份。
amount 只取新台幣金額整數（已換算後）。忽略紅利折抵/手續費/退款等非消費項目。

對帳單文字：
{text[:6000]}

只輸出 JSON 陣列，不要其他文字。"""

    response = claude_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    # 去掉 markdown code block
    raw = re.sub(r"^```json\s*|^```\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()

    try:
        txs = json.loads(raw)
    except json.JSONDecodeError as e:
        logging.error("JSON parse error: %s\nRaw: %s", e, raw[:500])
        return []

    for tx in txs:
        tx["bank"] = bank
        tx["card_last4"] = ""
        tx["note"] = ""
        tx["is_travel"] = 1 if (_is_foreign_merchant(tx.get("merchant", "")) or tx.get("category") == "旅遊") else 0
        if tx["is_travel"]:
            tx["category"] = "旅遊"

    return txs


def parse_pdf(pdf_bytes: bytes, bank: str, year_month: str, password: str = "") -> list[dict]:
    text = extract_pdf_text(pdf_bytes, password)
    logging.info("Extracted %d chars from %s PDF", len(text), bank)
    return parse_transactions_from_text(text, bank, year_month)
```

- [ ] **Step 4: 執行測試**

```bash
python3 -m pytest test_pdf_parser.py -v
# Expected: 2 passed
```

- [ ] **Step 5: Commit**

```bash
git add line-claude-bot/pdf_parser.py line-claude-bot/test_pdf_parser.py
git commit -m "feat: add PDF parser with pypdf decrypt + Claude categorization"
```

---

### Task 6：LINE Bot — 「處理對帳單」指令

**Files:**
- Modify: `line-claude-bot/main.py`

- [ ] **Step 1: 在 main.py 新增對帳單處理函式**

在 `process_event` 函式之前插入：

```python
# main.py 頂部新增 import
import calendar
from datetime import datetime
from gmail_fetcher import fetch_bank_pdfs
from pdf_parser import parse_pdf
from finance_db import FinanceDB

_finance_db = FinanceDB()
_finance_db.init()

# 暫存待確認的交易（in-memory，user_id → list[dict]）
_pending_transactions: dict[str, list[dict]] = {}

async def handle_statement_command(user_id: str, reply_token: str) -> None:
    """處理對帳單指令：下載 PDF → 解析 → 回傳預覽"""
    await send_reply(reply_token, ["⏳ 正在從 Gmail 下載對帳單，請稍候..."])

    now = datetime.now()
    year_month = f"{now.year}-{now.month-1:02d}" if now.month > 1 else f"{now.year-1}-12"

    try:
        pdfs = fetch_bank_pdfs(since_days=45)
    except Exception as e:
        await push_message(user_id, [f"❌ Gmail 連線失敗：{e}"])
        return

    if not pdfs:
        await push_message(user_id, ["找不到近期銀行對帳單 PDF。請確認 Gmail 中有附件信件。"])
        return

    all_txs = []
    for pdf_info in pdfs:
        try:
            txs = parse_pdf(pdf_info["data"], pdf_info["bank"], year_month)
            all_txs.extend(txs)
        except Exception as e:
            logging.error("parse_pdf error bank=%s: %s", pdf_info["bank"], e)

    if not all_txs:
        await push_message(user_id, ["⚠️ 解析失敗，找不到交易記錄。請確認 PDF 密碼設定。"])
        return

    _pending_transactions[user_id] = all_txs

    # 預覽前20筆
    lines = [f"📊 找到 {len(all_txs)} 筆交易（{year_month}）：\n"]
    for i, tx in enumerate(all_txs[:20], 1):
        travel_mark = "✈️" if tx["is_travel"] else ""
        lines.append(f"{i}. {tx['date'][5:]} {tx['merchant']} NT${tx['amount']:,} → {tx['category']}{travel_mark}")

    if len(all_txs) > 20:
        lines.append(f"...（共{len(all_txs)}筆）")

    lines.append("\n回覆「確認」全部存入")
    lines.append("或「改 3 娛樂」修改第3筆類別")

    await push_message(user_id, ["\n".join(lines)])


async def handle_confirm_command(user_id: str) -> None:
    txs = _pending_transactions.pop(user_id, None)
    if not txs:
        await push_message(user_id, ["沒有待確認的交易。請先輸入「處理對帳單」。"])
        return
    ids = _finance_db.insert_transactions_batch(txs)
    await push_message(user_id, [f"✅ 已存入 {len(ids)} 筆交易。"])


async def handle_edit_command(user_id: str, text: str) -> None:
    """解析「改 3 娛樂」格式"""
    m = re.match(r"改\s*(\d+)\s+(.+)", text.strip())
    if not m:
        await push_message(user_id, ["格式：改 [編號] [類別]，例如：改 3 娛樂"])
        return
    idx = int(m.group(1)) - 1
    new_cat = m.group(2).strip()
    if new_cat not in ["餐飲","房租","日常","娛樂","教育","旅遊","長期規劃","贈與"]:
        await push_message(user_id, [f"類別錯誤，請選：餐飲/房租/日常/娛樂/教育/旅遊/長期規劃/贈與"])
        return
    txs = _pending_transactions.get(user_id)
    if not txs or idx < 0 or idx >= len(txs):
        await push_message(user_id, ["編號超出範圍，請重新輸入「處理對帳單」。"])
        return
    txs[idx]["category"] = new_cat
    await push_message(user_id, [f"✏️ 第{idx+1}筆已改為「{new_cat}」，輸入「確認」存入。"])
```

- [ ] **Step 2: 修改 process_event 加入指令路由**

在 `process_event` 函式的 reset 判斷之後、`add_message` 之前插入：

```python
async def process_event(user_id: str, reply_token: str, user_text: str) -> None:
    if user_text.strip() in ("新病人", "/reset", "reset"):
        history[user_id] = []
        await send_reply(reply_token, ["已清除對話記錄，請開始描述新病人。"])
        return

    # 財務指令
    if user_text.strip() == "處理對帳單":
        await handle_statement_command(user_id, reply_token)
        return
    if user_text.strip() == "確認":
        await send_reply(reply_token, ["處理中..."])
        await handle_confirm_command(user_id)
        return
    if user_text.strip().startswith("改 ") or user_text.strip().startswith("改"):
        if re.match(r"改\s*\d+", user_text.strip()):
            await send_reply(reply_token, ["處理中..."])
            await handle_edit_command(user_id, user_text)
            return

    # 原有醫療 CPS 流程
    add_message(user_id, "user", user_text)
    # ... 下面不變
```

- [ ] **Step 3: 確認 main.py 頂部 import `re` 已存在**

main.py 已有 `import re` 的使用，若無則加入。

- [ ] **Step 4: Commit**

```bash
git add line-claude-bot/main.py
git commit -m "feat: add LINE bot commands for bank statement processing (處理對帳單/確認/改)"
```

---

## Phase 3：PWA 前端

### Task 7：PWA 骨架 + Tab 1 支出

**Files:**
- Create: `finance-app/index.html`
- Create: `finance-app/manifest.json`

- [ ] **Step 1: 建立 manifest.json**

```json
{
  "name": "財務管理",
  "short_name": "財務",
  "start_url": "/finance-app/index.html",
  "display": "standalone",
  "background_color": "#1a1a2e",
  "theme_color": "#16213e",
  "icons": [
    {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"}
  ]
}
```

- [ ] **Step 2: 建立 finance-app/index.html（Phase 3 完整版，見下方 Task 8-10）**

先建立骨架：

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<meta name="theme-color" content="#16213e">
<link rel="manifest" href="manifest.json">
<title>財務管理</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       background: #1a1a2e; color: #e0e0e0; min-height: 100vh; }

/* Tabs */
.tab-bar { display: flex; background: #16213e; position: sticky; top: 0; z-index: 100;
           border-bottom: 1px solid #0f3460; }
.tab-btn { flex: 1; padding: 14px 0; background: none; border: none; color: #888;
           font-size: 14px; cursor: pointer; transition: color 0.2s; }
.tab-btn.active { color: #e94560; border-bottom: 2px solid #e94560; }

.tab-content { display: none; padding: 16px; }
.tab-content.active { display: block; }

/* Cards */
.card { background: #16213e; border-radius: 12px; padding: 16px; margin-bottom: 12px; }
.card-title { font-size: 12px; color: #888; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
.card-value { font-size: 24px; font-weight: 700; color: #e0e0e0; }
.card-value.income { color: #4ade80; }
.card-value.expense { color: #f87171; }
.card-value.balance { color: #60a5fa; }

/* Month selector */
.month-selector { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.month-selector select { background: #16213e; color: #e0e0e0; border: 1px solid #0f3460;
                          border-radius: 8px; padding: 8px 12px; font-size: 14px; flex: 1; }

/* Transaction list */
.tx-list { list-style: none; }
.tx-item { background: #16213e; border-radius: 10px; padding: 12px; margin-bottom: 8px;
           display: flex; align-items: center; gap: 12px; }
.tx-icon { width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center;
           justify-content: center; font-size: 18px; flex-shrink: 0; }
.tx-info { flex: 1; min-width: 0; }
.tx-merchant { font-size: 15px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tx-meta { font-size: 12px; color: #888; margin-top: 2px; }
.tx-amount { font-size: 16px; font-weight: 700; color: #f87171; white-space: nowrap; }
.tx-category-badge { font-size: 11px; background: #0f3460; color: #60a5fa;
                     padding: 2px 8px; border-radius: 20px; cursor: pointer; }

/* Category icons */
.cat-餐飲 { background: #7c3aed22; }
.cat-房租 { background: #d9770622; }
.cat-日常 { background: #04748222; }
.cat-娛樂 { background: #e9456022; }
.cat-教育 { background: #06745822; }
.cat-旅遊 { background: #0369a122; }
.cat-長期規劃 { background: #71717a22; }
.cat-贈與 { background: #db277722; }

/* Modal */
.modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7);
                 z-index: 1000; align-items: flex-end; justify-content: center; }
.modal-overlay.open { display: flex; }
.modal { background: #16213e; border-radius: 20px 20px 0 0; padding: 24px; width: 100%;
         max-height: 80vh; overflow-y: auto; }
.modal h3 { font-size: 18px; margin-bottom: 16px; }
.modal-btn { width: 100%; padding: 12px; margin-bottom: 8px; background: #0f3460; color: #e0e0e0;
             border: none; border-radius: 10px; font-size: 15px; cursor: pointer; text-align: left; }
.modal-btn:active { background: #e94560; color: white; }
.modal-close { color: #888; font-size: 14px; text-align: center; padding: 8px; cursor: pointer; width: 100%; background: none; border: none; }

/* Chart container */
.chart-container { position: relative; height: 200px; margin: 16px 0; }

/* Form elements */
input, select { background: #0f3460; color: #e0e0e0; border: 1px solid #1e3a5f;
                border-radius: 8px; padding: 10px 12px; font-size: 14px; width: 100%; }
.btn-primary { background: #e94560; color: white; border: none; border-radius: 10px;
               padding: 12px 24px; font-size: 15px; cursor: pointer; width: 100%; margin-top: 12px; }
.btn-secondary { background: #0f3460; color: #e0e0e0; border: none; border-radius: 10px;
                 padding: 10px 24px; font-size: 14px; cursor: pointer; }

/* Summary grid */
.summary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }
.summary-grid .card { margin-bottom: 0; }

/* Settings */
.settings-section { margin-bottom: 20px; }
.settings-section h4 { font-size: 13px; color: #888; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
.settings-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.settings-row input { flex: 1; }
.settings-row .btn-secondary { white-space: nowrap; flex-shrink: 0; }

/* Net worth display */
.networth-big { text-align: center; padding: 20px; }
.networth-big .label { font-size: 13px; color: #888; margin-bottom: 4px; }
.networth-big .value { font-size: 36px; font-weight: 800; }
.networth-big .value.positive { color: #4ade80; }
.networth-big .value.negative { color: #f87171; }

/* Stock row */
.stock-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #0f3460; }
.stock-ticker { font-size: 14px; font-weight: 700; color: #60a5fa; }
.stock-name { font-size: 12px; color: #888; }
.stock-value { text-align: right; }
.stock-price { font-size: 14px; font-weight: 600; }
.stock-shares { font-size: 11px; color: #888; }

/* FAB */
.fab { position: fixed; bottom: 24px; right: 24px; width: 56px; height: 56px;
       background: #e94560; border: none; border-radius: 50%; color: white;
       font-size: 28px; cursor: pointer; box-shadow: 0 4px 12px rgba(233,69,96,0.4);
       display: flex; align-items: center; justify-content: center; z-index: 50; }

.loading { color: #888; font-size: 14px; text-align: center; padding: 32px; }
</style>
</head>
<body>

<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('expenses')">💸 支出</button>
  <button class="tab-btn" onclick="switchTab('cashflow')">📈 收支</button>
  <button class="tab-btn" onclick="switchTab('assets')">🏦 總資產</button>
</div>

<!-- Tab 1: 支出 -->
<div id="tab-expenses" class="tab-content active">
  <div class="month-selector">
    <select id="expense-month" onchange="loadExpenses()"></select>
  </div>
  <div class="summary-grid">
    <div class="card">
      <div class="card-title">本月支出</div>
      <div class="card-value expense" id="total-expense">--</div>
    </div>
    <div class="card">
      <div class="card-title">筆數</div>
      <div class="card-value" id="total-count">--</div>
    </div>
  </div>
  <div class="card">
    <div class="card-title">類別分佈</div>
    <div class="chart-container"><canvas id="category-chart"></canvas></div>
  </div>
  <ul class="tx-list" id="tx-list">
    <li class="loading">載入中...</li>
  </ul>
</div>

<!-- Tab 2: 收支 -->
<div id="tab-cashflow" class="tab-content">
  <div class="month-selector">
    <select id="cashflow-month" onchange="loadCashflow()"></select>
  </div>
  <div class="summary-grid">
    <div class="card">
      <div class="card-title">收入</div>
      <div class="card-value income" id="cf-income">--</div>
    </div>
    <div class="card">
      <div class="card-title">支出</div>
      <div class="card-value expense" id="cf-expense">--</div>
    </div>
  </div>
  <div class="card">
    <div class="card-title">結餘</div>
    <div class="card-value balance" id="cf-balance" style="font-size:32px">--</div>
  </div>
  <div class="card">
    <div class="card-title">月度趨勢（近12個月）</div>
    <div class="chart-container"><canvas id="cashflow-chart"></canvas></div>
  </div>
  <div class="card">
    <div class="card-title">本月收入明細</div>
    <div id="income-list"></div>
  </div>
</div>

<!-- Tab 3: 總資產 -->
<div id="tab-assets" class="tab-content">
  <div class="networth-big">
    <div class="label">淨資產</div>
    <div class="value" id="net-worth-value">--</div>
  </div>
  <div class="card">
    <div class="card-title">資產走勢</div>
    <div class="chart-container"><canvas id="networth-chart"></canvas></div>
  </div>

  <div class="card">
    <div class="card-title" style="display:flex;justify-content:space-between">
      <span>台股</span>
      <button class="btn-secondary" style="padding:4px 10px;font-size:12px" onclick="refreshPrices('TW')">更新價格</button>
    </div>
    <div id="tw-stocks"></div>
  </div>
  <div class="card">
    <div class="card-title" style="display:flex;justify-content:space-between">
      <span>美股</span>
      <button class="btn-secondary" style="padding:4px 10px;font-size:12px" onclick="refreshPrices('US')">更新價格</button>
    </div>
    <div id="us-stocks"></div>
  </div>
  <div class="card">
    <div class="card-title">存款/現金</div>
    <div id="cash-list"></div>
  </div>
  <div class="card">
    <div class="card-title" style="color:#f87171">負債</div>
    <div id="liability-list"></div>
  </div>

  <div style="margin-top:16px;display:flex;gap:8px">
    <button class="btn-secondary" style="flex:1" onclick="openAssetModal()">✏️ 編輯資產</button>
    <button class="btn-secondary" style="flex:1" onclick="saveNetworthSnapshot()">📸 快照</button>
  </div>
</div>

<!-- Category Edit Modal -->
<div class="modal-overlay" id="cat-modal">
  <div class="modal">
    <h3>變更類別</h3>
    <div id="cat-modal-buttons"></div>
    <button class="modal-close" onclick="closeModal('cat-modal')">取消</button>
  </div>
</div>

<!-- Income Modal -->
<div class="modal-overlay" id="income-modal">
  <div class="modal">
    <h3>新增收入</h3>
    <div style="display:flex;flex-direction:column;gap:10px">
      <input id="inc-source" placeholder="來源（薪資/獎金/其他）" />
      <input id="inc-amount" type="number" placeholder="金額" />
      <input id="inc-note" placeholder="備註（選填）" />
    </div>
    <button class="btn-primary" onclick="submitIncome()">存入</button>
    <button class="modal-close" onclick="closeModal('income-modal')">取消</button>
  </div>
</div>

<!-- Asset Edit Modal -->
<div class="modal-overlay" id="asset-modal">
  <div class="modal">
    <h3>編輯資產/負債</h3>
    <div id="asset-modal-content"></div>
    <button class="modal-close" onclick="closeModal('asset-modal')">關閉</button>
  </div>
</div>

<!-- FAB（依tab顯示不同） -->
<button class="fab" id="fab" onclick="fabAction()">＋</button>

<script>
// ============================================================
// CONFIG
// ============================================================
const API_BASE = localStorage.getItem('apiBase') || '';
const API_KEY = localStorage.getItem('apiKey') || '';

function apiHeaders() {
  return { 'Content-Type': 'application/json', 'x-api-key': API_KEY };
}

async function apiFetch(path, opts = {}) {
  const url = API_BASE + path;
  const res = await fetch(url, { headers: apiHeaders(), ...opts });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

// ============================================================
// TABS
// ============================================================
let currentTab = 'expenses';
function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach((b, i) => {
    const tabs = ['expenses','cashflow','assets'];
    b.classList.toggle('active', tabs[i] === tab);
  });
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');
  currentTab = tab;
  if (tab === 'expenses') loadExpenses();
  else if (tab === 'cashflow') loadCashflow();
  else if (tab === 'assets') loadAssets();
}

// ============================================================
// MONTH HELPERS
// ============================================================
function getMonthOptions(selectId, onchange) {
  const sel = document.getElementById(selectId);
  if (sel.options.length > 0) return sel.value;
  const now = new Date();
  for (let i = 0; i < 24; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const val = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;
    const opt = new Option(val, val);
    sel.add(opt);
  }
  return sel.value;
}

// ============================================================
// TAB 1: 支出
// ============================================================
let categoryChart = null;
let editingTxId = null;

async function loadExpenses() {
  if (!API_BASE) { showSetupPrompt(); return; }
  const ym = getMonthOptions('expense-month');
  document.getElementById('tx-list').innerHTML = '<li class="loading">載入中...</li>';
  try {
    const txs = await apiFetch(`/finance/transactions?year_month=${ym}`);
    renderExpenses(txs, ym);
  } catch(e) { document.getElementById('tx-list').innerHTML = `<li class="loading">錯誤：${e.message}</li>`; }
}

const CAT_ICONS = {
  '餐飲':'🍜','房租':'🏠','日常':'🛒','娛樂':'🎬',
  '教育':'📚','旅遊':'✈️','長期規劃':'💰','贈與':'🎁'
};

function renderExpenses(txs, ym) {
  const total = txs.reduce((s,t) => s + t.amount, 0);
  document.getElementById('total-expense').textContent = `NT$${total.toLocaleString()}`;
  document.getElementById('total-count').textContent = `${txs.length} 筆`;

  // Category chart
  const catTotals = {};
  txs.forEach(t => { catTotals[t.category] = (catTotals[t.category]||0) + t.amount; });
  const cats = Object.keys(catTotals);
  const vals = cats.map(c => catTotals[c]);
  const colors = ['#7c3aed','#d97706','#047482','#e94560','#065857','#0369a1','#71717a','#db2777'];

  if (categoryChart) categoryChart.destroy();
  categoryChart = new Chart(document.getElementById('category-chart'), {
    type: 'doughnut',
    data: { labels: cats, datasets: [{ data: vals, backgroundColor: colors, borderWidth: 0 }] },
    options: { plugins: { legend: { position: 'right', labels: { color: '#e0e0e0', font: { size: 11 } } } },
               cutout: '65%' }
  });

  // List
  const ul = document.getElementById('tx-list');
  ul.innerHTML = '';
  txs.forEach(tx => {
    const li = document.createElement('li');
    li.className = 'tx-item';
    li.innerHTML = `
      <div class="tx-icon cat-${tx.category}">${CAT_ICONS[tx.category]||'💳'}</div>
      <div class="tx-info">
        <div class="tx-merchant">${tx.merchant}</div>
        <div class="tx-meta">${tx.date} · ${tx.bank}
          <span class="tx-category-badge" onclick="openCatModal(${tx.id},'${tx.category}')">${tx.category}</span>
          ${tx.is_travel ? '✈️' : ''}
        </div>
      </div>
      <div class="tx-amount">-NT$${tx.amount.toLocaleString()}</div>
    `;
    ul.appendChild(li);
  });
}

function openCatModal(txId, currentCat) {
  editingTxId = txId;
  const cats = ['餐飲','房租','日常','娛樂','教育','旅遊','長期規劃','贈與'];
  const div = document.getElementById('cat-modal-buttons');
  div.innerHTML = cats.map(c =>
    `<button class="modal-btn" onclick="updateCategory('${c}')">${CAT_ICONS[c]} ${c}${c===currentCat?' ✓':''}</button>`
  ).join('');
  document.getElementById('cat-modal').classList.add('open');
}

async function updateCategory(cat) {
  await apiFetch(`/finance/transactions/${editingTxId}/category`, {
    method: 'PATCH', body: JSON.stringify({ category: cat })
  });
  closeModal('cat-modal');
  loadExpenses();
}

// ============================================================
// TAB 2: 收支
// ============================================================
let cashflowChart = null;

async function loadCashflow() {
  if (!API_BASE) { showSetupPrompt(); return; }
  const ym = getMonthOptions('cashflow-month');
  try {
    const [summary, allIncome] = await Promise.all([
      apiFetch(`/finance/summary/${ym}`),
      apiFetch('/finance/income')
    ]);

    document.getElementById('cf-income').textContent = `NT$${summary.total_income.toLocaleString()}`;
    document.getElementById('cf-expense').textContent = `NT$${summary.total_expense.toLocaleString()}`;
    const bal = summary.balance;
    const balEl = document.getElementById('cf-balance');
    balEl.textContent = `${bal >= 0 ? '+' : ''}NT$${bal.toLocaleString()}`;
    balEl.style.color = bal >= 0 ? '#4ade80' : '#f87171';

    // Income detail
    const monthIncome = allIncome.filter(i => i.year_month === ym);
    document.getElementById('income-list').innerHTML = monthIncome.length
      ? monthIncome.map(i => `<div class="stock-row"><div><div class="stock-ticker">${i.source}</div></div><div class="stock-value"><div class="stock-price" style="color:#4ade80">+NT$${i.amount.toLocaleString()}</div>${i.note?`<div class="stock-shares">${i.note}</div>`:''}</div></div>`).join('')
      : '<div style="color:#888;font-size:14px;padding:8px 0">尚無收入記錄</div>';

    // Trend chart (last 12 months)
    const months = Array.from({length:12}, (_,i) => {
      const d = new Date(); d.setMonth(d.getMonth()-11+i);
      return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;
    });
    const summaries = await Promise.all(months.map(m => apiFetch(`/finance/summary/${m}`)));
    if (cashflowChart) cashflowChart.destroy();
    cashflowChart = new Chart(document.getElementById('cashflow-chart'), {
      type: 'line',
      data: {
        labels: months.map(m => m.slice(5)),
        datasets: [
          { label: '收入', data: summaries.map(s=>s.total_income), borderColor:'#4ade80', tension:0.3, fill:false },
          { label: '支出', data: summaries.map(s=>s.total_expense), borderColor:'#f87171', tension:0.3, fill:false },
          { label: '結餘', data: summaries.map(s=>s.balance), borderColor:'#60a5fa', tension:0.3, fill:false },
        ]
      },
      options: { plugins: { legend: { labels: { color:'#e0e0e0', font:{size:11} } } },
                 scales: { x:{ticks:{color:'#888'}}, y:{ticks:{color:'#888'}} } }
    });
  } catch(e) { console.error(e); }
}

// ============================================================
// TAB 3: 總資產
// ============================================================
let networthChart = null;
const stockPrices = {}; // { 'TW:2330': 850.0 }

async function loadAssets() {
  if (!API_BASE) { showSetupPrompt(); return; }
  try {
    const [holdings, liabilities, cash, history] = await Promise.all([
      apiFetch('/finance/holdings'),
      apiFetch('/finance/liabilities'),
      apiFetch('/finance/cash'),
      apiFetch('/finance/networth/history'),
    ]);

    // Stocks
    await refreshPricesData(holdings);
    renderStocks(holdings);
    renderLiabilities(liabilities);
    renderCash(cash);

    // Net worth calc
    const twTotal = holdings.filter(h=>h.market==='TW').reduce((s,h)=>(s+(stockPrices[`TW:${h.ticker}`]||0)*h.shares),0);
    const usTotal = holdings.filter(h=>h.market==='US').reduce((s,h)=>(s+(stockPrices[`US:${h.ticker}`]||0)*h.shares),0);
    const cashTotal = cash.reduce((s,c)=>s+c.balance,0);
    const totalAssets = Math.round(twTotal + usTotal + cashTotal);
    const totalLiab = liabilities.reduce((s,l)=>s+l.balance,0);
    const netWorth = totalAssets - totalLiab;

    const el = document.getElementById('net-worth-value');
    el.textContent = `NT$${netWorth.toLocaleString()}`;
    el.className = `value ${netWorth >= 0 ? 'positive' : 'negative'}`;

    // History chart
    if (networthChart) networthChart.destroy();
    if (history.length > 1) {
      networthChart = new Chart(document.getElementById('networth-chart'), {
        type: 'line',
        data: {
          labels: history.map(h=>h.year_month.slice(5)),
          datasets: [{ label: '淨資產', data: history.map(h=>h.net_worth),
                       borderColor:'#4ade80', backgroundColor:'rgba(74,222,128,0.1)', fill:true, tension:0.3 }]
        },
        options: { plugins:{legend:{labels:{color:'#e0e0e0'}}},
                   scales:{x:{ticks:{color:'#888'}},y:{ticks:{color:'#888',callback:v=>`${(v/10000).toFixed(0)}萬`}}} }
      });
    }

    // Store for snapshot
    window._currentAssets = totalAssets;
    window._currentLiabilities = totalLiab;
  } catch(e) { console.error(e); }
}

async function refreshPricesData(holdings) {
  const fetches = holdings.map(async h => {
    try {
      const data = await apiFetch(`/finance/stock-price?ticker=${h.ticker}&market=${h.market}`);
      stockPrices[`${h.market}:${h.ticker}`] = data.price;
    } catch(e) { stockPrices[`${h.market}:${h.ticker}`] = 0; }
  });
  await Promise.all(fetches);
}

async function refreshPrices(market) {
  const holdings = await apiFetch('/finance/holdings');
  const filtered = holdings.filter(h=>h.market===market);
  await refreshPricesData(filtered);
  renderStocks(holdings);
}

function renderStocks(holdings) {
  const render = (market, elId, currency) => {
    const h = holdings.filter(h=>h.market===market);
    document.getElementById(elId).innerHTML = h.length
      ? h.map(s => {
          const price = stockPrices[`${market}:${s.ticker}`] || 0;
          const value = Math.round(price * s.shares);
          return `<div class="stock-row">
            <div><div class="stock-ticker">${s.ticker}</div><div class="stock-name">${s.name}</div></div>
            <div class="stock-value">
              <div class="stock-price">NT$${value.toLocaleString()}</div>
              <div class="stock-shares">${s.shares}股 × ${currency}${price.toFixed(market==='US'?2:0)}</div>
            </div>
          </div>`;
        }).join('')
      : '<div style="color:#888;font-size:14px;padding:8px 0">尚未設定</div>';
  };
  render('TW', 'tw-stocks', 'NT$');
  render('US', 'us-stocks', 'USD ');
}

function renderLiabilities(liabs) {
  document.getElementById('liability-list').innerHTML = liabs.length
    ? liabs.map(l => `<div class="stock-row">
        <div><div class="stock-ticker" style="color:#f87171">${l.name}</div><div class="stock-name">${l.type}${l.monthly_payment?` · 月繳NT$${l.monthly_payment.toLocaleString()}`:''}</div></div>
        <div class="stock-value"><div class="stock-price" style="color:#f87171">-NT$${l.balance.toLocaleString()}</div></div>
      </div>`).join('')
    : '<div style="color:#888;font-size:14px;padding:8px 0">無負債</div>';
}

function renderCash(cash) {
  document.getElementById('cash-list').innerHTML = cash.length
    ? cash.map(c => `<div class="stock-row">
        <div class="stock-ticker">${c.name}</div>
        <div class="stock-price" style="color:#4ade80">NT$${c.balance.toLocaleString()}</div>
      </div>`).join('')
    : '<div style="color:#888;font-size:14px;padding:8px 0">尚未設定</div>';
}

async function saveNetworthSnapshot() {
  const now = new Date();
  const ym = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;
  await apiFetch('/finance/networth/snapshot', {
    method: 'POST',
    body: JSON.stringify({ year_month: ym, total_assets: window._currentAssets||0, total_liabilities: window._currentLiabilities||0 })
  });
  alert(`${ym} 淨資產快照已儲存`);
  loadAssets();
}

// ============================================================
// ASSET EDIT MODAL
// ============================================================
function openAssetModal() {
  document.getElementById('asset-modal-content').innerHTML = `
    <div class="settings-section">
      <h4>台股</h4>
      <div class="settings-row">
        <input id="tw-ticker" placeholder="代號（如2330）" style="width:80px">
        <input id="tw-name" placeholder="名稱（如台積電）">
        <input id="tw-shares" type="number" placeholder="股數" style="width:80px">
        <button class="btn-secondary" onclick="addHolding('TW')">加入</button>
      </div>
    </div>
    <div class="settings-section">
      <h4>美股</h4>
      <div class="settings-row">
        <input id="us-ticker" placeholder="代號（如AAPL）" style="width:80px">
        <input id="us-name" placeholder="名稱（如Apple）">
        <input id="us-shares" type="number" placeholder="股數" style="width:80px">
        <button class="btn-secondary" onclick="addHolding('US')">加入</button>
      </div>
    </div>
    <div class="settings-section">
      <h4>存款/現金</h4>
      <div class="settings-row">
        <input id="cash-name" placeholder="帳戶名稱">
        <input id="cash-balance" type="number" placeholder="金額">
        <button class="btn-secondary" onclick="addCash()">更新</button>
      </div>
    </div>
    <div class="settings-section">
      <h4>負債</h4>
      <div class="settings-row" style="flex-wrap:wrap;gap:8px">
        <select id="liab-type" style="width:90px"><option>信貸</option><option>質押借款</option></select>
        <input id="liab-name" placeholder="名稱">
        <input id="liab-balance" type="number" placeholder="餘額">
        <input id="liab-payment" type="number" placeholder="月繳（選填）">
        <button class="btn-secondary" onclick="addLiability()">更新</button>
      </div>
    </div>
    <div class="settings-section">
      <h4>API 設定</h4>
      <div style="display:flex;flex-direction:column;gap:8px">
        <input id="cfg-base" placeholder="API URL（如 https://xxx.railway.app）" value="${localStorage.getItem('apiBase')||''}">
        <input id="cfg-key" placeholder="API Key" value="${localStorage.getItem('apiKey')||''}">
        <button class="btn-secondary" onclick="saveConfig()">儲存設定</button>
      </div>
    </div>
  `;
  document.getElementById('asset-modal').classList.add('open');
}

async function addHolding(market) {
  const t = document.getElementById(market.toLowerCase()+'-ticker').value.trim();
  const n = document.getElementById(market.toLowerCase()+'-name').value.trim();
  const s = parseFloat(document.getElementById(market.toLowerCase()+'-shares').value);
  if (!t || !n || isNaN(s)) return alert('請填寫完整');
  await apiFetch('/finance/holdings', { method:'POST', body:JSON.stringify({market,ticker:t,name:n,shares:s}) });
  alert('已更新');
}

async function addCash() {
  const n = document.getElementById('cash-name').value.trim();
  const b = parseInt(document.getElementById('cash-balance').value);
  if (!n || isNaN(b)) return alert('請填寫完整');
  await apiFetch('/finance/cash', { method:'POST', body:JSON.stringify({name:n,balance:b}) });
  alert('已更新');
}

async function addLiability() {
  const type = document.getElementById('liab-type').value;
  const name = document.getElementById('liab-name').value.trim();
  const balance = parseInt(document.getElementById('liab-balance').value);
  const payment = parseInt(document.getElementById('liab-payment').value) || 0;
  if (!name || isNaN(balance)) return alert('請填寫完整');
  await apiFetch('/finance/liabilities', { method:'POST', body:JSON.stringify({type,name,balance,monthly_payment:payment}) });
  alert('已更新');
}

function saveConfig() {
  localStorage.setItem('apiBase', document.getElementById('cfg-base').value.trim());
  localStorage.setItem('apiKey', document.getElementById('cfg-key').value.trim());
  closeModal('asset-modal');
  loadExpenses();
}

// ============================================================
// FAB & MODALS
// ============================================================
function fabAction() {
  if (currentTab === 'cashflow') {
    document.getElementById('cashflow-month'); // ensure loaded
    document.getElementById('income-modal').classList.add('open');
  } else if (currentTab === 'assets') {
    openAssetModal();
  }
  // Tab 1: no FAB action (data comes from LINE bot)
}

async function submitIncome() {
  const ym = document.getElementById('cashflow-month').value;
  const source = document.getElementById('inc-source').value.trim() || '薪資';
  const amount = parseInt(document.getElementById('inc-amount').value);
  const note = document.getElementById('inc-note').value.trim();
  if (isNaN(amount)) return alert('請輸入金額');
  await apiFetch('/finance/income', { method:'POST', body:JSON.stringify({year_month:ym,source,amount,note}) });
  closeModal('income-modal');
  loadCashflow();
}

function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

// ============================================================
// SETUP PROMPT
// ============================================================
function showSetupPrompt() {
  openAssetModal();
}

// ============================================================
// INIT
// ============================================================
getMonthOptions('expense-month');
getMonthOptions('cashflow-month');
if (API_BASE) loadExpenses();
else showSetupPrompt();
</script>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add finance-app/
git commit -m "feat: add PWA finance app with 3 tabs (支出/收支/總資產)"
```

---

## Phase 4：部署與設定

### Task 8：Railway 設定與部署

**Files:**
- Modify: `line-claude-bot/requirements.txt`（確認含 `pypdf`, `yfinance`）

- [ ] **Step 1: 確認 requirements.txt**

```
fastapi
uvicorn[standard]
anthropic
httpx
pytest
pytest-asyncio
pypdf
yfinance
```

- [ ] **Step 2: Railway 新增環境變數**

在 Railway Dashboard → Variables 新增：
```
GMAIL_USER=jennawang123123@gmail.com
GMAIL_APP_PASSWORD=（Gmail App Password，16位）
PDF_PASSWORD_ID=（身分證字號）
FINANCE_API_KEY=（隨機產生：python3 -c "import secrets;print(secrets.token_hex(16))"）
DATA_DIR=/data
```

- [ ] **Step 3: Railway 新增 Volume**

Railway Dashboard → 你的服務 → Volumes → Add Volume：
- Mount Path: `/data`
- Size: 1 GB（最小，NT$30/月）

- [ ] **Step 4: 推送並確認部署**

```bash
git add line-claude-bot/
git push origin main
# 等 Railway 重新部署（約 2 分鐘）
```

- [ ] **Step 5: 測試 API**

```bash
# 替換為你的 Railway URL 和 API key
curl https://YOUR.railway.app/finance/transactions \
  -H "x-api-key: YOUR_KEY"
# Expected: []
```

- [ ] **Step 6: 設定 PWA 的 API URL**

開啟 `finance-app/index.html` → 右下角會跳出「API 設定」→ 填入：
- API URL: `https://YOUR.railway.app`
- API Key: `YOUR_KEY`
→ 儲存設定

---

### Task 9：Gmail App Password 設定（一次性）

- [ ] **Step 1: 開啟 Google 兩步驟驗證**

前往 myaccount.google.com → 安全性 → 兩步驟驗證 → 開啟

- [ ] **Step 2: 產生 App Password**

myaccount.google.com → 安全性 → 應用程式密碼 → 選擇「郵件」→「其他裝置」→ 產生

- [ ] **Step 3: 測試 IMAP 連線**

```bash
cd line-claude-bot
GMAIL_USER=jennawang123123@gmail.com GMAIL_APP_PASSWORD=xxxx python3 -c "
from gmail_fetcher import fetch_bank_pdfs
pdfs = fetch_bank_pdfs(since_days=45)
print(f'找到 {len(pdfs)} 個 PDF')
for p in pdfs:
    print(f'  {p[\"bank\"]} - {p[\"filename\"]} ({len(p[\"data\"])} bytes)')
"
```

- [ ] **Step 4: 測試 PDF 解析**

```bash
PDF_PASSWORD_ID=你的身分證號 ANTHROPIC_API_KEY=sk-... python3 -c "
from gmail_fetcher import fetch_bank_pdfs
from pdf_parser import parse_pdf
pdfs = fetch_bank_pdfs(since_days=45)
if pdfs:
    txs = parse_pdf(pdfs[0]['data'], pdfs[0]['bank'], '2026-05')
    print(f'解析到 {len(txs)} 筆交易')
    for tx in txs[:5]:
        print(tx)
"
```

---

## Spec 覆蓋確認

| 需求 | Task |
|------|------|
| Gmail IMAP 下載 PDF 附件 | Task 4 |
| pypdf 解密（身分證密碼） | Task 5 |
| Claude 解析交易並分類 | Task 5 |
| LINE bot「處理對帳單」指令 | Task 6 |
| 使用者確認/改類別指令 | Task 6 |
| 8個支出類別 | Task 1 schema + Task 5 |
| 外幣自動標記旅遊 | Task 5 |
| REST API /finance/* | Task 2 |
| API key 認證 | Task 2 |
| SQLite 持久化 | Task 1 + Railway Volume |
| Tab 1 支出清單 + 類別圓餅 | Task 7 |
| Tab 1 手動改類別 | Task 7 |
| Tab 2 收支彙總 | Task 7 |
| Tab 2 月趨勢折線圖 | Task 7 |
| Tab 2 手動輸入收入 | Task 7 |
| Tab 3 台股/美股 + 即時股價 | Task 3 + Task 7 |
| Tab 3 現金/存款 | Task 7 |
| Tab 3 信貸負債追蹤 | Task 7 |
| Tab 3 質押借款 | Task 7 |
| Tab 3 淨資產計算 + 歷史趨勢 | Task 7 |
| PWA 可安裝至手機 | Task 7 manifest |
| Railway 部署 | Task 8 |
