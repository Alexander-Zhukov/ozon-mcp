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

    ``total_items`` is how many Ozon says the cart holds, against ``item_count``
    actually read. They match on a complete read; a difference means the walk
    came up short, which is worth knowing before deciding what to order.
    """

    items: list[CartItem] = []
    item_count: int = 0
    total_items: int | None = None
    groups: list[str] = []
