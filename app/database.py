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
            ADD COLUMN IF NOT EXISTS brand TEXT,
            ADD COLUMN IF NOT EXISTS category TEXT,
            ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS conditions_json TEXT NOT NULL DEFAULT '{}',
            ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
        """)

        # -------------------------
        # product_snapshots
        # -------------------------
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

        # Migration-safe additions for product_snapshots
        cur.execute("""
        ALTER TABLE product_snapshots
            ADD COLUMN IF NOT EXISTS price BIGINT,
            ADD COLUMN IF NOT EXISTS list_price BIGINT,
            ADD COLUMN IF NOT EXISTS discount_percent INTEGER,
            ADD COLUMN IF NOT EXISTS is_available BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS seller_name TEXT,
            ADD COLUMN IF NOT EXISTS best_discount_percent INTEGER,
            ADD COLUMN IF NOT EXISTS status TEXT,
            ADD COLUMN IF NOT EXISTS raw_data_json TEXT,
            ADD COLUMN IF NOT EXISTS checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
        """)

        # اگر جدول قدیمی raw_data_json را NULL داشته باشد، بهتر است مقدار پیش‌فرض بدهیم
        cur.execute("""
        UPDATE product_snapshots
        SET raw_data_json = '{}'
        WHERE raw_data_json IS NULL;
        """)

        cur.execute("""
        ALTER TABLE product_snapshots
            ALTER COLUMN raw_data_json SET DEFAULT '{}',
            ALTER COLUMN raw_data_json SET NOT NULL;
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
            discount_percent INTEGER,
            seller_rating REAL,
            warranty_name TEXT,
            lead_time TEXT,
            raw_data_json TEXT NOT NULL DEFAULT '{}',
            checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Migration-safe additions for seller_snapshots
        # این بخش مشکل اصلی شما را رفع می‌کند.
        cur.execute("""
        ALTER TABLE seller_snapshots
            ADD COLUMN IF NOT EXISTS seller_id BIGINT,
            ADD COLUMN IF NOT EXISTS seller_name TEXT,
            ADD COLUMN IF NOT EXISTS is_available BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS price_toman BIGINT,
            ADD COLUMN IF NOT EXISTS discount_percent INTEGER,
            ADD COLUMN IF NOT EXISTS seller_rating REAL,
            ADD COLUMN IF NOT EXISTS warranty_name TEXT,
            ADD COLUMN IF NOT EXISTS lead_time TEXT,
            ADD COLUMN IF NOT EXISTS raw_data_json TEXT,
            ADD COLUMN IF NOT EXISTS checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
        """)

        # برای سازگاری با schemaهای قدیمی که price/final_price داشته‌اند
        # اگر price_toman خالی باشد و ستون‌های قدیمی وجود داشته باشند، می‌توانیم بعداً دستی migrate کنیم.
        # اینجا ستون‌های قدیمی را حذف نمی‌کنیم تا داده‌ای از بین نرود.

        cur.execute("""
        UPDATE seller_snapshots
        SET seller_name = 'Unknown Seller'
        WHERE seller_name IS NULL;
        """)

        cur.execute("""
        UPDATE seller_snapshots
        SET raw_data_json = '{}'
        WHERE raw_data_json IS NULL;
        """)

        cur.execute("""
        ALTER TABLE seller_snapshots
            ALTER COLUMN seller_name SET NOT NULL,
            ALTER COLUMN raw_data_json SET DEFAULT '{}',
            ALTER COLUMN raw_data_json SET NOT NULL;
        """)

        # -------------------------
        # notifications
        # -------------------------
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

        # Migration-safe additions for notifications
        cur.execute("""
        ALTER TABLE notifications
            ADD COLUMN IF NOT EXISTS event_type TEXT,
            ADD COLUMN IF NOT EXISTS message TEXT,
            ADD COLUMN IF NOT EXISTS payload_json TEXT NOT NULL DEFAULT '{}',
            ADD COLUMN IF NOT EXISTS is_delivered_telegram BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS is_delivered_sms BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS is_delivered_bale BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
        """)

        # -------------------------
        # indexes
        # -------------------------
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
        CREATE INDEX IF NOT EXISTS idx_seller_snapshots_product_id_seller_id_checked_at
        ON seller_snapshots(product_id, seller_id, checked_at DESC);
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_product_id_created_at
        ON notifications(product_id, created_at DESC);
        """)

    conn.commit()
