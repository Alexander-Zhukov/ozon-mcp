"""Checkout services: read the order being formed, adjust payment and points.

Reachable only on a session whose OzonID login is intact — that realm guards
checkout and does not survive a storageState snapshot, which is why the browser
runs on a persistent profile.

Placing an order spends real money, so it sits behind its own flag
(``OZON_ENABLE_ORDERS``) rather than the general write flag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from ozon_mcp.dependencies import get_session
from ozon_mcp.errors import OrdersDisabledError
from ozon_mcp.parsing.checkout import parse_checkout
from ozon_mcp.settings import get_settings

if TYPE_CHECKING:
    from ozon_mcp.models.checkout import Checkout

# The checkout body lives in the entrypoint "second container", like the product
# description and the search facets.
_CHECKOUT_PATH: Final = "/gocheckout?layout_container=checkout&layout_page_index=2"
_CREATE_ORDER_ACTION: Final = "v2/createOrderV2"


def _read(path: str = _CHECKOUT_PATH) -> Checkout:
    return parse_checkout(get_session().fetch(path, backend="entrypoint"))


def get_checkout() -> Checkout:
    return _read()


def set_payment_method(payment_type: int) -> Checkout:
    """Select a payment method and return the recomputed checkout.

    Selection is a page refresh with ``payment_type`` — the same thing the site
    does when you click the method.
    """
    path = f"/gocheckout?payment_type={payment_type}&set_payment=0&layout_container=checkout&layout_page_index=2"
    return _read(path)


def apply_points(amount: int) -> Checkout:
    """Spend ``amount`` points on this order; 0 clears the deduction."""
    path = f"/gocheckout?points_applied={amount}.00&set_payment=0&layout_container=checkout&layout_page_index=2"
    return _read(path)


def set_pay_after_receipt(*, enabled: bool) -> Checkout:
    """Turn "pay on delivery for part of the order" on or off.

    Ozon models it as ``post_payment_disabled``, so the flag is inverted here to
    read the way the site labels the switch.
    """
    path = (
        f"/gocheckout?post_payment_disabled={0 if enabled else 1}&set_payment=0"
        "&layout_container=checkout&layout_page_index=2"
    )
    return _read(path)


def place_order() -> dict[str, Any]:
    """Submit the order — this spends money and is not undoable from here."""
    if not get_settings().enable_orders:
        raise OrdersDisabledError
    return get_session().action(_CREATE_ORDER_ACTION, {"id": "createOrder"})
