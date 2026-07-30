import sqlite3
from pathlib import Path


def get_connection(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True) if "/" in db_path else None
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL UNIQUE,
        url TEXT NOT NULL,
        custom_name TEXT,
        title TEXT,
        brand TEXT,
        category TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        conditions_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS product_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        is_available INTEGER NOT NULL,
        best_price_toman INTEGER,
        best_seller_name TEXT,
        best_discount_percent INTEGER,
        status TEXT,
        raw_json TEXT,
        FOREIGN KEY(product_id) REFERENCES products(product_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS seller_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        seller_id INTEGER,
        seller_name TEXT,
        is_available INTEGER NOT NULL,
        price_toman INTEGER,
        discount_percent INTEGER,
        seller_rating REAL,
        warranty_name TEXT,
        lead_time TEXT,
        raw_json TEXT,
        FOREIGN KEY(product_id) REFERENCES products(product_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        level TEXT NOT NULL DEFAULT 'info',
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        sent_console INTEGER NOT NULL DEFAULT 0,
        sent_telegram INTEGER NOT NULL DEFAULT 0,
        sent_sms INTEGER NOT NULL DEFAULT 0
    )
    """)

    conn.commit()
