import json
import random
import time
import httpx

from app.digikala import extract_product_id, fetch_product, parse_product
from app.rules import evaluate_rules, filter_offers, best_available_offer
from app.notifier import Notifier


def upsert_product(conn, product_id, url, custom_name, title, brand, category, conditions_json):
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO products (product_id, url, custom_name, title, brand, category, conditions_json, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(product_id) DO UPDATE SET
        url=excluded.url,
        custom_name=excluded.custom_name,
        title=excluded.title,
        brand=excluded.brand,
        category=excluded.category,
        conditions_json=excluded.conditions_json,
        updated_at=CURRENT_TIMESTAMP
    """, (product_id, url, custom_name, title, brand, category, conditions_json))
    conn.commit()


def get_all_active_products(conn):
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE active = 1 ORDER BY id ASC")
    return cur.fetchall()


def get_last_snapshot(conn, product_id):
    cur = conn.cursor()
    cur.execute("""
    SELECT * FROM product_snapshots
    WHERE product_id = ?
    ORDER BY id DESC
    LIMIT 1
    """, (product_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def get_last_seller_snapshots(conn, product_id):
    cur = conn.cursor()
    cur.execute("""
    SELECT * FROM seller_snapshots
    WHERE product_id = ? AND checked_at = (
        SELECT checked_at FROM seller_snapshots
        WHERE product_id = ?
        ORDER BY id DESC LIMIT 1
    )
    """, (product_id, product_id))
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def insert_snapshot(conn, snapshot, filtered_offers):
    cur = conn.cursor()
    best = best_available_offer(filtered_offers)

    cur.execute("""
    INSERT INTO product_snapshots (
        product_id, is_available, best_price_toman,
        best_seller_name, best_discount_percent,
        status, raw_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        snapshot.product_id,
        1 if any(o.is_available for o in filtered_offers) else 0,
        best.price_toman if best else None,
        best.seller_name if best else None,
        best.discount_percent if best else None,
        snapshot.status,
        json.dumps(snapshot.raw, ensure_ascii=False),
    ))

    for offer in filtered_offers:
        cur.execute("""
        INSERT INTO seller_snapshots (
            product_id, seller_id, seller_name, is_available,
            price_toman, discount_percent, seller_rating,
            warranty_name, lead_time, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot.product_id,
            offer.seller_id,
            offer.seller_name,
            1 if offer.is_available else 0,
            offer.price_toman,
            offer.discount_percent,
            offer.seller_rating,
            offer.warranty_name,
            offer.lead_time,
            json.dumps(offer.raw, ensure_ascii=False),
        ))

    conn.commit()


def insert_notification(conn, product_id, title, message, sent_result):
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO notifications (
        product_id, title, message,
        sent_console, sent_telegram, sent_sms
    ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        product_id,
        title,
        message,
        1 if sent_result.get("console") else 0,
        1 if sent_result.get("telegram") else 0,
        1 if sent_result.get("sms") else 0,
    ))
    conn.commit()


def build_report(snapshot, filtered_offers, reasons):
    best = best_available_offer(filtered_offers)

    lines = [
        "گزارش پایش دیجیکالا",
        f"کالا: {snapshot.title}",
        f"شناسه: {snapshot.product_id}",
        f"لینک: {snapshot.url}",
        f"وضعیت: {'موجود' if any(o.is_available for o in filtered_offers) else 'ناموجود'}",
        f"برند: {snapshot.brand or 'نامشخص'}",
        f"دسته‌بندی: {snapshot.category or 'نامشخص'}",
        "",
        "دلایل اعلان:",
    ]
    lines.extend(f"- {r}" for r in reasons)

    if best:
        lines.extend([
            "",
            "بهترین پیشنهاد:",
            f"- فروشنده: {best.seller_name or 'نامشخص'}",
            f"- قیمت: {best.price_toman:,} تومان" if best.price_toman is not None else "- قیمت: نامشخص",
            f"- تخفیف: {best.discount_percent}%" if best.discount_percent is not None else "- تخفیف: نامشخص",
            f"- گارانتی: {best.warranty_name or 'نامشخص'}",
            f"- ارسال: {best.lead_time or 'نامشخص'}",
            f"- امتیاز فروشنده: {best.seller_rating}" if best.seller_rating is not None else "- امتیاز فروشنده: نامشخص",
        ])

    lines.extend(["", "همه فروشنده‌ها:"])
    for o in sorted(
        filtered_offers,
        key=lambda x: (not x.is_available, x.price_toman if x.price_toman is not None else 10**18)
    ):
        lines.append(
            f"- {o.seller_name or 'نامشخص'} | "
            f"{'موجود' if o.is_available else 'ناموجود'} | "
            f"{f'{o.price_toman:,} تومان' if o.price_toman is not None else 'قیمت نامشخص'} | "
            f"تخفیف: {o.discount_percent if o.discount_percent is not None else 'نامشخص'}% | "
            f"گارانتی: {o.warranty_name or 'نامشخص'}"
        )

    return "\n".join(lines)


def monitor_once(conn, config):
    notifier = Notifier(config)
    products = get_all_active_products(conn)

    settings = config["app"]
    timeout = settings["request_timeout_seconds"]
    min_delay = settings["min_delay_between_requests_seconds"]
    max_delay = settings["max_delay_between_requests_seconds"]

    with httpx.Client(timeout=timeout) as client:
        for row in products:
            product_id = row["product_id"]
            url = row["url"]
            conditions = json.loads(row["conditions_json"])

            time.sleep(random.uniform(min_delay, max_delay))

            payload = fetch_product(client, product_id)
            snapshot = parse_product(product_id, url, payload)

            filtered_offers = filter_offers(snapshot.offers, conditions)

            previous_summary = get_last_snapshot(conn, product_id)
            previous_sellers = get_last_seller_snapshots(conn, product_id)

            reasons = evaluate_rules(
                snapshot=snapshot,
                previous_summary=previous_summary,
                previous_sellers=previous_sellers,
                conditions=conditions,
            )

            upsert_product(
                conn=conn,
                product_id=product_id,
                url=url,
                custom_name=row["custom_name"],
                title=snapshot.title,
                brand=snapshot.brand,
                category=snapshot.category,
                conditions_json=json.dumps(conditions, ensure_ascii=False),
            )

            insert_snapshot(conn, snapshot, filtered_offers)

            if reasons:
                report = build_report(snapshot, filtered_offers, reasons)
                sent = notifier.notify_all(report)
                insert_notification(conn, product_id, snapshot.title, report, sent)
