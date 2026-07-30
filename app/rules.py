from typing import Optional
from app.models import ProductSnapshot, SellerOffer


def best_available_offer(offers: list[SellerOffer]) -> Optional[SellerOffer]:
    candidates = [o for o in offers if o.is_available and o.price_toman is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda x: x.price_toman)


def filter_offers(offers: list[SellerOffer], conditions: dict) -> list[SellerOffer]:
    result = offers[:]

    include_sellers = conditions.get("seller_names_include") or []
    exclude_sellers = conditions.get("seller_names_exclude") or []
    only_digikala = conditions.get("only_digikala_seller", False)
    allowed_warranties = conditions.get("allowed_warranties") or []
    blocked_warranties = conditions.get("blocked_warranties") or []

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
            if "دیجی‌کالا" in (o.seller_name or "") or "دیجی کالا" in (o.seller_name or "")
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


def evaluate_rules(
    snapshot: ProductSnapshot,
    previous_summary: dict | None,
    previous_sellers: list[dict],
    conditions: dict,
) -> list[str]:
    reasons = []

    filtered = filter_offers(snapshot.offers, conditions)
    current_available = [o for o in filtered if o.is_available]
    current_best = best_available_offer(filtered)

    prev_available = previous_summary["is_available"] if previous_summary else None
    prev_best_price = previous_summary["best_price_toman"] if previous_summary else None
    prev_best_seller = previous_summary["best_seller_name"] if previous_summary else None
    prev_discount = previous_summary["best_discount_percent"] if previous_summary else None

    if conditions.get("notify_when_available", True):
        if current_available and prev_available is False:
            reasons.append("کالا از ناموجود به موجود تغییر کرد.")

    if conditions.get("notify_when_unavailable", True):
        if not current_available and prev_available is True:
            reasons.append("کالا از موجود به ناموجود تغییر کرد.")

    if current_best:
        max_price = conditions.get("max_price_toman")
        if max_price is not None and current_best.price_toman is not None:
            if current_best.price_toman <= max_price:
                if prev_best_price is None or prev_best_price > max_price or prev_best_price != current_best.price_toman:
                    reasons.append(
                        f"قیمت به حد مطلوب رسید: {current_best.price_toman:,} تومان <= {max_price:,} تومان"
                    )

        min_discount = conditions.get("min_discount_percent")
        if min_discount is not None and current_best.discount_percent is not None:
            if current_best.discount_percent >= min_discount:
                if prev_discount != current_best.discount_percent:
                    reasons.append(f"تخفیف به حد مطلوب رسید: {current_best.discount_percent}%")

        if conditions.get("notify_on_any_price_change", False):
            if prev_best_price is not None and current_best.price_toman is not None and prev_best_price != current_best.price_toman:
                reasons.append(
                    f"قیمت تغییر کرد: {prev_best_price:,} → {current_best.price_toman:,} تومان"
                )

        drop_percent = conditions.get("notify_on_price_drop_percent")
        if drop_percent is not None and prev_best_price and current_best.price_toman:
            if current_best.price_toman < prev_best_price:
                change = ((prev_best_price - current_best.price_toman) / prev_best_price) * 100
                if change >= drop_percent:
                    reasons.append(f"افت قیمت {change:.2f}% رخ داد.")

        if conditions.get("notify_on_seller_change", True):
            if prev_best_seller and current_best.seller_name and prev_best_seller != current_best.seller_name:
                reasons.append(
                    f"فروشنده ارزان‌ترین پیشنهاد تغییر کرد: {prev_best_seller} → {current_best.seller_name}"
                )

        min_stock_count = conditions.get("min_stock_count")
        if min_stock_count is not None:
            if len(current_available) >= min_stock_count:
                reasons.append(f"تعداد فروشنده‌های موجود به {len(current_available)} رسید.")

    prev_seller_names = {s["seller_name"] for s in previous_sellers}
    curr_seller_names = {o.seller_name for o in filtered if o.seller_name}

    if conditions.get("notify_on_new_seller", True):
        new_sellers = curr_seller_names - prev_seller_names
        for s in sorted(new_sellers):
            reasons.append(f"فروشنده جدید اضافه شد: {s}")

    if conditions.get("notify_on_removed_seller", True):
        removed_sellers = prev_seller_names - curr_seller_names
        for s in sorted(removed_sellers):
            reasons.append(f"فروشنده حذف شد: {s}")

    if conditions.get("notify_on_discount_change", True):
        if prev_discount is not None and current_best and current_best.discount_percent is not None:
            if prev_discount != current_best.discount_percent:
                reasons.append(
                    f"درصد تخفیف تغییر کرد: {prev_discount}% → {current_best.discount_percent}%"
                )

    return reasons
