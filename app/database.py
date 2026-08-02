import psycopg2
from psycopg2.extras import RealDictCursor


def get_connection(database_url: str):
    conn = psycopg2.connect(
        database_url,
        cursor_factory=RealDictCursor
    )
    return conn


def init_db(conn) -> None:
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
        product_id INTEGER NOT NULL UNIQUE,
        url TEXT NOT NULL,
        custom_name TEXT,
        title TEXT,
        brand TEXT,
        category TEXT,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        conditions_json TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS product_snapshots (
        id SERIAL PRIMARY KEY,
        product_id INTEGER NOT NULL,
        checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        is_available BOOLEAN NOT NULL,
        best_price_toman INTEGER,
        best_seller_name TEXT,
        best_discount_percent INTEGER,
        status TEXT,
        raw_json TEXT,
        FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE CASCADE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS seller_snapshots (
        id SERIAL PRIMARY KEY,
        product_id INTEGER NOT NULL,
        checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        seller_id INTEGER,
        seller_name TEXT,
        is_available BOOLEAN NOT NULL,
        price_toman INTEGER,
        discount_percent INTEGER,
        seller_rating REAL,
        warranty_name TEXT,
        lead_time TEXT,
        raw_json TEXT,
        FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE CASCADE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id SERIAL PRIMARY KEY,
        product_id INTEGER NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        level TEXT NOT NULL DEFAULT 'info',
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        sent_console BOOLEAN NOT NULL DEFAULT FALSE,
        sent_telegram BOOLEAN NOT NULL DEFAULT FALSE,
        sent_sms BOOLEAN NOT NULL DEFAULT FALSE,
        FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE CASCADE
    )
    """)

    conn.commit()
