import json
import random
import time
from string import Formatter

import httpx

from app.digikala import fetch_product, parse_product
from app.rules import evaluate_rules, filter_offers, best_available_offer
from app.notifier import Notifier


DEFAULT_SMS_TEMPLATE = """اعلان دیجیکالا
کالا: {product_name}
وضعیت: {availability}
قیمت: {best_price}
فروشنده: {best_seller}
دلایل:
{reasons}"""


class SafeFormatDict(dict):
    def __missing__(self, key):
        return "نامشخص"


def upsert_product(
    conn,
    product_id,
    url,
    custom_name,
    title,
    brand,
    category,
    conditions_json,
):
    cur = conn.cursor()
    try:
        cur.execute("""
        INSERT INTO products (
            product_id,
            url,
            custom_name,
            title,
            brand,
            category,
            conditions_json,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT(product_id) DO UPDATE SET
            url = EXCLUDED.url,
            custom_name = EXCLUDED.custom_name,
            title = EXCLUDED.title,
            brand = EXCLUDED.brand,
            category = EXCLUDED.category,
            conditions_json = EXCLUDED.conditions_json,
            updated_at = CURRENT_TIMESTAMP
        """, (
            product_id,
            url,
            custom_name,
            title or "",
            brand,
            category,
            conditions_json or "{}",
        ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def get_all_active_products(conn):
    cur = conn.cursor()
    try:
        cur.execute("""
        SELECT *
        FROM products
        WHERE active = TRUE
        ORDER BY id ASC
        """)
        return cur.fetchall()
    finally:
        cur.close()


def get_last_snapshot(conn, product_id):
    cur = conn.cursor()
    try:
        cur.execute("""
        SELECT *
        FROM product_snapshots
        WHERE product_id = %s
        ORDER BY id DESC
        LIMIT 1
        """, (product_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()


def get_last_seller_snapshots(conn, product_id):
    cur = conn.cursor()
    try:
        cur.execute("""
        SELECT *
        FROM seller_snapshots
        WHERE product_id = %s
          AND checked_at = (
              SELECT checked_at
              FROM seller_snapshots
              WHERE product_id = %s
              ORDER BY id DESC
              LIMIT 1
          )
        ORDER BY id ASC
        """, (product_id, product_id))
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        cur.close()


def safe_json_loads(value, default=None):
    if default is None:
        default = {}

    if value is None:
        return default

    if isinstance(value, dict):
        return value

    try:
        return json.loads(value)
    except Exception:
        return default


def insert_snapshot(conn, snapshot, filtered_offers):
    cur = conn.cursor()
    try:
        best = best_available_offer(filtered_offers)

        is_available = any(bool(o.is_available) for o in filtered_offers)

        best_price_toman = best.price_toman if best else None
        best_list_price_toman = best.list_price_toman if best else None
        best_seller_name = best.seller_name if best else None
        best_discount_percent = best.discount_percent if best else None

        cur.execute("""
        INSERT INTO product_snapshots (
            product_id,

            price,
            list_price,
            discount_percent,
            is_available,
            seller_name,

            best_price_toman,
            best_list_price_toman,
            best_seller_name,
            best_discount_percent,

            status,
            raw_data_json
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        """, (
            snapshot.product_id,

            # legacy columns
            best_price_toman,
            best_list_price_toman,
            best_discount_percent,
            is_available,
            best_seller_name,

            # standardized columns
            best_price_toman,
            best_list_price_toman,
            best_seller_name,
            best_discount_percent,

            snapshot.status or "unknown",
            json.dumps(snapshot.raw or {}, ensure_ascii=False),
        ))

        for offer in filtered_offers:
            cur.execute("""
            INSERT INTO seller_snapshots (
                product_id,
                seller_id,
                seller_name,
                is_available,
                price_toman,
                list_price_toman,
                discount_percent,
                seller_rating,
                rating,
                warranty_name,
                lead_time,
                lead_time_days,
                raw_data_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                snapshot.product_id,
                offer.seller_id,
                offer.seller_name or "Unknown Seller",
                bool(offer.is_available),
                offer.price_toman,
                offer.list_price_toman,
                offer.discount_percent,
                offer.seller_rating,
                offer.rating,
                offer.warranty_name,
                offer.lead_time,
                offer.lead_time_days,
                json.dumps(offer.raw or {}, ensure_ascii=False),
            ))

        cur.execute("""
        UPDATE products
        SET last_checked_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE product_id = %s
        """, (snapshot.product_id,))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def insert_notification(conn, product_id, title, message, sent_result):
    cur = conn.cursor()
    try:
        sent_result = sent_result or {}
        payload = json.dumps(sent_result, ensure_ascii=False)

        cur.execute("""
        INSERT INTO notifications (
            product_id,
            title,
            event_type,
            message,
            payload_json,

            sent_console,
            sent_telegram,
            sent_sms,
            sent_bale,

            is_delivered_telegram,
            is_delivered_sms,
            is_delivered_bale
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s
        )
        """, (
            product_id,
            title or "",
            "rule_triggered",
            message or "",
            payload,

            bool(sent_result.get("console")),
            bool(sent_result.get("telegram")),
            bool(sent_result.get("sms")),
            bool(sent_result.get("bale")),

            bool(sent_result.get("telegram")),
            bool(sent_result.get("sms")),
            bool(sent_result.get("bale")),
        ))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def _format_price_toman(value):
    if value is None:
        return "نامشخص"

    try:
        return f"{int(value):,} تومان"
    except (TypeError, ValueError):
        return "نامشخص"


def _format_percent(value):
    if value is None:
        return "نامشخص"

    return f"{value}%"


def _product_availability_text(filtered_offers):
    return "موجود" if any(bool(o.is_available) for o in filtered_offers) else "ناموجود"


def _safe_format_template(template: str, values: dict) -> str:
    """
    Safe template formatting.
    If template has unknown placeholders, they are replaced with 'نامشخص'.
    If template is broken, fallback text is returned.
    """

    if not template:
        template = DEFAULT_SMS_TEMPLATE

    try:
        formatter = Formatter()
        used_keys = {
            field_name
            for _, field_name, _, _ in formatter.parse(template)
            if field_name
        }

        safe_values = SafeFormatDict(values)

        for key in used_keys:
            safe_values.setdefault(key, "نامشخص")

        return template.format_map(safe_values).strip()

    except Exception:
        return DEFAULT_SMS_TEMPLATE.format_map(SafeFormatDict(values)).strip()


def _build_full_report_message(
    snapshot,
    filtered_offers,
    reasons,
    custom_name=None,
):
    best = best_available_offer(filtered_offers)

    display_title = custom_name or snapshot.title or f"DKP-{snapshot.product_id}"

    lines = [
        "گزارش پایش دیجیکالا",
        f"کالا: {display_title}",
        f"عنوان دیجیکالا: {snapshot.title or 'نامشخص'}",
        f"شناسه: {snapshot.product_id}",
        f"لینک: {snapshot.url}",
        f"وضعیت: {_product_availability_text(filtered_offers)}",
        f"برند: {snapshot.brand or 'نامشخص'}",
        f"دسته‌بندی: {snapshot.category or 'نامشخص'}",
        "",
        "دلایل اعلان:",
    ]

    if reasons:
        lines.extend(f"- {r}" for r in reasons)
    else:
        lines.append("- نامشخص")

    if best:
        lines.extend([
            "",
            "بهترین پیشنهاد:",
            f"- فروشنده: {best.seller_name or 'نامشخص'}",
            f"- قیمت فروش: {_format_price_toman(best.price_toman)}",
            f"- قیمت قبل از تخفیف: {_format_price_toman(best.list_price_toman)}",
            f"- تخفیف: {_format_percent(best.discount_percent)}",
            f"- گارانتی: {best.warranty_name or 'نامشخص'}",
            f"- ارسال: {best.lead_time or 'نامشخص'}",
            f"- امتیاز فروشنده: {best.seller_rating}"
            if best.seller_rating is not None
            else "- امتیاز فروشنده: نامشخص",
        ])

    lines.extend(["", "همه فروشنده‌ها:"])

    sorted_offers = sorted(
        filtered_offers,
        key=lambda x: (
            not bool(x.is_available),
            x.price_toman if x.price_toman is not None else 10**18,
        )
    )

    if not sorted_offers:
        lines.append("- فروشنده‌ای یافت نشد")
    else:
        for offer in sorted_offers:
            lines.append(
                f"- {offer.seller_name or 'نامشخص'} | "
                f"{'موجود' if offer.is_available else 'ناموجود'} | "
                f"قیمت: {_format_price_toman(offer.price_toman)} | "
                f"قیمت قبل: {_format_price_toman(offer.list_price_toman)} | "
                f"تخفیف: {_format_percent(offer.discount_percent)} | "
                f"گارانتی: {offer.warranty_name or 'نامشخص'}"
            )

    return "\n".join(lines)


def _build_sms_message(
    config,
    snapshot,
    filtered_offers,
    reasons,
    custom_name=None,
):
    sms_config = (
        (config or {})
        .get("notifications", {})
        .get("sms", {})
        or {}
    )

    template = sms_config.get("template") or DEFAULT_SMS_TEMPLATE

    try:
        max_reasons = int(sms_config.get("max_reasons", 3))
    except (TypeError, ValueError):
        max_reasons = 3

    if max_reasons < 0:
        max_reasons = 0

    best = best_available_offer(filtered_offers)

    display_title = custom_name or snapshot.title or f"DKP-{snapshot.product_id}"

    selected_reasons = list(reasons or [])

    if max_reasons == 0:
        selected_reasons = []
    else:
        selected_reasons = selected_reasons[:max_reasons]

    if selected_reasons:
        reasons_text = "\n".join(f"- {reason}" for reason in selected_reasons)
    else:
        reasons_text = "- اعلان جدید"

    values = {
        # Main aliases
        "product_name": display_title,
        "custom_name": custom_name or "",
        "title": snapshot.title or "نامشخص",
        "digikala_title": snapshot.title or "نامشخص",
        "product_id": snapshot.product_id,
        "dkp": snapshot.product_id,

        # Important: URL exists for compatibility,
        # but default SMS template does not use it.
        "url": snapshot.url or "",

        "availability": _product_availability_text(filtered_offers),
        "status": snapshot.status or "unknown",
        "brand": snapshot.brand or "نامشخص",
        "category": snapshot.category or "نامشخص",

        "best_seller": best.seller_name if best and best.seller_name else "نامشخص",
        "best_price": _format_price_toman(best.price_toman if best else None),
        "best_price_toman": best.price_toman if best and best.price_toman is not None else "",
        "best_list_price": _format_price_toman(best.list_price_toman if best else None),
        "best_list_price_toman": (
            best.list_price_toman
            if best and best.list_price_toman is not None
            else ""
        ),
        "discount": _format_percent(best.discount_percent if best else None),
        "discount_percent": (
            best.discount_percent
            if best and best.discount_percent is not None
            else ""
        ),
        "warranty": best.warranty_name if best and best.warranty_name else "نامشخص",
        "lead_time": best.lead_time if best and best.lead_time else "نامشخص",
        "seller_rating": (
            best.seller_rating
            if best and best.seller_rating is not None
            else "نامشخص"
        ),

        "reasons": reasons_text,
        "reason_count": len(reasons or []),
    }

    return _safe_format_template(template, values)


# Backward-compatible old function name.
def build_report(snapshot, filtered_offers, reasons, custom_name=None):
    return _build_full_report_message(
        snapshot=snapshot,
        filtered_offers=filtered_offers,
        reasons=reasons,
        custom_name=custom_name,
    )


def monitor_once(conn, config):
    notifier = Notifier(config)
    products = get_all_active_products(conn)

    settings = config.get("app", {})
    timeout = settings.get("request_timeout_seconds", 20)

    min_delay = settings.get(
        "min_delay_between_requests_seconds",
        settings.get("poll_delay_min_seconds", 1),
    )

    max_delay = settings.get(
        "max_delay_between_requests_seconds",
        settings.get("poll_delay_max_seconds", 3),
    )

    if min_delay > max_delay:
        min_delay, max_delay = max_delay, min_delay

    with httpx.Client(timeout=timeout) as client:
        for row in products:
            product_id = row["product_id"]
            url = row["url"]
            custom_name = row.get("custom_name")

            conditions = safe_json_loads(
                row.get("conditions_json"),
                default={},
            )

            time.sleep(random.uniform(min_delay, max_delay))

            try:
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
                    custom_name=custom_name,
                    title=snapshot.title,
                    brand=snapshot.brand,
                    category=snapshot.category,
                    conditions_json=json.dumps(
                        conditions,
                        ensure_ascii=False,
                    ),
                )

                insert_snapshot(conn, snapshot, filtered_offers)

                if reasons:
                    full_message = _build_full_report_message(
                        snapshot=snapshot,
                        filtered_offers=filtered_offers,
                        reasons=reasons,
                        custom_name=custom_name,
                    )

                    sms_message = _build_sms_message(
                        config=config,
                        snapshot=snapshot,
                        filtered_offers=filtered_offers,
                        reasons=reasons,
                        custom_name=custom_name,
                    )

                    sent = notifier.notify_all(
                        full_message=full_message,
                        sms_message=sms_message,
                    )

                    insert_notification(
                        conn=conn,
                        product_id=product_id,
                        title=custom_name or snapshot.title,
                        message=full_message,
                        sent_result=sent,
                    )

            except Exception as exc:
                conn.rollback()
                print(f"[ERROR] Failed to monitor product_id={product_id}: {exc}")
