"""The cart, and the ticks that decide what an order contains."""

from typing import Annotated

from pydantic import Field

from ozon_mcp.dependencies import run_blocking
from ozon_mcp.mcp_server import mcp
from ozon_mcp.models.cart import Cart
from ozon_mcp.models.common import WriteResult
from ozon_mcp.services import cart
from ozon_mcp.utils.annotations import CartSelectMode, Sku


@mcp.tool()
async def get_cart() -> Cart:
    """The whole cart (paginated through): items with title, price, quantity and
    `checked` — the tick is what decides the order's contents — plus Ozon's own
    group headings ("Доступны для заказа", «Бронирование товаров»).
    """
    return await run_blocking(cart.get_cart)


@mcp.tool()
async def set_cart_quantity(
    sku: Sku,
    quantity: Annotated[int, Field(ge=0, le=999, description="Desired quantity in the cart; 0 removes the item.")],
) -> WriteResult:
    """[GATED by writes_enabled] Set how many of a product are in the cart.
    Adding, changing and removing are all this one call: quantity=0 removes.
    Ozon reports nothing about the outcome, so the cart is read back: `ok=false`
    with the reason in `detail` means the call was accepted and changed nothing
    — an out-of-stock product, or an apparel base SKU with no size chosen (use
    the variant sku from product_details()).
    Being in the cart is not being in the order: tick it with
    select_cart_items() before checkout.
    """
    return await run_blocking(lambda: cart.set_cart_quantity(sku, quantity))


@mcp.tool()
async def select_cart_items(
    skus: Annotated[
        list[str] | None,
        Field(description='Cart item ids (the `id` field of get_cart().items). Required for "only", "add", "remove".'),
    ] = None,
    mode: CartSelectMode = "only",
) -> Cart:
    """[GATED by writes_enabled] Choose which cart items make up the order.
    This is the step that composes a checkout: get_checkout() reports nothing
    orderable until something is ticked, and it orders exactly what is ticked —
    so "buy these two" is mode="only" with those two skus, whatever else the
    cart holds. Returns the cart as it is afterwards, so the ticks can be
    checked before ordering.
    """
    return await run_blocking(lambda: cart.select_cart_items(skus, mode))
