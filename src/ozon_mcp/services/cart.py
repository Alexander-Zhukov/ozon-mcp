"""Cart read + (gated) mutation services.

Mutation endpoints captured from a live add-to-cart:
``POST _action/v2/addToCart`` with body ``[{"id": <int>, "quantity": N}]``
(quantity 0 removes).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ozon_mcp.dependencies import get_session
from ozon_mcp.errors import WritesDisabledError
from ozon_mcp.parsing.cart import parse_cart
from ozon_mcp.parsing.common import next_page
from ozon_mcp.settings import get_settings

if TYPE_CHECKING:
    from ozon_mcp.models.cart import Cart


_MAX_CART_PAGES = 30


def _require_writes() -> None:
    if not get_settings().enable_writes:
        raise WritesDisabledError


def get_cart() -> Cart:
    """The whole cart, following the scroll pagination.

    A large cart arrives a page at a time, and a caller deciding what to order
    needs all of it — so the pages are walked here rather than exposed.
    """
    session = get_session()
    data = session.fetch("/cart")
    cart = parse_cart(data)
    seen = {item.id for item in cart.items}
    for _ in range(_MAX_CART_PAGES):
        following = next_page(data)
        if not following:
            break
        data = session.fetch(following, backend="entrypoint")
        page = parse_cart(data)
        fresh = [item for item in page.items if item.id and item.id not in seen]
        if not fresh:
            break
        seen.update(item.id for item in fresh)
        cart.items += fresh
        cart.groups += [g for g in page.groups if g not in cart.groups]
    cart.item_count = len(cart.items)
    return cart


def set_cart_quantity(sku: str, quantity: int) -> dict[str, Any]:
    _require_writes()
    return get_session().action("v2/addToCart", [{"id": int(sku), "quantity": quantity}])


def add_to_cart(sku: str, quantity: int = 1) -> dict[str, Any]:
    return set_cart_quantity(sku, quantity)


def remove_from_cart(sku: str) -> dict[str, Any]:
    return set_cart_quantity(sku, 0)
