"""Order DTOs."""

from __future__ import annotations

from ozon_mcp.models.base import OzonModel


class OrderThumbnail(OzonModel):
    """A product thumbnail on an order row + its order-detail link."""

    photo: str | None = None
    detail_link: str | None = None


class Order(OzonModel):
    """One order as the order list shows it.

    ``order_number`` is what every other order tool takes — cancelling, paying,
    listing reasons. Ozon does not print it on the row: it is encoded in the
    row's link, so it is decoded here rather than left for the caller to dig
    out. An order split across parcels has one number per parcel, and
    ``order_numbers`` holds them all.
    """

    order_number: str | None = None
    order_numbers: list[str] = []
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
    """A product as it appears in an order."""

    sku: str
    title: str | None = None
    price: str | None = None
    variant: str | None = None
    seller: str | None = None
    url: str | None = None


class Return(OzonModel):
    """One buyer return, as the returns page lists it."""

    title: str | None = None
    status: str | None = None
    link: str | None = None
