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
    if isinstance(seller.get("rating"), dict):
        seller_rating = seller["rating"].get("total_rate")

    lead_time = None
    providers = shipment_methods.get("providers")
    if isinstance(providers, list) and providers:
        lead_time = providers[0].get("title")

    variant_status = (variant.get("status") or "").lower()
    has_price = bool(price.get("selling_price"))

    is_available = (
        bool(variant.get("available"))
        or variant_status in ("marketable", "in_stock")
        or has_price
    )

    return SellerOffer(
        seller_id=seller.get("id"),
        seller_name=seller.get("title"),
        is_available=is_available,
        price_toman=rial_to_toman(price.get("selling_price")),
        discount_percent=price.get("discount_percent"),
        seller_rating=seller_rating,
        warranty_name=warranty.get("title_fa") or warranty.get("title"),
        lead_time=lead_time,
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
