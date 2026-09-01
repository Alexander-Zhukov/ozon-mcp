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
    PayAfterReceipt,
    PaymentOption,
    PickupPoint,
    PointsOption,
    Shipment,
    ShipmentItem,
    TotalRow,
    Totals,
)
from ozon_mcp.parsing.common import PRICE_RE, find_all, layout_widgets, walk, widget, widgets_all
from ozon_mcp.utils.money import KOPECKS, format_money, to_kopecks
from ozon_mcp.utils.serde import dumps, loads

_PAYMENT_TYPE_RE = re.compile(r"payment_type=(\d+)")
_POINTS_RE = re.compile(r"points_applied=([\d.]+)")
_DIGITS_RE = re.compile(r"\d+")
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_RECIPIENT_ACTION = "editAddressAndRecipient"
# The destination cell is the one drawn with a location pin; the recipient cell
# looks the same but carries a profile icon.
_ADDRESS_ICON = "ic_m_location_pin_filled"
_ADDRESS_BOOK = "miniaddressbook"
# How Ozon names instalments among the payment methods it declares.
_INSTALMENT_KIND = "OzonCredit"
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


def _payment_note(state: Any, kind: str) -> str | None:
    """Ozon's own wording for one payment method, e.g. the instalment offer.

    Anchored on the method's declared kind (``automatizationDescription``)
    rather than on a word in the page text: the old read took the matching text
    plus the next two, whatever those happened to be, so a layout change moved
    the answer without breaking anything visibly.
    """
    entries = state.get("payments") if isinstance(state, dict) else None
    for entry in entries or []:
        if not isinstance(entry, dict) or entry.get("automatizationDescription") != kind:
            continue
        promote = entry.get("promoteLabel") if isinstance(entry.get("promoteLabel"), dict) else {}
        parts = [_plain(_text(entry.get("title"))), _plain(_text(promote))]
        return " ".join(part for part in parts if part) or None
    return None


def postpay_texts(data: dict[str, Any]) -> dict[str, str]:
    """The wording Ozon itself declares for the pay-on-delivery checkbox.

    The layout declares one label for a fully deferred order
    (``fullPostPayCheckboxText``) and another for one where only part of it can
    wait (``mixedPrepayCheckboxText``), plus the prefix of the prepayment line.
    Comparing the rendered label against these is what tells the two apart —
    guessing at a substring of a marketing string would break the day Ozon
    rewords it, and the two cases charge different money.
    """
    for entry in layout_widgets(data):
        if entry.get("component") != "paymentInfoV2":
            continue
        try:
            params = loads(entry.get("params") or "{}")
        except (ValueError, TypeError):
            continue
        if not isinstance(params, dict):
            continue
        return {key: value for key, value in params.items() if isinstance(value, str)}
    return {}


def _scope(label: str | None, texts: dict[str, str]) -> str:
    """Whether the offered pay-on-delivery covers the whole order or part of it."""
    rendered = (label or "").strip().casefold()
    if not rendered:
        return "none"
    if rendered == (texts.get("mixedPrepayCheckboxText") or "").strip().casefold():
        return "partial"
    if rendered == (texts.get("fullPostPayCheckboxText") or "").strip().casefold():
        return "full"
    # Unrecognised wording: the prepayment line is the other signal Ozon gives.
    return "partial" if "часть" in rendered else "full"


def parse_pay_after_receipt(state: Any, texts: dict[str, str] | None = None) -> PayAfterReceipt:
    """The pay-on-delivery switch: its state, its reach, and the link that flips it.

    The link is not a stable toggle — Ozon renames the parameter with the state
    (``post_payment_disabled=0`` while on, ``post_payment_enabled=0`` while off)
    — so it has to be read from the current payload rather than assumed.
    """
    texts = texts or {}
    for node in walk(state):
        title = (
            _text((node.get("centerBlock") or {}).get("title")) if isinstance(node.get("centerBlock"), dict) else None
        )
        if not title or "после получения" not in title.lower():
            continue
        left = node.get("leftBlock") if isinstance(node.get("leftBlock"), dict) else {}
        control = left.get("control") if isinstance(left, dict) else None
        status = ((control or {}).get("checkbox") or {}).get("status") if isinstance(control, dict) else None
        rendered = [t for t in find_all(state, "text") if isinstance(t, str)]
        prepayment = next((_plain(t) for t in rendered if "предоплата" in t.lower()), None)
        found = PRICE_RE.search(prepayment or "")
        return PayAfterReceipt(
            available=True,
            enabled=status == "SELECTED",
            scope=_scope(_plain(title), texts),
            label=_plain(title),
            prepayment=prepayment,
            prepayment_amount=found.group(0) if found else None,
            toggle_link=_link(left if isinstance(left, dict) else {}) or None,
        )
    return PayAfterReceipt()


def _point_number(entry: dict[str, Any]) -> str | None:
    """The pickup point's public number.

    ``numberPVZ`` holds it twice: rendered as «№ 144-94-60» and plain in the
    copy-to-clipboard action. The plain one is what a person types back, so it
    is preferred; only a pickup point has this block at all, which is what tells
    a point apart from a courier address.
    """
    block = entry.get("numberPVZ") if isinstance(entry.get("numberPVZ"), dict) else None
    if block is None:
        return None
    for node in walk(block):
        action = node.get("action")
        if isinstance(action, dict) and action.get("id") == "copyText":
            value = (action.get("params") or {}).get("clipboardText")
            if value:
                return str(value)
    return _plain(_text(block.get("number")))


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
        # Every entry states its own lines in order: the address first, then
        # either the storage term (a pickup point) or the flat/floor detail and
        # the recipient (a courier address). Reading them positionally is what
        # avoids guessing an address by "the first text longer than 12 chars".
        lines = [line for line in (_plain(_text(element)) for element in entry.get("elements") or []) if line]
        number = _point_number(entry)
        apply_link = _apply_link(entry)
        rest = lines[1:]
        notes = [note for note in (_plain(_text(element)) for element in entry.get("bottomElements") or []) if note]
        points.append(
            PickupPoint(
                address_book_id=entry.get("addressBookId"),
                title=_plain(_text(entry.get("title"))),
                # A courier address spreads over its lines; a point is one line
                # plus how long it keeps the parcel.
                address=", ".join(lines if number is None else lines[:1]) or None,
                number=number,
                storage=rest[0] if number is not None and rest else None,
                selected=bool(entry.get("isSelected")),
                available=bool(entry.get("isEnabled")) and apply_link is not None,
                note=" ".join(notes) or None,
            )
        )
    return points


def pickup_apply_link(state: Any, address_book_id: str) -> str | None:
    """The link that switches the order to ``address_book_id``."""
    for entry in (state.get("addresses") if isinstance(state, dict) else None) or []:
        if isinstance(entry, dict) and entry.get("addressBookId") == address_book_id:
            return _apply_link(entry)
    return None


def _address_cell(state: Any) -> dict[str, Any]:
    """The cell showing where the order goes, found by the pin it is drawn with.

    The recipient sits in a cell of the same shape right below it, so the two
    are told apart by their icons rather than by what their text looks like.
    """
    for node in walk(state):
        icon = dumps(node.get("leftBlock") or {})
        if _ADDRESS_ICON in icon and isinstance(node.get("centerBlock"), dict):
            return node
    return {}


def parse_delivery(state: Any) -> Delivery:
    """Where this part of the order goes, and how.

    The mode is a tag list, and the selected tag is the mode — no guessing from
    the wording. The address cell states the point and, after a ``<br>``, how
    long it keeps a parcel: Ozon writes them in that order, so they are taken by
    position. Deciding which half was which by looking for "хранение" broke on
    a courier address, which has no storage term but does have a flat and a
    floor.
    """
    mode, change_link = None, None
    for node in walk(state):
        link = _link(node)
        if _ADDRESS_BOOK in link:
            change_link = change_link or link
            if node.get("isSelected"):
                mode = _text(node)
    center: dict[str, Any] = _address_cell(state).get("centerBlock") or {}
    label = _plain(_text(center.get("title")))
    pieces = [_plain(piece) for piece in _BR_RE.split(_text(center.get("subtitle")) or "")]
    lines = [piece for piece in pieces if piece]
    return Delivery(
        mode=mode,
        address=", ".join(filter(None, (label, lines[0] if lines else None))) or None,
        storage=" ".join(lines[1:]) or None,
        recipient=_recipient(state),
        change_link=change_link,
    )


def _recipient(state: Any) -> str | None:
    """Who the order is addressed to, from the row that edits exactly that.

    Ozon gives the row its own action (``/modal/editAddressAndRecipient``), so
    the name is read from there instead of being recognised by shape — the old
    "two capitalised words then digits" pattern missed a single-word name, a
    double-barrelled surname and anything not in Cyrillic.
    """
    for node in walk(state):
        if _RECIPIENT_ACTION not in _link(node):
            continue
        for inner in walk(node):
            center = inner.get("centerBlock")
            title = _text((center or {}).get("title")) if isinstance(center, dict) else None
            if title:
                return _plain(title)
    return None


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


def parse_shipments(data: dict[str, Any]) -> list[Shipment]:
    """The order's shipments, each with the id Ozon addresses it by.

    Read from each ``rfbsSplit`` widget's own fields rather than by scanning the
    page's text: the id is what every per-shipment call needs, and text order is
    not a reliable way to pair a date with a shipment.
    """
    shipments: list[Shipment] = []
    for state in widgets_all(data, "rfbsSplit"):
        if not isinstance(state, dict) or not state.get("id"):
            continue
        header = state.get("header") if isinstance(state.get("header"), dict) else {}
        shipments.append(
            Shipment(
                split_key=str(state["id"]),
                delivery=_plain(_text(header.get("text"))),
                summary=_plain(_text(state.get("subHeader"))),
            )
        )
    return sorted(shipments, key=lambda shipment: shipment.split_key or "")


def shipment_detail_link(data: dict[str, Any], split_key: str) -> str | None:
    """The link to a shipment's contents, as that shipment declares it.

    It carries the currently chosen address, so it is taken from the payload
    instead of being assembled from the split key alone.
    """
    for state in widgets_all(data, "rfbsSplit"):
        if isinstance(state, dict) and str(state.get("id")) == split_key:
            action = state.get("action") if isinstance(state.get("action"), dict) else {}
            link = action.get("link")
            return str(link) if link else None
    return None


def _detail_items(state: Any) -> list[ShipmentItem]:
    """Lines of one ``splitDetailWebV2`` widget.

    ``vertical.splits`` groups the lines by seller; each line states its title
    and variant as two text atoms of ``mainColumn``, its price separately, and
    its quantity in ``sideColumn``.
    """
    items: list[ShipmentItem] = []
    vertical = state.get("vertical") if isinstance(state, dict) else None
    for group in (vertical or {}).get("splits") or []:
        if not isinstance(group, dict):
            continue
        seller = _plain(_text(group.get("title")))
        for entry in group.get("items") or []:
            if not isinstance(entry, dict):
                continue
            labels = [_plain(_text(atom.get("textAtom"))) for atom in entry.get("mainColumn") or []]
            labels = [label for label in labels if label]
            price = entry.get("price") if isinstance(entry.get("price"), dict) else {}
            quantity = next((_plain(_text(cell)) for cell in entry.get("sideColumn") or []), None)
            items.append(
                ShipmentItem(
                    title=labels[0] if labels else None,
                    variant=labels[1] if len(labels) > 1 else None,
                    price=_plain(_text(price.get("price")) or price.get("price")),
                    quantity=quantity,
                    seller=seller,
                )
            )
    return items


def parse_shipment_items(data: dict[str, Any]) -> list[ShipmentItem]:
    """Contents of one shipment, from its detail modal."""
    items: list[ShipmentItem] = []
    for state in widgets_all(data, "splitDetailWebV2"):
        items += _detail_items(state)
    return items


def prepayment_link(state: Any) -> str | None:
    """The link behind the «Есть предоплата N ₽» row of the payment block.

    That row is a control, not a caption: it opens Ozon's own breakdown of which
    items are charged now and which on receipt. The action hangs on the row's
    chevron rather than on the row, so the whole row is searched — the link is
    what matters, not which atom Ozon chose to attach it to.
    """
    for node in walk(state):
        center = node.get("centerBlock")
        title = _text((center or {}).get("title")) if isinstance(center, dict) else None
        if not title or "предоплата" not in title.lower():
            continue
        for inner in walk(node):
            link = _link(inner)
            if link:
                return link
    return None


def parse_prepayment_split(data: dict[str, Any]) -> tuple[list[ShipmentItem], list[ShipmentItem]]:
    """Ozon's own answer to which items are prepaid, as (charged now, on receipt).

    The modal renders the two groups as two ``splitDetailWebV2`` widgets titled
    «К оплате сейчас» and «К оплате после получения». Their order is not
    guaranteed, so they are told apart by title; with exactly two sections and
    only one of them recognised, the other is the remaining group by elimination.
    """
    sections = [
        (_text(state.get("title")) or "", _detail_items(state)) for state in widgets_all(data, "splitDetailWebV2")
    ]
    now = [items for title, items in sections if "сейчас" in title.lower()]
    later = [items for title, items in sections if "после получения" in title.lower()]
    if len(sections) == 2 and len(now) + len(later) == 1:
        unmatched = [
            items
            for title, items in sections
            if "сейчас" not in title.lower() and "после получения" not in title.lower()
        ]
        (later if now else now).extend(unmatched)
    return [item for group in now for item in group], [item for group in later for item in group]


def shipment_total(items: list[ShipmentItem]) -> str | None:
    """What a shipment costs, summed from its lines."""
    amounts = [to_kopecks(item.price) for item in items]
    known = [amount for amount in amounts if amount is not None]
    return format_money(sum(known)) if known and len(known) == len(amounts) else None


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
    # The same figure is stated as a number beside the rendered rows; preferring
    # it keeps the order total out of a caption Ozon is free to reword.
    declared = state.get("totalPrice") if isinstance(state, dict) else None
    if isinstance(declared, (int, float)) and not isinstance(declared, bool):
        order_total = format_money(round(declared * KOPECKS))
    return Totals(
        rows=rows,
        total=today,
        # With nothing deferred the two coincide, and Ozon prints only one.
        order_total=order_total or today,
        note=note or None,
    )


def _state_postpay(switch: PayAfterReceipt, totals: Totals) -> None:
    """Spell out what the switch means in money, in one sentence.

    Ozon renders the deferred half nowhere: it prints today's charge and the
    order total and leaves the difference to the reader. A caller that quotes
    only what it was given therefore states the wrong number, so the split is
    computed here rather than left to each consumer.
    """
    if not switch.available:
        switch.note = "Ozon does not offer pay-on-delivery for this order"
        return
    part = "only part of this order can be paid on delivery" if switch.scope == "partial" else "the whole order"
    if not switch.enabled:
        # Ozon prints the prepayment line only while the switch is on: with it
        # off nothing is deferred, so today's charge is the whole order.
        switch.note = f"{part}; the switch is off, so all {totals.order_total} is charged now"
        return
    if switch.scope != "partial":
        switch.post_payment_amount = totals.order_total
        switch.note = f"the whole order ({totals.order_total}) is paid on receipt, nothing is charged now"
        return
    order_total = to_kopecks(totals.order_total)
    prepayment = to_kopecks(switch.prepayment_amount)
    if order_total is None or prepayment is None:
        switch.note = "only part of this order can be paid on delivery; Ozon did not state the prepayment"
        return
    deferred = format_money(order_total - prepayment)
    switch.post_payment_amount = deferred
    switch.note = (
        f"only part of this order can be paid on delivery: {switch.prepayment_amount} is charged now, "
        f"{deferred} on receipt"
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
    pay_after_receipt = parse_pay_after_receipt(payment, postpay_texts(data))
    _state_postpay(pay_after_receipt, totals)
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
        pay_after_receipt=pay_after_receipt,
        installment=_payment_note(payment, _INSTALMENT_KIND),
        deliveries=deliveries,
        shipments=parse_shipments(data),
        points=parse_points(widget(data, "premiumPointsToggle")),
        totals=totals,
        place_order_action=create_action,
    )
