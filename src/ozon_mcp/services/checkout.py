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

import re
import time
from itertools import combinations
from typing import TYPE_CHECKING, Any, Final

from ozon_mcp.dependencies import get_session
from ozon_mcp.errors import OrdersDisabledError, OzonError, TotalMismatchError
from ozon_mcp.parsing.checkout import (
    parse_checkout,
    parse_pickup_points,
    parse_prepayment_split,
    parse_shipment_items,
    pickup_apply_link,
    prepayment_link,
    shipment_detail_link,
    shipment_total,
)
from ozon_mcp.parsing.common import widget
from ozon_mcp.settings import get_settings
from ozon_mcp.utils.money import to_kopecks

if TYPE_CHECKING:
    from ozon_mcp.models.checkout import Delivery, PaymentOption, PickupPoint

from ozon_mcp.models.checkout import Checkout, OrderPlaced

# The checkout body lives in the entrypoint "second container", like the product
# description and the search facets.
_CONTAINER: Final = "layout_container=checkout&layout_page_index=2"
_CHECKOUT_PATH: Final = f"/gocheckout?{_CONTAINER}"
_CREATE_ORDER_ACTION: Final = "v2/createOrderV2"
_INIT_CHECKOUT_ACTION: Final = "initCheckoutState"
# Order creation is asynchronous: the first call schedules it and the client
# re-calls the same action until the response carries the result instead of
# another polling instruction.
_ORDER_POLL_ATTEMPTS: Final = 40
# Attributing the prepayment is a subset sum over shipments; an order with more
# than a dozen of them is not worth enumerating.
_SUBSET_LIMIT: Final = 12

# Ozon names the methods in English internals only, but a person says "СБП",
# "Ozon Банк" or "ЮMoney" — so map those words onto the `kind` the payload
# carries. Which methods are offered changes with the order's state: Ozon Card
# appears once pay-on-delivery is off, and the fast-payment option drops out.
_PAYMENT_ALIASES: Final[dict[str, str]] = {
    "озон карт": "ozoncard",
    "ozon карт": "ozoncard",
    "озон банк": "ozoncard",
    "ozon банк": "ozoncard",
    "ozon bank": "ozoncard",
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


def _fill_shipments(checkout: Checkout, data: dict[str, Any]) -> None:
    """Load each shipment's contents from its own detail view."""
    for shipment in checkout.shipments:
        link = shipment_detail_link(data, shipment.split_key or "")
        if link is None:
            continue
        shipment.items = parse_shipment_items(get_session().fetch(link, backend="entrypoint"))
        shipment.total = shipment_total(shipment.items)


def _read_prepayment_split(checkout: Checkout, data: dict[str, Any]) -> None:
    """Ask Ozon which items it charges now, instead of inferring it.

    The «Есть предоплата N ₽» row is a control: behind it Ozon lists the lines
    charged now and the lines charged on receipt. That is the authoritative
    answer, and it exists exactly when the order is split — so it is followed
    whenever the row offers a link.
    """
    link = prepayment_link(widget(data, "paymentInfoV2"))
    if link is None:
        return
    now, later = parse_prepayment_split(get_session().fetch(link, backend="entrypoint"))
    checkout.pay_after_receipt.pay_now_items = now
    checkout.pay_after_receipt.pay_on_receipt_items = later


def _attribute_shipments(checkout: Checkout) -> None:
    """Mark each shipment as prepaid or not, from the items Ozon named.

    A shipment holding items from both sides is left unset rather than forced
    into one: the split is per item, and Ozon groups the modal by payment, not
    by parcel.
    """
    prepaid = {item.title for item in checkout.pay_after_receipt.pay_now_items if item.title}
    deferred = {item.title for item in checkout.pay_after_receipt.pay_on_receipt_items if item.title}
    if not prepaid and not deferred:
        return
    for shipment in checkout.shipments:
        titles = {item.title for item in shipment.items if item.title}
        if not titles:
            continue
        if titles <= prepaid:
            shipment.prepaid = True
        elif titles <= deferred:
            shipment.prepaid = False


def _attribute_prepayment(checkout: Checkout) -> None:
    """Work out which shipments the prepayment is for, when Ozon named no items.

    Fallback for a page that offers no breakdown: eligibility is decided per
    shipment, so the one figure Ozon does print has to be some combination of
    shipment totals. When exactly one combination adds up to it, those shipments
    are the prepaid ones; when several fit, the answer is left unset, because
    naming the wrong items is worse than admitting nothing was published.
    """
    prepayment = to_kopecks(checkout.pay_after_receipt.prepayment_amount)
    shipments = checkout.shipments
    amounts = [to_kopecks(shipment.total) for shipment in shipments]
    if prepayment is None or not shipments or None in amounts or len(shipments) > _SUBSET_LIMIT:
        return
    indexes = range(len(shipments))
    matches = [
        combination
        for size in indexes
        for combination in combinations(indexes, size + 1)
        if sum(amounts[index] or 0 for index in combination) == prepayment
    ]
    if len(matches) != 1:
        return
    prepaid = set(matches[0])
    for index, shipment in enumerate(shipments):
        shipment.prepaid = index in prepaid


def _read(
    path: str = _CHECKOUT_PATH,
    *,
    with_points: bool = True,
    with_shipments: bool | None = None,
) -> Checkout:
    """Read the checkout. ``with_shipments`` defaults to loading the shipments'
    contents only when the order is split across prepaid and deferred parts —
    that is the case where knowing which items are which decides what to do.
    """
    data = get_session().fetch(path, backend="entrypoint")
    checkout = parse_checkout(data)
    if checkout.available and with_points:
        for delivery in checkout.deliveries:
            state = _address_book(delivery.change_link)
            delivery.pickup_points = parse_pickup_points(state) if state is not None else []
    if checkout.available:
        _read_prepayment_split(checkout, data)
    partial = checkout.pay_after_receipt.scope == "partial"
    if checkout.available and (partial if with_shipments is None else with_shipments):
        _fill_shipments(checkout, data)
        if checkout.pay_after_receipt.pay_now_items:
            _attribute_shipments(checkout)
        else:
            _attribute_prepayment(checkout)
    return checkout


def _with_container(link: str) -> str:
    joiner = "&" if "?" in link else "?"
    return f"{link}{joiner}{_CONTAINER}"


def _apply(link: str) -> Checkout:
    """Press one of the checkout's own control links and re-read the result.

    These controls are POSTs to the entrypoint page, not GETs: fetched instead,
    Ozon answers with a page that looks right and has changed nothing.
    ``page_changed`` is what the site sends alongside, and Ozon needs it to
    recompute the order.
    """
    joiner = "&" if "?" in link else "?"
    get_session().post_page(f"{link}{joiner}page_changed=true", {}, backend="entrypoint")
    return _read(with_points=False, with_shipments=False)


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


def _match_payment_option(options: list[PaymentOption], wanted: str) -> PaymentOption:
    """Resolve a payment method from a word, a masked card, or the raw id."""
    needle = wanted.strip().casefold()
    known_types = {option.payment_type for option in options if option.payment_type is not None}
    selectable = [option for option in options if option.apply_link or option.selected]
    options = selectable or options
    # A bare number is an id only if the order actually offers it; otherwise it
    # is a card number, which can look just as short (2044 vs 5898).
    if needle.isdigit() and int(needle) in known_types:
        return next(option for option in options if option.payment_type == int(needle))

    # A masked card: compare digits only, since Ozon writes the label "** 5898".
    digits = "".join(ch for ch in needle if ch.isdigit())
    if digits:
        for option in options:
            label_digits = "".join(ch for ch in (option.label or "") if ch.isdigit())
            if label_digits and label_digits == digits and option.payment_type is not None:
                return option

    target_kind = next((kind for alias, kind in _PAYMENT_ALIASES.items() if alias in needle), None)
    for option in options:
        kind = (option.kind or "").casefold()
        label = (option.label or "").casefold()
        # Not every method has a payment_type — Ozon Card, the credit card and
        # instalments are identified by their link alone — so requiring one here
        # would hide exactly the methods a person names most often.
        if target_kind and kind == target_kind:
            return option
        if needle and (needle in kind or needle in label):
            return option

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


def start_checkout() -> Checkout:
    """Form a checkout from the items currently ticked in the cart.

    Ozon needs this step before /gocheckout resolves to anything: without it the
    URL falls back to the cart, which reads as "nothing to order" even though
    items are selected. It is what pressing «Перейти к оформлению» does.
    """
    from ozon_mcp.services.cart import get_cart  # ruff: ignore[import-outside-top-level] - avoids a cycle

    selected = [(item.id, item.quantity or 1) for item in get_cart().items if item.checked and item.id]
    if not selected:
        return Checkout(available=False, reason="no cart items are selected — select them first")
    body = {"items": [{"id": sku, "quantity": quantity} for sku, quantity in selected]}
    get_session().action(_INIT_CHECKOUT_ACTION, body)
    return _read()


def get_checkout(shipment_items: bool | None = None) -> Checkout:
    """The order being formed, initialising it if Ozon has not done so yet."""
    checkout = _read(with_shipments=shipment_items)
    if not checkout.available and "selected" not in (checkout.reason or ""):
        return start_checkout()
    return checkout


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
    # Same entry point as get_checkout: Ozon may not have formed the order yet,
    # and a plain read of an unformed checkout reports every option as absent.
    checkout = get_checkout()
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
        checkout = _apply(link)
    if payment is not None:
        option = _match_payment_option(checkout.payment_options, payment)
        # Ozon drops the link from the method already in use, so its absence
        # means "already selected", not "cannot be selected".
        if option.apply_link and not option.selected:
            checkout = _apply(option.apply_link)
    if pay_after_receipt is not None:
        checkout = _set_pay_after_receipt(checkout, enabled=pay_after_receipt)
    if points is not None:
        checkout = _set_points(checkout, points)
    return _read()


def _set_pay_after_receipt(checkout: Checkout, *, enabled: bool) -> Checkout:
    switch = checkout.pay_after_receipt
    if not switch.available:
        # Spending points and paying on delivery are mutually exclusive, and
        # Ozon simply hides the switch rather than explaining why.
        spending = next((option for option in checkout.points if option.selected and option.amount), None)
        because = f" — points are being spent ({spending.amount}); clear them with points=0 first" if spending else ""
        msg = f"pay-on-delivery is not offered for this order{because}"
        raise OzonError(msg)
    # The link flips whatever state it finds, so press it only when the current
    # state is not the one asked for.
    if switch.enabled == enabled or not switch.toggle_link:
        return checkout
    return _apply(switch.toggle_link)


def _set_points(checkout: Checkout, points: int) -> Checkout:
    """Spend a given number of points, or none at all when passed 0.

    Ozon drops the apply link from whichever choice is already active, so a
    missing link means "already there" far more often than "not allowed" —
    treating it as an error would refuse a request that is in fact satisfied.
    """
    wanted = next((option for option in checkout.points if (option.amount or 0) == points), None)
    if wanted is None:
        offered = ", ".join(str(option.amount or 0) for option in checkout.points)
        msg = f"Ozon does not offer spending {points} points here; offered: {offered or 'none'}"
        raise OzonError(msg)
    if wanted.selected or not wanted.apply_link:
        return checkout
    return _apply(wanted.apply_link)


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def place_order(confirm_total: str) -> OrderPlaced:
    """Submit the order — this spends money and is not undoable from here.

    ``confirm_total`` must match the total Ozon is currently charging, so a
    stale plan cannot silently pay a different amount. Compared on digits only,
    since the string carries spaces, ₽ and a "сегодня" suffix.

    Creation is asynchronous: the action is re-called until it returns the order
    instead of another polling instruction, so this comes back only once the
    order actually exists.

    Both payment routes complete: paying from the Ozon Card balance settles when
    the order is created, and pay-on-delivery leaves nothing to pay today.
    ``payment_url`` is the page Ozon names for the payment, worth passing on if a
    payment ever does need finishing.
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

    session = get_session()
    for _ in range(_ORDER_POLL_ATTEMPTS):
        response = session.action(_CREATE_ORDER_ACTION, {"id": "createOrder"})
        data = response.get("data") or {}
        created = data.get("createOrderResponse")
        if isinstance(created, dict):
            link = str(created.get("link") or "")
            back = str(created.get("returnLink") or "")
            # A card order puts the number in returnLink and the confirmation
            # page in link; a pay-on-delivery order puts the number in link.
            number = re.search(r"orderNumber=([\w\-]+)", back) or re.search(r"orderNumber=([\w\-]+)", link)
            return OrderPlaced(
                order_number=number.group(1) if number else None,
                total=actual,
                order_total=checkout.totals.order_total,
                link=back or None,
                payment_url=link or None,
            )
        pooling = data.get("poolingDetails") or {}
        time.sleep((pooling.get("delay") or 500) / 1000)
    msg = "order creation did not finish in time; check the orders list before retrying"
    raise OzonError(msg)
