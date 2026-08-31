"""Cart DTOs."""

from __future__ import annotations

from ozon_mcp.models.base import OzonModel


class CartItem(OzonModel):
    id: str | None = None
    title: str | None = None
    price: str | None = None
    quantity: int | None = None
    max_quantity: int | None = None
    checked: bool | None = None
    is_favorite: bool | None = None


class Cart(OzonModel):
    items: list[CartItem] = []
    item_count: int = 0
