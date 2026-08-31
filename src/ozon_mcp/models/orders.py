"""Order DTOs."""

from __future__ import annotations

from ozon_mcp.models.base import OzonModel


class OrderThumbnail(OzonModel):
    """A product thumbnail on an order row + its order-detail link."""

    photo: str | None = None
    detail_link: str | None = None


class Order(OzonModel):
    pickup: str | None = None
    slot: str | None = None
    delivery_eta: str | None = None
    status: str | None = None
    date: str | None = None
    total: str | None = None
    items_count: int = 0
    products: list[OrderThumbnail] = []
    detail_link: str | None = None
    order_ids: list[int] = []


class OrderProduct(OzonModel):
    """A product resolved from an order-detail page."""

    sku: str
    title: str | None = None
    url: str | None = None
