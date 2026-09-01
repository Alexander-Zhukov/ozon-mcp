"""Cart DTOs."""

from pydantic import Field

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

    items: list[CartItem] = Field(default_factory=list, description="The items actually read.")
    item_count: int = Field(default=0, description="How many were read.")
    total_items: int | None = Field(
        default=None, description="How many Ozon says the cart holds; a difference means the read came up short."
    )
    groups: list[str] = Field(default_factory=list)
