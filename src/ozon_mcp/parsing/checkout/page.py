"""Assembling the checkout from its parts.

The money is stated in words here, where both halves of it are in hand: what is
charged today and what the order costs.
"""

from typing import Any

from ozon_mcp.models.checkout import Checkout
from ozon_mcp.parsing.checkout.atoms import action_link
from ozon_mcp.parsing.checkout.delivery import parse_deliveries, parse_shipments
from ozon_mcp.parsing.checkout.money import parse_points, parse_totals
from ozon_mcp.parsing.checkout.payment import (
    INSTALMENT_KIND,
    parse_pay_after_receipt,
    parse_payment_options,
    payment_note,
    postpay_texts,
    state_postpay,
)
from ozon_mcp.parsing.common import walk, widget


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
    state_postpay(pay_after_receipt, totals)
    # The page still renders its shell when nothing in the cart is ticked. Saying
    # "available" then would hand the caller an empty order; name the fix instead.
    if not payment_options and not deliveries and not totals.total:
        return Checkout(
            available=False,
            reason="no cart items are selected for this order — tick them in the cart first",
        )
    create_action = next(
        (action_link(node) for node in walk(total or {}) if "createOrder" in action_link(node)),
        None,
    )
    return Checkout(
        available=True,
        payment_options=payment_options,
        pay_after_receipt=pay_after_receipt,
        installment=payment_note(payment, INSTALMENT_KIND),
        deliveries=deliveries,
        shipments=parse_shipments(data),
        points=parse_points(widget(data, "premiumPointsToggle")),
        totals=totals,
        place_order_action=create_action,
    )
