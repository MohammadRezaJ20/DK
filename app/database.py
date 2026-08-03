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
        # -------------------------
        # products
        # -------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL UNIQUE,
            custom_name TEXT,
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

        # Migration-safe additions for products
        cur.execute("""
        ALTER TABLE products
            ADD COLUMN IF NOT EXISTS custom_name TEXT,
            ADD COLUMN IF NOT EXISTS brand TEXT,
            ADD COLUMN IF NOT EXISTS category TEXT,
            ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS conditions_json TEXT NOT NULL DEFAULT '{}',
            ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
        """)

        cur.execute("""
        UPDATE products
        SET conditions_json = '{}'
        WHERE conditions_json IS NULL;
        """)

        cur.execute("""
        UPDATE products
        SET active = TRUE
        WHERE active IS NULL;
        """)

        cur.execute("""
        UPDATE products
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL;
        """)

        cur.execute("""
        UPDATE products
        SET updated_at = CURRENT_TIMESTAMP
        WHERE updated_at IS NULL;
        """)

        cur.execute("""
        ALTER TABLE products
            ALTER COLUMN active SET DEFAULT TRUE,
            ALTER COLUMN active SET NOT NULL,
            ALTER COLUMN conditions_json SET DEFAULT '{}',
            ALTER COLUMN conditions_json SET NOT NULL,
            ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP,
            ALTER COLUMN created_at SET NOT NULL,
            ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP,
            ALTER COLUMN updated_at SET NOT NULL;
        """)

        # -------------------------
        # product_snapshots
        # -------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS product_snapshots (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,

            -- Legacy/simple summary columns
            price BIGINT,
            list_price BIGINT,
            discount_percent INTEGER,
            is_available BOOLEAN NOT NULL DEFAULT FALSE,
            seller_name TEXT,

            -- Standardized best-offer summary columns
            best_price_toman BIGINT,
            best_list_price_toman BIGINT,
            best_seller_name TEXT,
            best_discount_percent INTEGER,

            status TEXT,
            raw_data_json TEXT NOT NULL DEFAULT '{}',
            checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Migration-safe additions for product_snapshots
        cur.execute("""
        ALTER TABLE product_snapshots
            ADD COLUMN IF NOT EXISTS price BIGINT,
            ADD COLUMN IF NOT EXISTS list_price BIGINT,
            ADD COLUMN IF NOT EXISTS discount_percent INTEGER,
            ADD COLUMN IF NOT EXISTS is_available BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS seller_name TEXT,
            ADD COLUMN IF NOT EXISTS best_price_toman BIGINT,
            ADD COLUMN IF NOT EXISTS best_list_price_toman BIGINT,
            ADD COLUMN IF NOT EXISTS best_seller_name TEXT,
            ADD COLUMN IF NOT EXISTS best_discount_percent INTEGER,
            ADD COLUMN IF NOT EXISTS status TEXT,
            ADD COLUMN IF NOT EXISTS raw_data_json TEXT,
            ADD COLUMN IF NOT EXISTS checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
        """)

        # Backfill standardized best-offer columns from legacy columns where possible
        cur.execute("""
        UPDATE product_snapshots
        SET
            best_price_toman = COALESCE(best_price_toman, price),
            best_list_price_toman = COALESCE(best_list_price_toman, list_price),
            best_seller_name = COALESCE(best_seller_name, seller_name),
            best_discount_percent = COALESCE(best_discount_percent, discount_percent)
        WHERE
            best_price_toman IS NULL
            OR best_list_price_toman IS NULL
            OR best_seller_name IS NULL
            OR best_discount_percent IS NULL;
        """)

        cur.execute("""
        UPDATE product_snapshots
        SET raw_data_json = '{}'
        WHERE raw_data_json IS NULL;
        """)

        cur.execute("""
        UPDATE product_snapshots
        SET is_available = FALSE
        WHERE is_available IS NULL;
        """)

        cur.execute("""
        UPDATE product_snapshots
        SET checked_at = CURRENT_TIMESTAMP
        WHERE checked_at IS NULL;
        """)

        cur.execute("""
        ALTER TABLE product_snapshots
            ALTER COLUMN is_available SET DEFAULT FALSE,
            ALTER COLUMN is_available SET NOT NULL,
            ALTER COLUMN raw_data_json SET DEFAULT '{}',
            ALTER COLUMN raw_data_json SET NOT NULL,
            ALTER COLUMN checked_at SET DEFAULT CURRENT_TIMESTAMP,
            ALTER COLUMN checked_at SET NOT NULL;
        """)

        # -------------------------
        # seller_snapshots
        # -------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS seller_snapshots (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
            seller_id BIGINT,
            seller_name TEXT NOT NULL,
            is_available BOOLEAN NOT NULL DEFAULT FALSE,
            price_toman BIGINT,
            list_price_toman BIGINT,
            discount_percent INTEGER,
            seller_rating REAL,
            rating REAL,
            warranty_name TEXT,
            lead_time TEXT,
            lead_time_days INTEGER,
            raw_data_json TEXT NOT NULL DEFAULT '{}',
            checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Migration-safe additions for seller_snapshots
        cur.execute("""
        ALTER TABLE seller_snapshots
            ADD COLUMN IF NOT EXISTS seller_id BIGINT,
            ADD COLUMN IF NOT EXISTS seller_name TEXT,
            ADD COLUMN IF NOT EXISTS is_available BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS price_toman BIGINT,
            ADD COLUMN IF NOT EXISTS list_price_toman BIGINT,
            ADD COLUMN IF NOT EXISTS discount_percent INTEGER,
            ADD COLUMN IF NOT EXISTS seller_rating REAL,
            ADD COLUMN IF NOT EXISTS rating REAL,
            ADD COLUMN IF NOT EXISTS warranty_name TEXT,
            ADD COLUMN IF NOT EXISTS lead_time TEXT,
            ADD COLUMN IF NOT EXISTS lead_time_days INTEGER,
            ADD COLUMN IF NOT EXISTS raw_data_json TEXT,
            ADD COLUMN IF NOT EXISTS checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
        """)

        cur.execute("""
        UPDATE seller_snapshots
        SET seller_name = 'Unknown Seller'
        WHERE seller_name IS NULL;
        """)

        cur.execute("""
        UPDATE seller_snapshots
        SET is_available = FALSE
        WHERE is_available IS NULL;
        """)

        cur.execute("""
        UPDATE seller_snapshots
        SET raw_data_json = '{}'
        WHERE raw_data_json IS NULL;
        """)

        cur.execute("""
        UPDATE seller_snapshots
        SET checked_at = CURRENT_TIMESTAMP
        WHERE checked_at IS NULL;
        """)

        cur.execute("""
        ALTER TABLE seller_snapshots
            ALTER COLUMN seller_name SET NOT NULL,
            ALTER COLUMN is_available SET DEFAULT FALSE,
            ALTER COLUMN is_available SET NOT NULL,
            ALTER COLUMN raw_data_json SET DEFAULT '{}',
            ALTER COLUMN raw_data_json SET NOT NULL,
            ALTER COLUMN checked_at SET DEFAULT CURRENT_TIMESTAMP,
            ALTER COLUMN checked_at SET NOT NULL;
        """)

        # -------------------------
        # notifications
        # -------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
            title TEXT,
            event_type TEXT NOT NULL DEFAULT 'rule_triggered',
            message TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',

            sent_console BOOLEAN NOT NULL DEFAULT FALSE,
            sent_telegram BOOLEAN NOT NULL DEFAULT FALSE,
            sent_sms BOOLEAN NOT NULL DEFAULT FALSE,
            sent_bale BOOLEAN NOT NULL DEFAULT FALSE,

            is_delivered_telegram BOOLEAN NOT NULL DEFAULT FALSE,
            is_delivered_sms BOOLEAN NOT NULL DEFAULT FALSE,
            is_delivered_bale BOOLEAN NOT NULL DEFAULT FALSE,

            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Migration-safe additions for notifications
        # Important: includes base columns too, for older schemas.
        cur.execute("""
        ALTER TABLE notifications
            ADD COLUMN IF NOT EXISTS title TEXT,
            ADD COLUMN IF NOT EXISTS event_type TEXT,
            ADD COLUMN IF NOT EXISTS message TEXT,
            ADD COLUMN IF NOT EXISTS payload_json TEXT,
            ADD COLUMN IF NOT EXISTS sent_console BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS sent_telegram BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS sent_sms BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS sent_bale BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS is_delivered_telegram BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS is_delivered_sms BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS is_delivered_bale BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
        """)

        cur.execute("""
        UPDATE notifications
        SET event_type = 'rule_triggered'
        WHERE event_type IS NULL;
        """)

        cur.execute("""
        UPDATE notifications
        SET message = ''
        WHERE message IS NULL;
        """)

        cur.execute("""
        UPDATE notifications
        SET payload_json = '{}'
        WHERE payload_json IS NULL;
        """)

        cur.execute("""
        UPDATE notifications
        SET sent_console = FALSE
        WHERE sent_console IS NULL;
        """)

        cur.execute("""
        UPDATE notifications
        SET sent_telegram = FALSE
        WHERE sent_telegram IS NULL;
        """)

        cur.execute("""
        UPDATE notifications
        SET sent_sms = FALSE
        WHERE sent_sms IS NULL;
        """)

        cur.execute("""
        UPDATE notifications
        SET sent_bale = FALSE
        WHERE sent_bale IS NULL;
        """)

        cur.execute("""
        UPDATE notifications
        SET is_delivered_telegram = FALSE
        WHERE is_delivered_telegram IS NULL;
        """)

        cur.execute("""
        UPDATE notifications
        SET is_delivered_sms = FALSE
        WHERE is_delivered_sms IS NULL;
        """)

        cur.execute("""
        UPDATE notifications
        SET is_delivered_bale = FALSE
        WHERE is_delivered_bale IS NULL;
        """)

        cur.execute("""
        UPDATE notifications
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL;
        """)

        cur.execute("""
        ALTER TABLE notifications
            ALTER COLUMN event_type SET DEFAULT 'rule_triggered',
            ALTER COLUMN event_type SET NOT NULL,
            ALTER COLUMN message SET NOT NULL,
            ALTER COLUMN payload_json SET DEFAULT '{}',
            ALTER COLUMN payload_json SET NOT NULL,
            ALTER COLUMN sent_console SET DEFAULT FALSE,
            ALTER COLUMN sent_console SET NOT NULL,
            ALTER COLUMN sent_telegram SET DEFAULT FALSE,
            ALTER COLUMN sent_telegram SET NOT NULL,
            ALTER COLUMN sent_sms SET DEFAULT FALSE,
            ALTER COLUMN sent_sms SET NOT NULL,
            ALTER COLUMN sent_bale SET DEFAULT FALSE,
            ALTER COLUMN sent_bale SET NOT NULL,
            ALTER COLUMN is_delivered_telegram SET DEFAULT FALSE,
            ALTER COLUMN is_delivered_telegram SET NOT NULL,
            ALTER COLUMN is_delivered_sms SET DEFAULT FALSE,
            ALTER COLUMN is_delivered_sms SET NOT NULL,
            ALTER COLUMN is_delivered_bale SET DEFAULT FALSE,
            ALTER COLUMN is_delivered_bale SET NOT NULL,
            ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP,
            ALTER COLUMN created_at SET NOT NULL;
        """)

        # -------------------------
        # indexes
        # -------------------------
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_products_product_id
        ON products(product_id);
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_products_active_id
        ON products(active, id);
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_product_snapshots_product_id_checked_at
        ON product_snapshots(product_id, checked_at DESC);
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_product_snapshots_product_id_id
        ON product_snapshots(product_id, id DESC);
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_seller_snapshots_product_id_checked_at
        ON seller_snapshots(product_id, checked_at DESC);
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_seller_snapshots_product_id_seller_id_checked_at
        ON seller_snapshots(product_id, seller_id, checked_at DESC);
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_product_id_created_at
        ON notifications(product_id, created_at DESC);
        """)

    conn.commit()
