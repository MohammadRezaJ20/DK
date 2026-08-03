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
        m = re.search(pattern, url)
        if m:
            return int(m.group(1))
    raise ValueError(f"Cannot extract product_id from URL: {url}")


def rial_to_toman(value):
    if value is None:
        return None
    return int(value) // 10

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
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError)),
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
        raise httpx.HTTPStatusError("Rate limit", request=response.request, response=response)

    response.raise_for_status()
    return response.json()


def parse_offer(variant: dict) -> SellerOffer:
    seller = variant.get("seller") or {}
    price = variant.get("price") or {}
    shipment_methods = variant.get("shipment_methods") or {}
    warranty = variant.get("warranty") or {}

    seller_rating = None
    rating_data = seller.get("rating")
    if isinstance(rating_data, dict):
        seller_rating = safe_float(
            rating_data.get("total_rate")
            or rating_data.get("rate")
            or rating_data.get("score")
        )
    else:
        seller_rating = safe_float(rating_data)

    lead_time = None
    lead_time_days = None

    providers = shipment_methods.get("providers")
    if isinstance(providers, list) and providers:
        lead_time = providers[0].get("title")
        lead_time_days = (
            safe_int(providers[0].get("lead_time"))
            or safe_int(providers[0].get("lead_time_days"))
            or extract_first_int(lead_time)
        )

    variant_status = (variant.get("status") or "").lower()
    selling_price = safe_int(price.get("selling_price"))
    rrp_price = safe_int(price.get("rrp_price"))

    is_available = (
        bool(variant.get("available"))
        or variant_status in ("marketable", "in_stock")
        or selling_price is not None
    )

    return SellerOffer(
        seller_id=safe_int(seller.get("id")),
        seller_name=seller.get("title") or seller.get("name") or "Unknown Seller",
        is_available=is_available,
        price_toman=rial_to_toman(selling_price),
        list_price_toman=rial_to_toman(rrp_price),
        discount_percent=safe_int(price.get("discount_percent")),
        seller_rating=seller_rating,
        rating=seller_rating,
        warranty_name=warranty.get("title_fa") or warranty.get("title"),
        lead_time=lead_time,
        lead_time_days=lead_time_days,
        raw=variant,
    )

def parse_product(product_id: int, url: str, payload: dict) -> ProductSnapshot:
    product = safe_get(payload, ["data", "product"], {})
    title = product.get("title_fa") or product.get("title_en") or f"Product {product_id}"
    brand = safe_get(product, ["brand", "title_fa"]) or safe_get(product, ["brand", "title_en"])
    category = safe_get(product, ["category", "title_fa"]) or safe_get(product, ["category", "title_en"])
    status = product.get("status")

    variants = product.get("variants") or []
    offers = [parse_offer(v) for v in variants]

    is_available = any(o.is_available for o in offers)


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
