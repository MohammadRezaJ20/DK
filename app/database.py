import psycopg2
from psycopg2.extras import RealDictCursor


def get_connection(database_url: str):
    return psycopg2.connect(
        database_url,
        cursor_factory=RealDictCursor,
        sslmode="require",
    )


def init_db(conn):
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            brand TEXT,
            category TEXT,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            conditions_json TEXT NOT NULL DEFAULT '{}',
            last_checked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS product_snapshots (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
            price BIGINT,
            list_price BIGINT,
            discount_percent INTEGER,
            is_available BOOLEAN NOT NULL DEFAULT FALSE,
            seller_name TEXT,
            best_discount_percent INTEGER,
            status TEXT,
            raw_data_json TEXT NOT NULL,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS seller_snapshots (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
            seller_name TEXT NOT NULL,
            price BIGINT,
            final_price BIGINT,
            is_available BOOLEAN NOT NULL DEFAULT FALSE,
            seller_rating REAL,
            seller_code TEXT,
            inventory_status TEXT,
            lead_time_days INTEGER,
            raw_data_json TEXT NOT NULL,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            is_delivered_telegram BOOLEAN NOT NULL DEFAULT FALSE,
            is_delivered_sms BOOLEAN NOT NULL DEFAULT FALSE,
            is_delivered_bale BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_products_product_id
        ON products(product_id);
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_product_snapshots_product_id_checked_at
        ON product_snapshots(product_id, checked_at DESC);
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_seller_snapshots_product_id_checked_at
        ON seller_snapshots(product_id, checked_at DESC);
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_product_id_created_at
        ON notifications(product_id, created_at DESC);
        """)

    conn.commit()
