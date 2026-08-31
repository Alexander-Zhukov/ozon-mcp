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
from ozon_mcp.settings import get_settings

if TYPE_CHECKING:
    from ozon_mcp.models.cart import Cart


def _require_writes() -> None:
    if not get_settings().enable_writes:
        raise WritesDisabledError


def get_cart() -> Cart:
    return parse_cart(get_session().fetch("/cart"))


def set_cart_quantity(sku: str, quantity: int) -> dict[str, Any]:
    _require_writes()
    return get_session().action("v2/addToCart", [{"id": int(sku), "quantity": quantity}])


def add_to_cart(sku: str, quantity: int = 1) -> dict[str, Any]:
    return set_cart_quantity(sku, quantity)


def remove_from_cart(sku: str) -> dict[str, Any]:
    return set_cart_quantity(sku, 0)
