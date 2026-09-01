"""How the order is paid: methods, the pay-on-delivery switch, the prepayment.

The switch is the delicate part. Ozon offers the same control for a whole order
and for part of one, and the two charge different money, so which case it is
comes from the labels the layout declares rather than from the rendered words.
"""

import re
from typing import Any, Final

from ozon_mcp.models.checkout import PayAfterReceipt, PaymentOption, ShipmentItem, Totals
from ozon_mcp.models.enums import PostPaymentScope
from ozon_mcp.parsing.checkout.atoms import action_link, plain, text
from ozon_mcp.parsing.checkout.delivery import detail_items
from ozon_mcp.parsing.common import PRICE_RE, find_all, layout_widgets, walk, widgets_all
from ozon_mcp.utils.money import format_money, to_kopecks
from ozon_mcp.utils.serde import loads

_PAYMENT_TYPE_RE: Final = re.compile(r"payment_type=(\d+)")


INSTALMENT_KIND: Final = "OzonCredit"


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
        link = action_link(entry)
        match = _PAYMENT_TYPE_RE.search(link)
        label = text(entry.get("title"))
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


def payment_note(state: Any, kind: str) -> str | None:
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
        parts = [plain(text(entry.get("title"))), plain(text(promote))]
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


def _scope(label: str | None, texts: dict[str, str]) -> PostPaymentScope:
    """Whether the offered pay-on-delivery covers the whole order or part of it."""
    rendered = (label or "").strip().casefold()
    if not rendered:
        return PostPaymentScope.NONE
    if rendered == (texts.get("mixedPrepayCheckboxText") or "").strip().casefold():
        return PostPaymentScope.PARTIAL
    if rendered == (texts.get("fullPostPayCheckboxText") or "").strip().casefold():
        return PostPaymentScope.FULL
    # Unrecognised wording: the prepayment line is the other signal Ozon gives.
    return PostPaymentScope.PARTIAL if "часть" in rendered else PostPaymentScope.FULL


def parse_pay_after_receipt(state: Any, texts: dict[str, str] | None = None) -> PayAfterReceipt:
    """The pay-on-delivery switch: its state, its reach, and the link that flips it.

    The link is not a stable toggle — Ozon renames the parameter with the state
    (``post_payment_disabled=0`` while on, ``post_payment_enabled=0`` while off)
    — so it has to be read from the current payload rather than assumed.
    """
    texts = texts or {}
    for node in walk(state):
        title = (
            text((node.get("centerBlock") or {}).get("title")) if isinstance(node.get("centerBlock"), dict) else None
        )
        if not title or "после получения" not in title.lower():
            continue
        left = node.get("leftBlock") if isinstance(node.get("leftBlock"), dict) else {}
        control = left.get("control") if isinstance(left, dict) else None
        status = ((control or {}).get("checkbox") or {}).get("status") if isinstance(control, dict) else None
        rendered = [t for t in find_all(state, "text") if isinstance(t, str)]
        prepayment = next((plain(t) for t in rendered if "предоплата" in t.lower()), None)
        found = PRICE_RE.search(prepayment or "")
        return PayAfterReceipt(
            available=True,
            enabled=status == "SELECTED",
            scope=_scope(plain(title), texts),
            label=plain(title),
            prepayment=prepayment,
            prepayment_amount=found.group(0) if found else None,
            toggle_link=action_link(left if isinstance(left, dict) else {}) or None,
        )
    return PayAfterReceipt()


def prepayment_link(state: Any) -> str | None:
    """The link behind the «Есть предоплата N ₽» row of the payment block.

    That row is a control, not a caption: it opens Ozon's own breakdown of which
    items are charged now and which on receipt. The action hangs on the row's
    chevron rather than on the row, so the whole row is searched — the link is
    what matters, not which atom Ozon chose to attach it to.
    """
    for node in walk(state):
        center = node.get("centerBlock")
        title = text((center or {}).get("title")) if isinstance(center, dict) else None
        if not title or "предоплата" not in title.lower():
            continue
        for inner in walk(node):
            link = action_link(inner)
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
        (text(state.get("title")) or "", detail_items(state)) for state in widgets_all(data, "splitDetailWebV2")
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


def state_postpay(switch: PayAfterReceipt, totals: Totals) -> None:
    """Spell out what the switch means in money, in one sentence.

    Ozon renders the deferred half nowhere: it prints today's charge and the
    order total and leaves the difference to the reader. A caller that quotes
    only what it was given therefore states the wrong number, so the split is
    computed here rather than left to each consumer.
    """
    if not switch.available:
        switch.note = "Ozon does not offer pay-on-delivery for this order"
        return
    part = (
        "only part of this order can be paid on delivery"
        if switch.scope is PostPaymentScope.PARTIAL
        else "the whole order"
    )
    if not switch.enabled:
        # Ozon prints the prepayment line only while the switch is on: with it
        # off nothing is deferred, so today's charge is the whole order.
        switch.note = f"{part}; the switch is off, so all {totals.order_total} is charged now"
        return
    if switch.scope is not PostPaymentScope.PARTIAL:
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
