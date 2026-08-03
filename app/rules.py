from typing import Optional

from app.models import ProductSnapshot, SellerOffer


def best_available_offer(offers: list[SellerOffer]) -> Optional[SellerOffer]:
    candidates = [
        o for o in offers
        if bool(o.is_available) and o.price_toman is not None
    ]

    if not candidates:
        return None

    return min(candidates, key=lambda x: x.price_toman)


def filter_offers(offers: list[SellerOffer], conditions: dict) -> list[SellerOffer]:
    conditions = conditions or {}
    result = offers[:]

    include_sellers = conditions.get("seller_names_include") or []
    exclude_sellers = conditions.get("seller_names_exclude") or []
    only_digikala = conditions.get("only_digikala_seller", False)
    allowed_warranties = conditions.get("allowed_warranties") or []
    blocked_warranties = conditions.get("blocked_warranties") or []

    if isinstance(include_sellers, str):
        include_sellers = [include_sellers]

    if isinstance(exclude_sellers, str):
        exclude_sellers = [exclude_sellers]

    if isinstance(allowed_warranties, str):
        allowed_warranties = [allowed_warranties]

    if isinstance(blocked_warranties, str):
        blocked_warranties = [blocked_warranties]

    include_sellers = [str(x).strip() for x in include_sellers if str(x).strip()]
    exclude_sellers = [str(x).strip() for x in exclude_sellers if str(x).strip()]
    allowed_warranties = [str(x).strip() for x in allowed_warranties if str(x).strip()]
    blocked_warranties = [str(x).strip() for x in blocked_warranties if str(x).strip()]

    if include_sellers:
        result = [
            o for o in result
            if any(name in (o.seller_name or "") for name in include_sellers)
        ]

    if exclude_sellers:
        result = [
            o for o in result
            if not any(name in (o.seller_name or "") for name in exclude_sellers)
        ]

    if only_digikala:
        result = [
            o for o in result
            if (
                "دیجی‌کالا" in (o.seller_name or "")
                or "دیجی کالا" in (o.seller_name or "")
                or "Digikala" in (o.seller_name or "")
                or "digikala" in (o.seller_name or "")
            )
        ]

    if allowed_warranties:
        result = [
            o for o in result
            if any(w in (o.warranty_name or "") for w in allowed_warranties)
        ]

    if blocked_warranties:
        result = [
            o for o in result
            if not any(w in (o.warranty_name or "") for w in blocked_warranties)
        ]

    return result


def _safe_int(value, default=None):
    if value is None or value == "":
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_previous_available_count(previous_sellers: list[dict]) -> int:
    if not previous_sellers:
        return 0

    return sum(1 for s in previous_sellers if bool(s.get("is_available")))


def evaluate_rules(
    snapshot: ProductSnapshot,
    previous_summary: dict | None,
    previous_sellers: list[dict],
    conditions: dict,
) -> list[str]:
    reasons = []

    conditions = conditions or {}
    previous_sellers = previous_sellers or []

    filtered = filter_offers(snapshot.offers, conditions)
    current_available = [o for o in filtered if bool(o.is_available)]
    current_best = best_available_offer(filtered)

    # Safe access to previous snapshot fields.
    # This avoids KeyError when older DB rows do not have standardized best_* fields.
    prev_available = previous_summary.get("is_available") if previous_summary else None

    prev_best_price = None
    prev_best_seller = None
    prev_discount = None

    if previous_summary:
        prev_best_price = (
            previous_summary.get("best_price_toman")
            if previous_summary.get("best_price_toman") is not None
            else previous_summary.get("price")
        )

        prev_best_seller = (
            previous_summary.get("best_seller_name")
            if previous_summary.get("best_seller_name") is not None
            else previous_summary.get("seller_name")
        )

        prev_discount = (
            previous_summary.get("best_discount_percent")
            if previous_summary.get("best_discount_percent") is not None
            else previous_summary.get("discount_percent")
        )

    prev_best_price = _safe_int(prev_best_price)
    prev_discount = _safe_int(prev_discount)

    # -------------------------
    # Availability changes
    # -------------------------
    if conditions.get("notify_when_available", True):
        if current_available and prev_available is False:
            reasons.append("کالا از ناموجود به موجود تغییر کرد.")

    if conditions.get("notify_when_unavailable", True):
        if not current_available and prev_available is True:
            reasons.append("کالا از موجود به ناموجود تغییر کرد.")

    # -------------------------
    # Best offer related rules
    # -------------------------
    if current_best:
        current_price = _safe_int(current_best.price_toman)
        current_discount = _safe_int(current_best.discount_percent)

        max_price = _safe_int(conditions.get("max_price_toman"))
        if max_price is not None and current_price is not None:
            if current_price <= max_price:
                # Notify if:
                # - There was no previous snapshot,
                # - or previous best price was above threshold,
                # - or the price changed while still satisfying the threshold.
                if (
                    prev_best_price is None
                    or prev_best_price > max_price
                    or prev_best_price != current_price
                ):
                    reasons.append(
                        f"قیمت به حد مطلوب رسید: {current_price:,} تومان <= {max_price:,} تومان"
                    )

        min_discount = _safe_int(conditions.get("min_discount_percent"))
        if min_discount is not None and current_discount is not None:
            if current_discount >= min_discount:
                # Notify when discount newly reaches or changes at/above target.
                if prev_discount is None or prev_discount < min_discount or prev_discount != current_discount:
                    reasons.append(f"تخفیف به حد مطلوب رسید: {current_discount}%")

        if conditions.get("notify_on_any_price_change", False):
            if (
                prev_best_price is not None
                and current_price is not None
                and prev_best_price != current_price
            ):
                reasons.append(
                    f"قیمت تغییر کرد: {prev_best_price:,} → {current_price:,} تومان"
                )

        drop_percent = conditions.get("notify_on_price_drop_percent")
        try:
            drop_percent = float(drop_percent) if drop_percent is not None else None
        except (TypeError, ValueError):
            drop_percent = None

        if drop_percent is not None and prev_best_price and current_price:
            if current_price < prev_best_price:
                change = ((prev_best_price - current_price) / prev_best_price) * 100
                if change >= drop_percent:
                    reasons.append(f"افت قیمت {change:.2f}% رخ داد.")

        if conditions.get("notify_on_seller_change", True):
            if (
                prev_best_seller
                and current_best.seller_name
                and prev_best_seller != current_best.seller_name
            ):
                reasons.append(
                    f"فروشنده ارزان‌ترین پیشنهاد تغییر کرد: {prev_best_seller} → {current_best.seller_name}"
                )

        # Avoid repeated notification on every polling.
        # Notify only when current available count crosses the threshold from below.
        min_stock_count = _safe_int(conditions.get("min_stock_count"))
        if min_stock_count is not None:
            current_count = len(current_available)
            previous_count = _get_previous_available_count(previous_sellers)

            if current_count >= min_stock_count and previous_count < min_stock_count:
                reasons.append(f"تعداد فروشنده‌های موجود به {current_count} رسید.")

    # -------------------------
    # Seller list changes
    # -------------------------
    prev_seller_names = {
        s.get("seller_name")
        for s in previous_sellers
        if s.get("seller_name")
    }

    curr_seller_names = {
        o.seller_name
        for o in filtered
        if o.seller_name
    }

    # Important:
    # If there is no previous snapshot/seller snapshot, do not treat all current sellers
    # as "new sellers" on the first monitoring run.
    has_previous_seller_snapshot = bool(previous_sellers)

    if conditions.get("notify_on_new_seller", True) and has_previous_seller_snapshot:
        new_sellers = curr_seller_names - prev_seller_names
        for seller_name in sorted(new_sellers):
            reasons.append(f"فروشنده جدید اضافه شد: {seller_name}")

    if conditions.get("notify_on_removed_seller", True) and has_previous_seller_snapshot:
        removed_sellers = prev_seller_names - curr_seller_names
        for seller_name in sorted(removed_sellers):
            reasons.append(f"فروشنده حذف شد: {seller_name}")

    # -------------------------
    # Discount change
    # -------------------------
    if conditions.get("notify_on_discount_change", True):
        if (
            prev_discount is not None
            and current_best
            and current_best.discount_percent is not None
        ):
            current_discount = _safe_int(current_best.discount_percent)
            if current_discount is not None and prev_discount != current_discount:
                reasons.append(
                    f"درصد تخفیف تغییر کرد: {prev_discount}% → {current_discount}%"
                )

    return reasons
