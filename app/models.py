from dataclasses import dataclass
from typing import Optional


@dataclass
class SellerOffer:
    seller_id: Optional[int]
    seller_name: Optional[str]
    is_available: bool
    price_toman: Optional[int]
    discount_percent: Optional[int]
    seller_rating: Optional[float]
    warranty_name: Optional[str]
    lead_time: Optional[str]
    raw: dict


@dataclass
class ProductSnapshot:
    product_id: int
    title: str
    url: str
    brand: Optional[str]
    category: Optional[str]
    status: Optional[str]
    is_available: bool
    offers: list[SellerOffer]
    raw: dict
