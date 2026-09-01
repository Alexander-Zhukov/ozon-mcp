"""Reading the checkout page.

Split by what it is about — payment, delivery, money — because the page is, and
one module holding all of it hid the seams. ``parse_checkout`` is the assembly:
it reads each part and states the money in words once, where both halves of it
are in hand.
"""

from ozon_mcp.parsing.checkout.atoms import action_link, plain, text
from ozon_mcp.parsing.checkout.delivery import (
    detail_items,
    parse_deliveries,
    parse_delivery,
    parse_pickup_points,
    parse_shipment_items,
    parse_shipments,
    pickup_apply_link,
    shipment_detail_link,
    shipment_total,
)
from ozon_mcp.parsing.checkout.money import parse_points, parse_totals
from ozon_mcp.parsing.checkout.page import parse_checkout
from ozon_mcp.parsing.checkout.payment import (
    parse_pay_after_receipt,
    parse_payment_options,
    parse_prepayment_split,
    payment_note,
    postpay_texts,
    prepayment_link,
    state_postpay,
)

__all__ = [
    "action_link",
    "detail_items",
    "parse_checkout",
    "parse_deliveries",
    "parse_delivery",
    "parse_pay_after_receipt",
    "parse_payment_options",
    "parse_pickup_points",
    "parse_points",
    "parse_prepayment_split",
    "parse_shipment_items",
    "parse_shipments",
    "parse_totals",
    "payment_note",
    "pickup_apply_link",
    "plain",
    "postpay_texts",
    "prepayment_link",
    "shipment_detail_link",
    "shipment_total",
    "state_postpay",
    "text",
]
