"""Placing an order is gated twice and confirmed against what Ozon charges.

On a pay-on-delivery order today's charge is 0 ₽, so accepting only that figure
had the caller confirm "0 ₽" for an order of several thousand.
"""

from __future__ import annotations

import pytest

from ozon_mcp.errors import OrdersDisabledError, TotalMismatchError
from ozon_mcp.services import checkout
from support import FakeSession, page

TOTAL = {
    "summary": {
        "footer": {"price": "0 ₽ сегодня"},
        "prices": [{"left": {"title": "Товары (1)"}, "right": {"price": "777 ₽"}}],
    },
    "totalPrice": 777,
}
PAYMENT = {"payments": [{"title": {"text": "Ozon Карта"}, "automatizationDescription": "OzonCard", "isSelected": True}]}
CHECKOUT_PAGE = page(total=TOTAL, paymentInfoV2=PAYMENT)
# Placing enters checkout first, which reads the cart to know that something is
# ticked at all — see test_checkout_is_entered_before_it_is_read.
CART_PAGE = page(
    cartSplit={
        "cartItems": [
            {
                "product": {"id": "3077454533", "titleColumn": {"text": "Товар"}, "priceColumn": {"price": "777 ₽"}},
                "controls": {"quantity": {"current": 1, "maximum": 5}},
                "checkbox": {"isChecked": True},
            }
        ]
    }
)
PAGES = {"/cart": CART_PAGE, "/gocheckout": CHECKOUT_PAGE}


def test_without_the_orders_gate_nothing_is_sent(session: FakeSession) -> None:
    session.pages = dict(PAGES)
    with pytest.raises(OrdersDisabledError) as raised:
        checkout.place_order("777 ₽")
    assert "operator's setting" in str(raised.value)
    assert session.performed == []


def test_the_order_total_is_accepted(session: FakeSession, writes_on: None) -> None:
    session.pages = dict(PAGES)
    session.actions = {"createOrderV2": {"data": {"createOrderResponse": {"link": "?orderNumber=44563249-0900"}}}}
    placed = checkout.place_order("777 ₽")
    assert placed.order_number == "44563249-0900"
    assert placed.order_total == "777 ₽"


def test_todays_charge_is_accepted_too(session: FakeSession, writes_on: None) -> None:
    session.pages = dict(PAGES)
    session.actions = {"createOrderV2": {"data": {"createOrderResponse": {"link": "?orderNumber=44563249-0901"}}}}
    assert checkout.place_order("0 ₽ сегодня").order_number == "44563249-0901"


def test_a_stale_total_is_refused_and_nothing_is_ordered(session: FakeSession, writes_on: None) -> None:
    session.pages = dict(PAGES)
    with pytest.raises(TotalMismatchError) as raised:
        checkout.place_order("999 ₽")
    assert "777 ₽" in str(raised.value)
    assert "Nothing was ordered" in str(raised.value)
    assert session.performed == []
