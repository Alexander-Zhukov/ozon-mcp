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
    group: str | None = None
    is_favorite: bool | None = None


class Cart(OzonModel):
    """The whole cart, paginated through.

    ``groups`` are Ozon's own headings ("Доступны для заказа", "Бронирование
    товаров", …); an item's ``group`` says which one it came from, because that
    is what decides whether it can be ordered at all.
    """

    items: list[CartItem] = []
    item_count: int = 0
    groups: list[str] = []
