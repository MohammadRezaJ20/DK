import re
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.models import ProductSnapshot, SellerOffer


def extract_product_id(url: str) -> int:
    patterns = [
        r"dkp-(\d+)",
        r"/product/(\d+)",
        r"product/.*?-(\d+)/?",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return int(match.group(1))

    raise ValueError(f"Cannot extract product_id from URL: {url}")


def rial_to_toman(value):
    if value is None:
        return None

    try:
        return int(value) // 10
    except (TypeError, ValueError):
        return None


def safe_int(value, default=None):
    if value is None or value == "":
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=None):
    if value is None or value == "":
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_first_int(text):
    if not text:
        return None

    match = re.search(r"\d+", str(text))
    if not match:
        return None

    return int(match.group(0))


def safe_get(data: dict, path: list[str], default=None):
    current = data

    for key in path:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


@retry(
    retry=retry_if_exception_type(
        (
            httpx.TimeoutException,
            httpx.TransportError,
            httpx.HTTPStatusError,
        )
    ),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=60),
)
def fetch_product(client: httpx.Client, product_id: int) -> dict[str, Any]:
    url = f"https://api.digikala.com/v2/product/{product_id}/"

    response = client.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 compatible; digikala-monitor/2.0",
            "Accept": "application/json",
        },
    )

    if response.status_code == 429:
        raise httpx.HTTPStatusError(
            "Rate limit",
            request=response.request,
            response=response,
        )

    response.raise_for_status()
    return response.json()


def _extract_seller_rating(seller: dict):
    rating_data = seller.get("rating")

    if isinstance(rating_data, dict):
        return safe_float(
            rating_data.get("total_rate")
            or rating_data.get("rate")
            or rating_data.get("score")
        )

    return safe_float(rating_data)


def _extract_lead_time(shipment_methods: dict):
    lead_time = None
    lead_time_days = None

    providers = shipment_methods.get("providers")

    if isinstance(providers, list) and providers:
        first_provider = providers[0] or {}

        if isinstance(first_provider, dict):
            lead_time = (
                first_provider.get("title")
                or first_provider.get("description")
                or first_provider.get("label")
            )

            lead_time_days = (
                safe_int(first_provider.get("lead_time"))
                or safe_int(first_provider.get("lead_time_days"))
                or safe_int(first_provider.get("delivery_days"))
                or extract_first_int(lead_time)
            )

    return lead_time, lead_time_days


def _extract_warranty_name(warranty: dict):
    if not isinstance(warranty, dict):
        return None

    return (
        warranty.get("title_fa")
        or warranty.get("title")
        or warranty.get("name")
    )


def _is_variant_available(variant: dict, selling_price: int | None) -> bool:
    """
    Important fix:
    Do not mark a variant as available only because selling_price exists.
    Some Digikala payloads may keep price fields for inactive/unavailable variants.
    Availability should come from explicit availability/status/stock/marketability signals.
    """

    if bool(variant.get("available")):
        return True

    variant_status = str(variant.get("status") or "").lower().strip()

    available_statuses = {
        "marketable",
        "in_stock",
        "available",
        "active",
    }

    unavailable_statuses = {
        "inactive",
        "out_of_stock",
        "out-of-stock",
        "unavailable",
        "not_available",
        "not-available",
        "stopped",
        "disabled",
    }

    if variant_status in available_statuses:
        return True

    if variant_status in unavailable_statuses:
        return False

    # Some payloads expose stock or quantity explicitly.
    stock = (
        safe_int(variant.get("stock"))
        or safe_int(variant.get("quantity"))
        or safe_int(variant.get("seller_stock"))
    )

    if stock is not None and stock > 0:
        return True

    # Some payloads expose marketplace flag.
    if variant.get("marketable") is True:
        return True

    # Conservative fallback:
    # price alone is not enough to consider a variant available.
    return False


def parse_offer(variant: dict) -> SellerOffer:
    variant = variant or {}

    seller = variant.get("seller") or {}
    price = variant.get("price") or {}
    shipment_methods = variant.get("shipment_methods") or {}
    warranty = variant.get("warranty") or {}

    if not isinstance(seller, dict):
        seller = {}

    if not isinstance(price, dict):
        price = {}

    if not isinstance(shipment_methods, dict):
        shipment_methods = {}

    if not isinstance(warranty, dict):
        warranty = {}

    seller_rating = _extract_seller_rating(seller)

    lead_time, lead_time_days = _extract_lead_time(shipment_methods)

    selling_price = safe_int(price.get("selling_price"))
    rrp_price = safe_int(price.get("rrp_price"))

    is_available = _is_variant_available(variant, selling_price)

    return SellerOffer(
        seller_id=safe_int(seller.get("id")),
        seller_name=(
            seller.get("title")
            or seller.get("name")
            or seller.get("title_fa")
            or "Unknown Seller"
        ),
        is_available=is_available,
        price_toman=rial_to_toman(selling_price),
        list_price_toman=rial_to_toman(rrp_price),
        discount_percent=safe_int(price.get("discount_percent")),
        seller_rating=seller_rating,
        rating=seller_rating,
        warranty_name=_extract_warranty_name(warranty),
        lead_time=lead_time,
        lead_time_days=lead_time_days,
        raw=variant,
    )


def parse_product(product_id: int, url: str, payload: dict) -> ProductSnapshot:
    payload = payload or {}

    product = safe_get(payload, ["data", "product"], {})

    if not isinstance(product, dict):
        product = {}

    title = (
        product.get("title_fa")
        or product.get("title_en")
        or product.get("title")
        or f"Product {product_id}"
    )

    brand = (
        safe_get(product, ["brand", "title_fa"])
        or safe_get(product, ["brand", "title_en"])
        or safe_get(product, ["brand", "title"])
    )

    category = (
        safe_get(product, ["category", "title_fa"])
        or safe_get(product, ["category", "title_en"])
        or safe_get(product, ["category", "title"])
    )

    status = product.get("status")

    variants = product.get("variants") or []
    if not isinstance(variants, list):
        variants = []

    offers = [parse_offer(variant) for variant in variants if isinstance(variant, dict)]

    is_available = any(bool(o.is_available) for o in offers)

    return ProductSnapshot(
        product_id=product_id,
        title=title,
        url=url,
        brand=brand,
        category=category,
        status=status,
        is_available=is_available,
        offers=offers,
        raw=payload,
    )
