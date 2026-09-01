"""«Текущие заказы» is not a list of current orders.

Ozon keeps the recently received and cancelled orders on that page, in the same
shape, so passing it through as "active" reported finished orders as current.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ozon_mcp.models.enums import OrderState
from ozon_mcp.parsing.orders import parse_orders
from ozon_mcp.services import orders as service

if TYPE_CHECKING:
    from support import FakeSession


def _row(status: str) -> dict[str, Any]:
    return {
        "common": {"action": {"link": f"v2/cacheOrderProducts?data={status}"}},
        "leftBlock": {"textIcon": {"text": {"text": status, "testInfo": {"automatizationId": "tileStatus"}}}},
        "rightBlock": {"products": {"products": []}},
    }


def _orderlist(*statuses: str) -> dict[str, Any]:
    rows = [_row(status) for status in statuses]
    return {"widgetStates": {"orderList-1": json.dumps({"ordersV2": rows}, ensure_ascii=False)}}


CURRENT_PAGE = _orderlist("Можно забирать", "В пути", "Получен 24 августа", "Отменён 1 сентября")


def test_active_leaves_out_the_received_and_cancelled_rows(session: FakeSession) -> None:
    session.pages = {"/my/orderlist": CURRENT_PAGE}
    listed = service.list_orders("active")
    assert [order.status for order in listed] == ["Можно забирать", "В пути"]
    assert {order.state for order in listed} == {OrderState.ACTIVE}


def test_the_finished_rows_are_still_readable_and_labelled() -> None:
    states = [order.state for order in parse_orders(CURRENT_PAGE)]
    assert states == [OrderState.ACTIVE, OrderState.ACTIVE, OrderState.RECEIVED, OrderState.CANCELLED]


def test_all_does_not_serve_a_finished_order_twice(session: FakeSession) -> None:
    """Scope "all" is the active rows plus the archive, so nothing arrives twice."""
    archive = _orderlist("Получен 24 августа")
    session.pages = {"selectedTab=archive": archive, "/my/orderlist": CURRENT_PAGE}
    statuses = [order.status for order in service.list_orders("all")]
    assert statuses.count("Получен 24 августа") == 1
