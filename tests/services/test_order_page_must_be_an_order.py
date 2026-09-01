"""Ozon answers an unknown order number with a valid page that has no order.

Paying one then reported "nothing left to pay" — indistinguishable from an order
that was already settled.
"""

from __future__ import annotations

from ozon_mcp.services.orders import _order_exists


def test_a_real_order_page_is_recognised() -> None:
    page = {"widgetStates": {"shipmentWidget-1": '{"items": []}'}}
    assert _order_exists(page) is True


def test_a_page_without_an_order_is_not_one() -> None:
    assert _order_exists({"widgetStates": {"skuGrid-1": '{"products": []}'}}) is False
    assert _order_exists({}) is False
