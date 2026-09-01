"""Cart read + (gated) mutation services.

Two different mechanisms, both captured live:

- quantity (and removal, at quantity 0) is an ``_action`` endpoint,
  ``POST _action/v2/addToCart`` with ``[{"id": <int>, "quantity": N}]``;
- the tick next to each item is a page command posted to the cart's own JSON
  URL, ``{"name": "selectItems", "params": "{...}"}``.

The ticks matter more than they look: they are what composes an order. Ozon
builds the checkout from the selected items, so nothing can be ordered until
something is ticked.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

from ozon_mcp.dependencies import get_session
from ozon_mcp.errors import OzonError, WritesDisabledError
from ozon_mcp.models.common import WriteResult
from ozon_mcp.parsing.cart import parse_cart
from ozon_mcp.parsing.common import next_page
from ozon_mcp.settings import get_settings

if TYPE_CHECKING:
    from ozon_mcp.models.cart import Cart


_MAX_CART_PAGES = 30

# Modes Ozon itself sends from the checkboxes; SPECIFIED variants are idempotent
# (they set a state, they do not toggle).
_SELECT: Final = "MODE_SELECT_SPECIFIED"
_UNSELECT: Final = "MODE_UNSELECT_SPECIFIED"
_SELECT_ALL: Final = "MODE_SELECT_ALL"
SELECTION_MODES: Final = ("only", "add", "remove", "all", "none")


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
            # An empty page reads the same as the end of the cart, so ask once
            # more before believing it.
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


def set_cart_quantity(sku: str, quantity: int) -> WriteResult:
    """Set how many of a product are in the cart; 0 removes it.

    The result is read back from the cart instead of taken from Ozon's answer,
    which reports nothing either way: adding an unknown SKU, asking for more
    than exists and a change that worked all return the same fragment. The
    ordinary mistakes are exactly the silent ones — a base apparel SKU with no
    size chosen, a product out of stock — so the cart is what settles it.
    """
    _require_writes()
    get_session().action("v2/addToCart", [{"id": int(sku), "quantity": quantity}])
    found = next((item for item in get_cart().items if item.id == str(sku)), None)
    in_cart = found.quantity if found else 0
    if in_cart == quantity:
        return WriteResult()
    if found is None:
        return WriteResult(
            ok=False,
            detail=(
                f"the cart holds no {sku} — Ozon accepted the call and changed nothing. "
                "For apparel use the variant SKU from product_details(); otherwise the product "
                "is out of stock or not orderable."
            ),
        )
    return WriteResult(ok=False, detail=f"the cart holds {in_cart}, not the requested {quantity}")


def _send_selection(mode: str, skus: list[str] | None = None) -> None:
    params: dict[str, Any] = {"mode": mode}
    if skus is not None:
        params["items"] = [str(sku) for sku in skus]
    body = {"name": "selectItems", "params": json.dumps(params, ensure_ascii=False)}
    get_session().post_page("/cart", body)


def select_cart_items(skus: list[str] | None = None, mode: str = "only") -> Cart:
    """Choose which cart items form the order.

    ``only`` is the useful default: "order exactly these" is what a person
    actually asks for, and it should not require unticking everything else by
    hand. The other modes map straight onto Ozon's own commands.
    """
    _require_writes()
    if mode not in SELECTION_MODES:
        msg = f"unknown mode {mode!r}; use one of {', '.join(SELECTION_MODES)}"
        raise OzonError(msg)
    wanted = [str(sku) for sku in skus or []]
    if mode in {"only", "add", "remove"} and not wanted:
        msg = f"mode {mode!r} needs at least one sku"
        raise OzonError(msg)

    if mode == "all":
        _send_selection(_SELECT_ALL)
    elif mode == "add":
        _send_selection(_SELECT, wanted)
    elif mode == "remove":
        _send_selection(_UNSELECT, wanted)
    else:
        checked = [item.id for item in get_cart().items if item.checked and item.id]
        if mode == "none":
            if checked:
                _send_selection(_UNSELECT, checked)
        else:  # only
            _send_selection(_SELECT, wanted)
            extra = [sku for sku in checked if sku not in wanted]
            if extra:
                _send_selection(_UNSELECT, extra)
    return get_cart()
