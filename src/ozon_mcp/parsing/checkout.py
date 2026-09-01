"""Parse the checkout widgets (entrypoint second container) into DTOs.

Layout, verified live: ``paymentInfoV2`` holds the payment methods, each
selectable through a refresh link carrying ``payment_type``; ``rfbsAddressInfo``
holds the delivery mode tabs and the pickup address; ``rfbsSplitHeader`` the
per-shipment dates; ``total`` the money rows plus the create-order action;
``premiumPointsToggle`` the points choices.
"""

from __future__ import annotations

import re
from typing import Any

from ozon_mcp.models.checkout import (
    Checkout,
    Delivery,
    DeliveryPart,
    PayAfterReceipt,
    PaymentOption,
    PickupPoint,
    PointsOption,
    TotalRow,
    Totals,
)
from ozon_mcp.parsing.common import find_all, walk, widget, widgets_all

_PAYMENT_TYPE_RE = re.compile(r"payment_type=(\d+)")
_POINTS_RE = re.compile(r"points_applied=([\d.]+)")
_DIGITS_RE = re.compile(r"\d+")
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_RECIPIENT_RE = re.compile(r"^[А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+\s+\d{6,}$")
_DELIVERY_RE = re.compile(r"Достав(?:ка|им)\s+\d")
_SPLIT_KEY_RE = re.compile(r"split_key=([A-Za-z0-9\-]+)")


def _text(node: Any) -> str | None:
    """Text of a node that may be a bare string or a ``{"text": …}`` atom."""
    if isinstance(node, str):
        return str(node).strip() or None
    if isinstance(node, dict):
        value = node.get("text")
        if isinstance(value, str):
            return str(value).strip() or None
    return None


def _plain(value: str | None) -> str | None:
    """Ozon wraps checkout titles and prices in styled spans."""
    if value is None:
        return None
    return " ".join(_TAG_RE.sub(" ", value).split()) or None


def _link(node: dict[str, Any]) -> str:
    """The link of a node's action, wherever Ozon hung it.

    Rows put their action directly on the node; controls inside a row put it
    under ``common``. Checking only one of the two reads as "no action" and
    makes a control silently do nothing.
    """
    for holder in (node, node.get("common") if isinstance(node.get("common"), dict) else {}):
        action = holder.get("action") if isinstance(holder, dict) else None
        link = action.get("link") if isinstance(action, dict) else None
        if isinstance(link, str) and link:
            return link
    return ""


def parse_payment_options(state: Any) -> list[PaymentOption]:
    """The payment methods Ozon offers, from ``paymentInfoV2.payments``.

    That list is the one the page renders; walking the widget for links instead
    finds only the secondary entries and silently drops Ozon Card, the credit
    card and instalments. Identity differs per method — ``payment_type`` for
    most, ``card_token`` for a saved card, ``part_payment_method`` for
    instalments — so the apply link is the authoritative selector and the type
    is exposed only where it exists. The selected method carries no link, which
    is how Ozon marks it.
    """
    options: list[PaymentOption] = []
    entries = state.get("payments") if isinstance(state, dict) else None
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        link = _link(entry)
        match = _PAYMENT_TYPE_RE.search(link)
        label = _text(entry.get("title"))
        options.append(
            PaymentOption(
                payment_type=int(match.group(1)) if match else None,
                label=label,
                kind=entry.get("automatizationDescription"),
                selected=bool(entry.get("isSelected")),
                apply_link=link or None,
            )
        )
    return options


def _payment_note(state: Any, needle: str) -> str | None:
    """Ozon's own wording for a payment condition, e.g. pay-on-delivery."""
    texts: list[str] = [t for t in find_all(state, "text") if isinstance(t, str)]
    for index, text in enumerate(texts):
        if needle.lower() in text.lower():
            tail = " ".join(texts[index : index + 3])
            return " ".join(tail.split())
    return None


def parse_pay_after_receipt(state: Any) -> PayAfterReceipt:
    """The pay-on-delivery switch: its checkbox state and the link that flips it.

    The link is not a stable toggle — Ozon renames the parameter with the state
    (``post_payment_disabled=0`` while on, ``post_payment_enabled=0`` while off)
    — so it has to be read from the current payload rather than assumed.
    """
    for node in walk(state):
        title = (
            _text((node.get("centerBlock") or {}).get("title")) if isinstance(node.get("centerBlock"), dict) else None
        )
        if not title or "после получения" not in title.lower():
            continue
        left = node.get("leftBlock") if isinstance(node.get("leftBlock"), dict) else {}
        control = left.get("control") if isinstance(left, dict) else None
        status = ((control or {}).get("checkbox") or {}).get("status") if isinstance(control, dict) else None
        texts: list[str] = [t for t in find_all(state, "text") if isinstance(t, str)]
        return PayAfterReceipt(
            available=True,
            enabled=status == "SELECTED",
            label=_plain(title),
            prepayment=next((_plain(t) for t in texts if "предоплата" in t.lower()), None),
            toggle_link=_link(left if isinstance(left, dict) else {}) or None,
        )
    return PayAfterReceipt()


def _point_number(entry: dict[str, Any]) -> str | None:
    """The pickup point's public number; Ozon exposes it as copy-to-clipboard."""
    for node in walk(entry):
        action = node.get("action")
        if isinstance(action, dict) and action.get("id") == "copyText":
            value = (action.get("params") or {}).get("clipboardText")
            if value:
                return str(value)
    return None


def _apply_link(entry: dict[str, Any]) -> str | None:
    for node in walk(entry):
        link = _link(node)
        if "apply_address_split=" in link:
            return link
    return None


def parse_pickup_points(state: Any) -> list[PickupPoint]:
    """Saved addresses from the address-book modal.

    Each entry carries its own apply link; entries without one are points Ozon
    will not ship this cart to, so they are returned as unavailable rather than
    hidden — the caller can explain why.
    """
    points: list[PickupPoint] = []
    for entry in (state.get("addresses") if isinstance(state, dict) else None) or []:
        if not isinstance(entry, dict):
            continue
        texts: list[str] = [t.strip() for t in find_all(entry, "text") if isinstance(t, str) and t.strip()]
        apply_link = _apply_link(entry)
        points.append(
            PickupPoint(
                address_book_id=entry.get("addressBookId"),
                title=_text(entry.get("title")) or (texts[0] if texts else None),
                address=next((t for t in texts[1:] if len(t) > 12 and "хранени" not in t.lower()), None),
                number=_point_number(entry),
                storage=next((t for t in texts if "хранени" in t.lower()), None),
                selected=bool(entry.get("isSelected")),
                available=bool(entry.get("isEnabled")) and apply_link is not None,
                note=next((t for t in texts if "не можем" in t.lower()), None),
            )
        )
    return points


def pickup_apply_link(state: Any, address_book_id: str) -> str | None:
    """The link that switches the order to ``address_book_id``."""
    for entry in (state.get("addresses") if isinstance(state, dict) else None) or []:
        if isinstance(entry, dict) and entry.get("addressBookId") == address_book_id:
            return _apply_link(entry)
    return None


def parse_delivery(state: Any) -> Delivery:
    mode, change_link = None, None
    for node in walk(state):
        link = _link(node)
        if "miniaddressbook" in link:
            change_link = change_link or link
            if node.get("isSelected"):
                mode = _text(node)
    texts: list[str] = [t for t in find_all(state, "text") if isinstance(t, str) and t.strip()]
    # Ozon puts the pickup label, the street address and the storage term in one
    # <br>-separated blob.
    blob = next((t for t in texts if _BR_RE.search(t)), None)
    pieces = [_plain(piece) for piece in _BR_RE.split(blob)] if blob else []
    lines = [piece for piece in pieces if piece]
    label = next((t for t in texts if t.strip().startswith("Пункт")), None)
    street = next((line for line in lines if "хранени" not in line.lower()), None)
    return Delivery(
        mode=mode or next((t for t in texts if t.strip() in {"Самовывоз", "Курьером"}), None),
        address=", ".join(filter(None, (label, street))) or None,
        storage=next((line for line in lines if "хранени" in line.lower()), None),
        recipient=next((t for t in texts if _RECIPIENT_RE.match(t.strip())), None),
        change_link=change_link,
    )


def parse_deliveries(data: dict[str, Any]) -> list[Delivery]:
    """One entry per destination widget, each tagged with the shipments it covers."""
    deliveries: list[Delivery] = []
    for state in widgets_all(data, "rfbsAddressInfo"):
        delivery = parse_delivery(state)
        keys: list[str] = []
        for node in walk(state):
            for key in _SPLIT_KEY_RE.findall(_link(node)):
                if key not in keys:
                    keys.append(key)
        delivery.split_keys = keys
        deliveries.append(delivery)
    return deliveries


def parse_parts(data: dict[str, Any]) -> list[DeliveryPart]:
    """Per-shipment dates. They sit in one of several rfbsSplit instances, so
    scan them all rather than trusting widget order.
    """
    parts: list[DeliveryPart] = []
    texts: list[str] = []
    for state in widgets_all(data, "rfbsSplit"):
        texts += [t.strip() for t in find_all(state, "text") if isinstance(t, str) and t.strip()]
    for index, text in enumerate(texts):
        if not _DELIVERY_RE.search(text):
            continue
        details = next((t for t in texts[index + 1 : index + 4] if "товар" in t), None)
        parts.append(DeliveryPart(title=_plain(text), details=_plain(details)))
    return parts


def parse_points(state: Any) -> list[PointsOption]:
    options: list[PointsOption] = []
    tabs = state.get("tabs") if isinstance(state, dict) else None
    entries = tabs.get("tabs") if isinstance(tabs, dict) else None
    selected_index = tabs.get("selectedTabIndex") if isinstance(tabs, dict) else None
    for index, tab in enumerate(entries or []):
        if not isinstance(tab, dict):
            continue
        label = _text(tab.get("title")) or _text(tab)
        common = tab.get("common") if isinstance(tab.get("common"), dict) else {}
        link = _link(common)
        # The amount is in the link when Ozon offers one ("points_applied=100.00")
        # and only in the label otherwise ("Списать 100"); the two patterns
        # capture differently, so they are read apart rather than together.
        from_link = _POINTS_RE.search(link)
        from_label = _DIGITS_RE.search(label or "") if label else None
        amount = float(from_link.group(1)) if from_link else (float(from_label.group(0)) if from_label else None)
        options.append(
            PointsOption(
                label=label,
                amount=int(amount) if amount is not None else None,
                selected=index == selected_index,
                apply_link=link or None,
            )
        )
    return options


def parse_totals(state: Any) -> Totals:
    summary = state.get("summary") if isinstance(state, dict) else None
    summary = summary if isinstance(summary, dict) else {}
    rows: list[TotalRow] = []
    for row in summary.get("prices") or []:
        if not isinstance(row, dict):
            continue
        left, right = row.get("left") or {}, row.get("right") or {}
        title = _plain(_text(left.get("title")) or _text(left))
        value = _plain(_text(right.get("price")) or _text(right))
        if title or value:
            rows.append(TotalRow(title=title, value=value))
    footer_raw = summary.get("footer")
    footer: dict[str, Any] = footer_raw if isinstance(footer_raw, dict) else {}
    note = None
    order_total = None
    for row in summary.get("footerPrices") or []:
        if not isinstance(row, dict):
            continue
        left, right = row.get("left") or {}, row.get("right") or {}
        title = _text(left.get("title"))
        price = _plain(_text(right.get("price")))
        note = " ".join(filter(None, (title, _text(left.get("subtitle")), price)))
        # Ozon labels the whole-order figure separately from today's charge.
        if title and "всего заказа" in title.lower():
            order_total = price
    today = _plain(_text(footer.get("price")))
    return Totals(
        rows=rows,
        total=today,
        # With nothing deferred the two coincide, and Ozon prints only one.
        order_total=order_total or today,
        note=note or None,
    )


def parse_checkout(data: dict[str, Any]) -> Checkout:
    """Build the checkout state; ``available`` is False when Ozon shows no order."""
    payment = widget(data, "paymentInfoV2")
    total = widget(data, "total")
    if payment is None and total is None:
        return Checkout(available=False, reason="checkout page did not load (empty cart or auth required)")
    payment_options = parse_payment_options(payment)
    deliveries = parse_deliveries(data)
    totals = parse_totals(total)
    # The page still renders its shell when nothing in the cart is ticked. Saying
    # "available" then would hand the caller an empty order; name the fix instead.
    if not payment_options and not deliveries and not totals.total:
        return Checkout(
            available=False,
            reason="no cart items are selected for this order — tick them in the cart first",
        )
    create_action = next(
        (_link(node) for node in walk(total or {}) if "createOrder" in _link(node)),
        None,
    )
    return Checkout(
        available=True,
        payment_options=payment_options,
        pay_after_receipt=parse_pay_after_receipt(payment),
        installment=_payment_note(payment, "Рассрочка"),
        deliveries=deliveries,
        parts=parse_parts(data),
        points=parse_points(widget(data, "premiumPointsToggle")),
        totals=totals,
        place_order_action=create_action,
    )
