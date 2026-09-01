"""Reading the checkout has to enter it first.

Ozon's checkout is a snapshot of the cart's ticks taken on entry, and only an
entry replaces it: after unticking an item the cart said one item and 649 ₽ while
the checkout still said two and 768 ₽ — in the site's own browser too. A read
that skipped the entry therefore described, and would have placed, an order the
caller had not composed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from ozon_mcp.errors import TotalMismatchError
from ozon_mcp.services import checkout
from support import page

if TYPE_CHECKING:
    from support import FakeSession

TOTAL = {
    "summary": {
        "footer": {"price": "649 ₽"},
        "prices": [{"left": {"title": "Товары (1)"}, "right": {"price": "649 ₽"}}],
    },
    "totalPrice": 649,
}
PAYMENT = {"payments": [{"title": {"text": "Ozon Карта"}, "automatizationDescription": "OzonCard", "isSelected": True}]}
CHECKOUT_PAGE = page(total=TOTAL, paymentInfoV2=PAYMENT)


def _cart(*, checked: bool) -> dict[str, Any]:
    return page(
        cartSplit={
            "cartItems": [
                {
                    "product": {
                        "id": "2859492815",
                        "titleColumn": {"text": "Салфетки"},
                        "priceColumn": {"price": "649 ₽"},
                    },
                    "controls": {"quantity": {"current": 1, "maximum": 5}},
                    "checkbox": {"isChecked": checked},
                }
            ]
        }
    )


def _entries(session: FakeSession) -> list[str]:
    return [url for url in session.fetched if url.startswith("/gocheckout?activeTab=")]


def test_a_read_enters_checkout_first(session: FakeSession) -> None:
    session.pages = {"/cart": _cart(checked=True), "/gocheckout": CHECKOUT_PAGE}
    assert checkout.get_checkout().totals.order_total == "649 ₽"
    entries = _entries(session)
    assert len(entries) == 1
    # The parameters are the ones the cart's own button carries; session_uid is
    # fresh each time, which is what makes it an entry rather than a re-read.
    assert "session_uid=" in entries[0]
    assert "totalCurrency=RUB" in entries[0]


def test_placing_an_order_enters_checkout_too(session: FakeSession, writes_on: None) -> None:
    session.pages = {"/cart": _cart(checked=True), "/gocheckout": CHECKOUT_PAGE}
    session.actions = {"createOrderV2": {"data": {"createOrderResponse": {"link": "?orderNumber=44563249-0902"}}}}
    assert checkout.place_order("649 ₽").order_number == "44563249-0902"
    assert _entries(session), "an order was placed against a snapshot nobody refreshed"


def test_an_empty_selection_is_refused_without_entering(session: FakeSession) -> None:
    session.pages = {"/cart": _cart(checked=False), "/gocheckout": CHECKOUT_PAGE}
    answer = checkout.get_checkout()
    assert answer.available is False
    assert "selected" in (answer.reason or "")
    assert _entries(session) == []


def test_a_total_from_a_stale_snapshot_is_still_refused(session: FakeSession, writes_on: None) -> None:
    """The confirmation stays the last line of defence, entry or not."""
    session.pages = {"/cart": _cart(checked=True), "/gocheckout": CHECKOUT_PAGE}
    with pytest.raises(TotalMismatchError):
        checkout.place_order("768 ₽")
    assert session.performed == []
