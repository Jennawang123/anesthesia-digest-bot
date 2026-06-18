import os
import logging
from typing import Optional
from sqlalchemy import create_engine, text

CATEGORIES = ["日常", "房租", "交通", "旅遊", "娛樂", "教育", "醫療", "贈與", "長期規劃", "貸款"]


def _make_engine():
    url = os.environ.get("DATABASE_URL", "")
    if url:
        url = url.replace("postgres://", "postgresql://", 1)
        return create_engine(url, pool_pre_ping=True)
    data_dir = os.environ.get("DATA_DIR", "/tmp/finance")
    os.makedirs(data_dir, exist_ok=True)
    return create_engine(f"sqlite:///{data_dir}/finance.db")


engine = _make_engine()
IS_PG = engine.dialect.name == "postgresql"

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, merchant TEXT NOT NULL, amount INTEGER NOT NULL,
    currency TEXT DEFAULT 'TWD', category TEXT NOT NULL, bank TEXT NOT NULL,
    card_last4 TEXT DEFAULT '', note TEXT DEFAULT '', is_travel INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS income (
    id INTEGER PRIMARY KEY AUTOINCREMENT, year_month TEXT NOT NULL,
    source TEXT NOT NULL, amount INTEGER NOT NULL, note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, market TEXT NOT NULL, ticker TEXT NOT NULL,
    name TEXT NOT NULL, shares REAL NOT NULL, avg_price REAL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(market, ticker)
);
CREATE TABLE IF NOT EXISTS liabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL, name TEXT NOT NULL,
    balance INTEGER NOT NULL, monthly_payment INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now')), UNIQUE(name)
);
CREATE TABLE IF NOT EXISTS cash_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
    balance INTEGER NOT NULL, updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS net_worth_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, year_month TEXT NOT NULL UNIQUE,
    total_assets INTEGER NOT NULL, total_liabilities INTEGER NOT NULL, net_worth INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS futures_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL DEFAULT '小台',
    direction TEXT NOT NULL DEFAULT '多', contracts INTEGER NOT NULL DEFAULT 1,
    entry_date TEXT NOT NULL, entry_price INTEGER NOT NULL,
    exit_date TEXT, exit_price INTEGER,
    point_value INTEGER NOT NULL DEFAULT 50, fee INTEGER NOT NULL DEFAULT 0,
    note TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS net_worth_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL UNIQUE,
    total_assets INTEGER NOT NULL, total_liabilities INTEGER NOT NULL, net_worth INTEGER NOT NULL
);
"""

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL, merchant TEXT NOT NULL, amount INTEGER NOT NULL,
    currency TEXT DEFAULT 'TWD', category TEXT NOT NULL, bank TEXT NOT NULL,
    card_last4 TEXT DEFAULT '', note TEXT DEFAULT '', is_travel INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS income (
    id SERIAL PRIMARY KEY, year_month TEXT NOT NULL,
    source TEXT NOT NULL, amount INTEGER NOT NULL, note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS holdings (
    id SERIAL PRIMARY KEY, market TEXT NOT NULL, ticker TEXT NOT NULL,
    name TEXT NOT NULL, shares REAL NOT NULL, avg_price REAL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(market, ticker)
);
CREATE TABLE IF NOT EXISTS liabilities (
    id SERIAL PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL,
    balance INTEGER NOT NULL, monthly_payment INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE(name)
);
CREATE TABLE IF NOT EXISTS cash_accounts (
    id SERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE,
    balance INTEGER NOT NULL, updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS net_worth_history (
    id SERIAL PRIMARY KEY, year_month TEXT NOT NULL UNIQUE,
    total_assets INTEGER NOT NULL, total_liabilities INTEGER NOT NULL, net_worth INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS futures_trades (
    id SERIAL PRIMARY KEY, symbol TEXT NOT NULL DEFAULT '小台',
    direction TEXT NOT NULL DEFAULT '多', contracts INTEGER NOT NULL DEFAULT 1,
    entry_date TEXT NOT NULL, entry_price INTEGER NOT NULL,
    exit_date TEXT, exit_price INTEGER,
    point_value INTEGER NOT NULL DEFAULT 50, fee INTEGER NOT NULL DEFAULT 0,
    note TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS net_worth_daily (
    id SERIAL PRIMARY KEY, date TEXT NOT NULL UNIQUE,
    total_assets INTEGER NOT NULL, total_liabilities INTEGER NOT NULL, net_worth INTEGER NOT NULL
);
"""


def init_db():
    schema = SCHEMA_PG if IS_PG else SCHEMA_SQLITE
    # Each CREATE TABLE in its own transaction so one failure doesn't block others
    for stmt in schema.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception as e:
            logging.debug("Schema stmt skipped: %s", e)

    # Migrations in separate transactions
    migrations = [
        "ALTER TABLE holdings ADD COLUMN avg_price REAL DEFAULT 0",
    ]
    for m in migrations:
        try:
            with engine.begin() as conn:
                conn.execute(text(m))
            logging.info("Migration applied: %s", m[:60])
        except Exception:
            pass  # already applied

    logging.info("DB initialized (%s)", "PostgreSQL" if IS_PG else "SQLite")


def _rows(result) -> list:
    keys = list(result.keys())
    return [dict(zip(keys, row)) for row in result.fetchall()]


# ── Transactions ──────────────────────────────────────────────

def insert_transaction(tx: dict) -> int:
    with engine.begin() as conn:
        if IS_PG:
            result = conn.execute(text(
                "INSERT INTO transactions (date,merchant,amount,currency,category,bank,card_last4,note,is_travel) "
                "VALUES (:date,:merchant,:amount,:currency,:category,:bank,:card_last4,:note,:is_travel) RETURNING id"
            ), tx)
            return result.fetchone()[0]
        else:
            result = conn.execute(text(
                "INSERT INTO transactions (date,merchant,amount,currency,category,bank,card_last4,note,is_travel) "
                "VALUES (:date,:merchant,:amount,:currency,:category,:bank,:card_last4,:note,:is_travel)"
            ), tx)
            return result.lastrowid


def insert_transactions_batch(txs: list) -> list:
    return [insert_transaction(tx) for tx in txs]


def list_transactions(year_month: Optional[str] = None) -> list:
    with engine.connect() as conn:
        if year_month:
            result = conn.execute(text(
                "SELECT id,date,merchant,amount,currency,category,bank,card_last4,note,is_travel "
                "FROM transactions WHERE date LIKE :ym ORDER BY date DESC"
            ), {"ym": f"{year_month}%"})
        else:
            result = conn.execute(text(
                "SELECT id,date,merchant,amount,currency,category,bank,card_last4,note,is_travel "
                "FROM transactions ORDER BY date DESC"
            ))
        return _rows(result)


def update_category(tx_id: int, category: str):
    with engine.begin() as conn:
        conn.execute(text("UPDATE transactions SET category=:c WHERE id=:id"), {"c": category, "id": tx_id})


def update_note(tx_id: int, note: str):
    with engine.begin() as conn:
        conn.execute(text("UPDATE transactions SET note=:n WHERE id=:id"), {"n": note, "id": tx_id})


def update_transaction(tx_id: int, tx: dict):
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE transactions SET date=:date, merchant=:merchant, amount=:amount, "
            "category=:category, bank=:bank, note=:note, is_travel=:is_travel WHERE id=:id"
        ), {**tx, "id": tx_id})


def delete_transaction(tx_id: int):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM transactions WHERE id=:id"), {"id": tx_id})


def delete_transactions_by_month(year_month: str) -> int:
    with engine.begin() as conn:
        result = conn.execute(text(
            "DELETE FROM transactions WHERE date LIKE :ym"
        ), {"ym": f"{year_month}%"})
        return result.rowcount


def monthly_summary(year_month: str) -> dict:
    txs = list_transactions(year_month)
    by_category: dict = {}
    for tx in txs:
        by_category[tx["category"]] = by_category.get(tx["category"], 0) + tx["amount"]
    total_expense = sum(tx["amount"] for tx in txs)
    income_rows = list_income(year_month)
    total_income = sum(r["amount"] for r in income_rows)
    return {
        "year_month": year_month,
        "total_expense": total_expense,
        "total_income": total_income,
        "balance": total_income - total_expense,
        "by_category": by_category,
        "transaction_count": len(txs),
    }


# ── Income ────────────────────────────────────────────────────

def upsert_income(year_month: str, source: str, amount: int, note: str = ""):
    with engine.begin() as conn:
        existing = conn.execute(text(
            "SELECT id FROM income WHERE year_month=:ym AND source=:src"
        ), {"ym": year_month, "src": source}).fetchone()
        if existing:
            conn.execute(text("UPDATE income SET amount=:a,note=:n WHERE id=:id"),
                         {"a": amount, "n": note, "id": existing[0]})
        else:
            conn.execute(text(
                "INSERT INTO income (year_month,source,amount,note) VALUES (:ym,:src,:a,:n)"
            ), {"ym": year_month, "src": source, "a": amount, "n": note})


def delete_income(income_id: int):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM income WHERE id=:id"), {"id": income_id})


def list_income(year_month: Optional[str] = None) -> list:
    with engine.connect() as conn:
        if year_month:
            result = conn.execute(text("SELECT * FROM income WHERE year_month=:ym"), {"ym": year_month})
        else:
            result = conn.execute(text("SELECT * FROM income ORDER BY year_month DESC"))
        return _rows(result)


# ── Holdings ──────────────────────────────────────────────────

def upsert_holding(market: str, ticker: str, name: str, shares: float, avg_price: float = 0):
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO holdings (market,ticker,name,shares,avg_price) VALUES (:m,:t,:n,:s,:a) "
            "ON CONFLICT(market,ticker) DO UPDATE SET name=EXCLUDED.name, shares=EXCLUDED.shares, avg_price=EXCLUDED.avg_price"
        ), {"m": market, "t": ticker, "n": name, "s": shares, "a": avg_price})


def delete_holding(holding_id: int):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM holdings WHERE id=:id"), {"id": holding_id})


def list_holdings() -> list:
    with engine.connect() as conn:
        return _rows(conn.execute(text("SELECT * FROM holdings ORDER BY market,ticker")))


# ── Liabilities ───────────────────────────────────────────────

def upsert_liability(type_: str, name: str, balance: int, monthly_payment: int = 0):
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO liabilities (type,name,balance,monthly_payment) VALUES (:t,:n,:b,:m) "
            "ON CONFLICT(name) DO UPDATE SET type=EXCLUDED.type, balance=EXCLUDED.balance, "
            "monthly_payment=EXCLUDED.monthly_payment"
        ), {"t": type_, "n": name, "b": balance, "m": monthly_payment})


def delete_liability(liability_id: int):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM liabilities WHERE id=:id"), {"id": liability_id})


def list_liabilities() -> list:
    with engine.connect() as conn:
        return _rows(conn.execute(text("SELECT * FROM liabilities")))


# ── Cash ──────────────────────────────────────────────────────

def upsert_cash(name: str, balance: int):
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO cash_accounts (name,balance) VALUES (:n,:b) "
            "ON CONFLICT(name) DO UPDATE SET balance=EXCLUDED.balance"
        ), {"n": name, "b": balance})


def delete_cash(cash_id: int):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM cash_accounts WHERE id=:id"), {"id": cash_id})


def list_cash() -> list:
    with engine.connect() as conn:
        return _rows(conn.execute(text("SELECT * FROM cash_accounts")))


# ── Net Worth ─────────────────────────────────────────────────

def save_net_worth_snapshot(year_month: str, assets: int, liabilities: int):
    net = assets - liabilities
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO net_worth_history (year_month,total_assets,total_liabilities,net_worth) "
            "VALUES (:ym,:a,:l,:n) ON CONFLICT(year_month) DO UPDATE SET "
            "total_assets=EXCLUDED.total_assets, total_liabilities=EXCLUDED.total_liabilities, "
            "net_worth=EXCLUDED.net_worth"
        ), {"ym": year_month, "a": assets, "l": liabilities, "n": net})


def list_net_worth_history() -> list:
    with engine.connect() as conn:
        return _rows(conn.execute(text("SELECT * FROM net_worth_history ORDER BY year_month")))


def save_net_worth_daily(date: str, assets: int, liabilities: int):
    net = assets - liabilities
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO net_worth_daily (date,total_assets,total_liabilities,net_worth) "
            "VALUES (:d,:a,:l,:n) ON CONFLICT(date) DO UPDATE SET "
            "total_assets=EXCLUDED.total_assets, total_liabilities=EXCLUDED.total_liabilities, "
            "net_worth=EXCLUDED.net_worth"
        ), {"d": date, "a": assets, "l": liabilities, "n": net})


def list_net_worth_daily() -> list:
    with engine.connect() as conn:
        return _rows(conn.execute(text("SELECT * FROM net_worth_daily ORDER BY date")))


# ── Futures ───────────────────────────────────────────────────

def insert_futures_trade(trade: dict) -> int:
    with engine.begin() as conn:
        if IS_PG:
            result = conn.execute(text(
                "INSERT INTO futures_trades (symbol,direction,contracts,entry_date,entry_price,exit_date,exit_price,point_value,fee,note) "
                "VALUES (:symbol,:direction,:contracts,:entry_date,:entry_price,:exit_date,:exit_price,:point_value,:fee,:note) RETURNING id"
            ), trade)
            return result.fetchone()[0]
        else:
            result = conn.execute(text(
                "INSERT INTO futures_trades (symbol,direction,contracts,entry_date,entry_price,exit_date,exit_price,point_value,fee,note) "
                "VALUES (:symbol,:direction,:contracts,:entry_date,:entry_price,:exit_date,:exit_price,:point_value,:fee,:note)"
            ), trade)
            return result.lastrowid


def list_futures_trades(status: Optional[str] = None) -> list:
    with engine.connect() as conn:
        if status == "open":
            result = conn.execute(text(
                "SELECT * FROM futures_trades WHERE exit_price IS NULL ORDER BY entry_date DESC"))
        elif status == "closed":
            result = conn.execute(text(
                "SELECT * FROM futures_trades WHERE exit_price IS NOT NULL ORDER BY entry_date DESC"))
        else:
            result = conn.execute(text("SELECT * FROM futures_trades ORDER BY entry_date DESC"))
        return _rows(result)


def update_futures_trade(trade_id: int, trade: dict):
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE futures_trades SET symbol=:symbol, direction=:direction, contracts=:contracts, "
            "entry_date=:entry_date, entry_price=:entry_price, exit_date=:exit_date, exit_price=:exit_price, "
            "point_value=:point_value, fee=:fee, note=:note WHERE id=:id"
        ), {**trade, "id": trade_id})


def delete_futures_trade(trade_id: int):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM futures_trades WHERE id=:id"), {"id": trade_id})
