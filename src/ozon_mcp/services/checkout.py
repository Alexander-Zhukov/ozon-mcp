"""Checkout services: read the order being formed and adjust its options.

Reachable only on a session whose OzonID login is intact — that realm guards
checkout and does not survive a storageState snapshot, which is why the browser
runs on a persistent profile.

Every option Ozon exposes here is applied the way the site does it: a refresh of
the checkout page carrying one query parameter. Configuring several options is
therefore several refreshes, and the last response is the final state.

Placing an order spends real money, so it sits behind its own flag
(``OZON_ENABLE_ORDERS``) rather than the general write flag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from ozon_mcp.dependencies import get_session
from ozon_mcp.errors import OrdersDisabledError, OzonError
from ozon_mcp.parsing.checkout import parse_checkout, parse_pickup_points, pickup_apply_link
from ozon_mcp.parsing.common import widget
from ozon_mcp.settings import get_settings

if TYPE_CHECKING:
    from ozon_mcp.models.checkout import Checkout, Delivery

# The checkout body lives in the entrypoint "second container", like the product
# description and the search facets.
_CONTAINER: Final = "layout_container=checkout&layout_page_index=2"
_CHECKOUT_PATH: Final = f"/gocheckout?{_CONTAINER}"
_CREATE_ORDER_ACTION: Final = "v2/createOrderV2"


def _address_book(link: str | None) -> Any:
    """The address-book modal state behind a destination's change link."""
    if not link:
        return None
    return widget(get_session().fetch(link, backend="entrypoint"), "commonAddressBook")


def _read(path: str = _CHECKOUT_PATH, *, with_points: bool = True) -> Checkout:
    checkout = parse_checkout(get_session().fetch(path, backend="entrypoint"))
    if checkout.available and with_points:
        for delivery in checkout.deliveries:
            state = _address_book(delivery.change_link)
            delivery.pickup_points = parse_pickup_points(state) if state is not None else []
    return checkout


def _with_container(link: str) -> str:
    joiner = "&" if "?" in link else "?"
    return f"{link}{joiner}{_CONTAINER}"


def _target_delivery(checkout: Checkout, split_key: str | None) -> Delivery:
    """Which destination to retarget.

    With one destination the choice is unambiguous; with several the caller has
    to name the shipment, because silently moving the wrong parcel is worse than
    refusing.
    """
    deliveries = checkout.deliveries
    if not deliveries:
        msg = "checkout exposes no destination to change"
        raise OzonError(msg)
    if split_key is not None:
        for delivery in deliveries:
            if split_key in delivery.split_keys:
                return delivery
        msg = f"no shipment {split_key} in this order"
        raise OzonError(msg)
    if len(deliveries) > 1:
        keys = ", ".join(key for delivery in deliveries for key in delivery.split_keys)
        msg = f"order has several destinations; pass split_key (one of: {keys})"
        raise OzonError(msg)
    return deliveries[0]


def get_checkout() -> Checkout:
    return _read()


def configure_checkout(
    payment_type: int | None = None,
    points: int | None = None,
    pay_after_receipt: bool | None = None,
    pickup_point_id: str | None = None,
    split_key: str | None = None,
) -> Checkout:
    """Apply the given options and return the recomputed checkout.

    Applied in the order Ozon recalculates them: destination first (it can
    change what payment is possible), then payment, then the pay-on-delivery
    switch, then points.
    """
    checkout = _read(with_points=False)
    if not checkout.available:
        return checkout

    if pickup_point_id is not None:
        delivery = _target_delivery(checkout, split_key)
        link = pickup_apply_link(_address_book(delivery.change_link), pickup_point_id)
        if link is None:
            msg = f"pickup point {pickup_point_id} is not selectable for this shipment"
            raise OzonError(msg)
        checkout = _read(_with_container(link), with_points=False)
    if payment_type is not None:
        checkout = _read(f"/gocheckout?payment_type={payment_type}&set_payment=0&{_CONTAINER}", with_points=False)
    if pay_after_receipt is not None:
        disabled = 0 if pay_after_receipt else 1
        checkout = _read(f"/gocheckout?post_payment_disabled={disabled}&set_payment=0&{_CONTAINER}", with_points=False)
    if points is not None:
        checkout = _read(f"/gocheckout?points_applied={points}.00&set_payment=0&{_CONTAINER}", with_points=False)
    return _read()


def place_order() -> dict[str, Any]:
    """Submit the order — this spends money and is not undoable from here."""
    if not get_settings().enable_orders:
        raise OrdersDisabledError
    return get_session().action(_CREATE_ORDER_ACTION, {"id": "createOrder"})
