from __future__ import annotations

import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Any


def get_connection(database_url: str):
    """
    Open PostgreSQL connection.

    Notes:
    - sslmode=require should already exist in DATABASE_URL for Neon.
    - autocommit is kept False so caller controls transactions.
    """
    conn = psycopg2.connect(
        database_url,
        cursor_factory=RealDictCursor,
    )
    return conn


def init_db(conn) -> None:
    """
    Create tables and indexes if they do not exist.
    """
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            custom_name TEXT,
            title TEXT NOT NULL,
            brand TEXT,
            category TEXT,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            conditions_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS product_snapshots (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
            is_available BOOLEAN NOT NULL,
            best_price_toman BIGINT,
            best_seller_name TEXT,
            best_discount_percent INTEGER,
            status TEXT,
            raw_data_json TEXT NOT NULL,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS seller_snapshots (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
            seller_id TEXT NOT NULL,
            seller_name TEXT NOT NULL,
            is_available BOOLEAN NOT NULL,
            price_toman BIGINT,
            discount_percent INTEGER,
            rating NUMERIC,
            warranty_name TEXT,
            lead_time_days INTEGER,
            raw_data_json TEXT NOT NULL,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            level TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_delivered_telegram BOOLEAN NOT NULL DEFAULT FALSE,
            is_delivered_sms BOOLEAN NOT NULL DEFAULT FALSE
        );
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_products_active
        ON products(active);
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_product_snapshots_product_id_checked_at
        ON product_snapshots(product_id, checked_at DESC);
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_seller_snapshots_product_id_checked_at
        ON seller_snapshots(product_id, checked_at DESC);
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notifications_product_id_created_at
        ON notifications(product_id, created_at DESC);
        """
    )

    conn.commit()
    cur.close()
