"""What list_orders hands out has to be accepted by the tools it feeds."""

from __future__ import annotations

import base64

import pytest

from ozon_mcp.errors import OzonError, WritesDisabledError
from ozon_mcp.services import orders
from ozon_mcp.utils.serde import dumps
from support import FakeSession, page

LINK = (
    "v2/cacheOrderProducts?data=" + base64.urlsafe_b64encode(dumps({"postings": ["44563249-0877-1"]}).encode()).decode()
)


def test_paying_an_order_that_does_not_exist_says_so(session: FakeSession, writes_on: None) -> None:
    # Ozon serves an unknown number a valid page with no order on it.
    session.pages = {"/my/orderdetails": page(skuGrid={"products": []})}
    with pytest.raises(OzonError) as raised:
        orders.pay_order("00000000-0000")
    assert "no order 00000000-0000" in str(raised.value)


def test_a_detail_link_is_accepted_where_a_number_is(session: FakeSession, writes_on: None) -> None:
    session.pages = {"/my/orderdetails": page(shipmentWidget={"items": []})}
    asked = orders.pay_order(LINK)
    # The link resolved to the order behind it, and a settled order reports
    # that there is nothing left rather than raising.
    assert asked.order_number == "44563249-0877"
    assert "nothing left to pay" in (asked.detail or "")
    assert any("order=44563249-0877" in path for path in session.fetched)


def test_cancelling_without_the_gate_is_refused_first(session: FakeSession) -> None:
    with pytest.raises(WritesDisabledError):
        orders.cancel_order(LINK)
    assert session.performed == []


def test_a_comment_is_required_by_the_catch_all_reason(session: FakeSession, writes_on: None) -> None:
    with pytest.raises(OzonError) as raised:
        orders.cancel_order("44563249-0877", reason_id="508")
    assert "comment" in str(raised.value).lower()
