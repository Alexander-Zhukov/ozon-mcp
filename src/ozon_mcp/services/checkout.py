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
from ozon_mcp.errors import OrdersDisabledError, OzonError, TotalMismatchError
from ozon_mcp.parsing.checkout import parse_checkout, parse_pickup_points, pickup_apply_link
from ozon_mcp.parsing.common import widget
from ozon_mcp.settings import get_settings

if TYPE_CHECKING:
    from ozon_mcp.models.checkout import Checkout, Delivery, PaymentOption, PickupPoint

# The checkout body lives in the entrypoint "second container", like the product
# description and the search facets.
_CONTAINER: Final = "layout_container=checkout&layout_page_index=2"
_CHECKOUT_PATH: Final = f"/gocheckout?{_CONTAINER}"
_CREATE_ORDER_ACTION: Final = "v2/createOrderV2"

# Ozon names the methods in English internals only, but a person says "СБП" or
# "ЮMoney" — so map the words onto the `kind` the payload carries.
_PAYMENT_ALIASES: Final[dict[str, str]] = {
    "сбп": "fastpaymentsystem",
    "быстры": "fastpaymentsystem",
    "fast": "fastpaymentsystem",
    "сбер": "sberpay",
    "sber": "sberpay",
    "юmoney": "yoomoney",
    "юмани": "yoomoney",
    "yoomoney": "yoomoney",
    "нов": "newcard",
    "new": "newcard",
}


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


def _match_pickup(points: list[PickupPoint], wanted: str) -> PickupPoint:
    """Resolve a pickup point from whatever the user actually said.

    Agents get "в Данилова" or "№1449460" from a person, not a UUID, so accept
    the address-book id, the point number, or a substring of the address.
    """
    needle = wanted.strip().lstrip("№#").casefold()
    available = [point for point in points if point.available]
    for point in available:
        if point.address_book_id == wanted or (point.number or "").casefold() == needle:
            return point
    matches = [point for point in available if needle and needle in (point.address or "").casefold()]
    if len(matches) == 1:
        return matches[0]
    if matches:
        options = "; ".join(f"№{p.number} {p.address}" for p in matches)
        msg = f"{wanted!r} matches several pickup points: {options}"
        raise OzonError(msg)
    options = "; ".join(f"№{p.number} {p.address}" for p in available) or "none"
    msg = f"no selectable pickup point matches {wanted!r}; available: {options}"
    raise OzonError(msg)


def _match_payment(options: list[PaymentOption], wanted: str) -> int:
    """Resolve a payment method from a word, a masked card, or the raw id."""
    needle = wanted.strip().casefold()
    known_types = {option.payment_type for option in options if option.payment_type is not None}
    # A bare number is an id only if the order actually offers it; otherwise it
    # is a card number, which can look just as short (2044 vs 5898).
    if needle.isdigit() and int(needle) in known_types:
        return int(needle)

    # A masked card: compare digits only, since Ozon writes the label "** 5898".
    digits = "".join(ch for ch in needle if ch.isdigit())
    if digits:
        for option in options:
            label_digits = "".join(ch for ch in (option.label or "") if ch.isdigit())
            if label_digits and label_digits == digits and option.payment_type is not None:
                return option.payment_type

    target_kind = next((kind for alias, kind in _PAYMENT_ALIASES.items() if alias in needle), None)
    for option in options:
        kind = (option.kind or "").casefold()
        label = (option.label or "").casefold()
        if option.payment_type is None:
            continue
        if target_kind and kind == target_kind:
            return option.payment_type
        if needle and (needle in kind or needle in label):
            return option.payment_type

    known = "; ".join(f"{o.payment_type}={o.kind or ''} {o.label or ''}".strip() for o in options)
    msg = f"no payment method matches {wanted!r}; available: {known}"
    raise OzonError(msg)


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
    payment: str | None = None,
    points: int | None = None,
    pay_after_receipt: bool | None = None,
    pickup_point: str | None = None,
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

    if pickup_point is not None:
        delivery = _target_delivery(checkout, split_key)
        state = _address_book(delivery.change_link)
        chosen = _match_pickup(parse_pickup_points(state), pickup_point)
        link = pickup_apply_link(state, chosen.address_book_id or "")
        if link is None:
            msg = f"pickup point {chosen.address} is not selectable for this shipment"
            raise OzonError(msg)
        checkout = _read(_with_container(link), with_points=False)
    if payment is not None:
        payment_type = _match_payment(checkout.payment_options, payment)
        checkout = _read(f"/gocheckout?payment_type={payment_type}&set_payment=0&{_CONTAINER}", with_points=False)
    if pay_after_receipt is not None:
        disabled = 0 if pay_after_receipt else 1
        checkout = _read(f"/gocheckout?post_payment_disabled={disabled}&set_payment=0&{_CONTAINER}", with_points=False)
    if points is not None:
        checkout = _read(f"/gocheckout?points_applied={points}.00&set_payment=0&{_CONTAINER}", with_points=False)
    return _read()


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def place_order(confirm_total: str) -> dict[str, Any]:
    """Submit the order — this spends money and is not undoable from here.

    ``confirm_total`` must match the total Ozon is currently charging, so a
    stale plan cannot silently pay a different amount. Compared on digits only,
    since the string carries spaces, ₽ and a "сегодня" suffix.
    """
    if not get_settings().enable_orders:
        raise OrdersDisabledError
    checkout = _read(with_points=False)
    if not checkout.available:
        msg = checkout.reason or "no order to place"
        raise OzonError(msg)
    actual = checkout.totals.total
    if _digits(confirm_total) != _digits(actual):
        raise TotalMismatchError(confirm_total, actual)
    return get_session().action(_CREATE_ORDER_ACTION, {"id": "createOrder"})
