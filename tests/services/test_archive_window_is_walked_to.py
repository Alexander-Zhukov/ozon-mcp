"""A date window deep in the archive has to be walked to, not filtered for.

The archive is a newest-first cursor, so the only way to a window two years back
is to page down to it. Counting every row scanned against the limit stopped the
walk before it arrived: July 2024 with a limit of 500 ended somewhere in 2025 and
answered "no orders that month" for a month that had eleven.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ozon_mcp.services import orders
from ozon_mcp.utils.serde import dumps
from support import page

if TYPE_CHECKING:
    from support import FakeSession


def _row(number: str, status: str) -> dict[str, Any]:
    return {
        "common": {"action": {"link": f"v2/cacheOrderProducts?data={number}"}},
        "leftBlock": {"textIcon": {"text": {"text": status, "testInfo": {"automatizationId": "tileStatus"}}}},
        "rightBlock": {"products": {"products": []}},
    }


def _archive(rows: list[dict[str, Any]], *, more: bool) -> dict[str, Any]:
    served = page(orderList={"ordersV2": rows})
    if more:
        # The cursor Ozon embeds in the response; the walk finds it by pattern.
        served["widgetStates"]["paginator-1-default-1"] = dumps({
            "nextPage": "/my/orderlist?selectedTab=archive&archiveOrdersStart=12345"
        })
    return served


NEWEST = _archive([_row("0900", "Получен 24 августа"), _row("0899", "Получен 20 августа")], more=True)
MIDDLE = _archive([_row("0700", "Получен 8 августа 2025"), _row("0699", "Получен 1 августа 2025")], more=True)
WANTED = _archive([_row("0500", "Получен 28 июля 2024"), _row("0499", "Получен 1 июля 2024")], more=True)
OLDER = _archive([_row("0300", "Получен 12 мая 2024")], more=False)


def test_a_window_below_the_limit_is_still_reached(session: FakeSession) -> None:
    pages = iter([NEWEST, MIDDLE, WANTED, OLDER])
    session.pages = {"/my/orderlist": lambda: next(pages, OLDER)}
    found = orders.list_orders("completed", limit=2, date_from="2024-07-01", date_to="2024-07-31")
    assert [order.date for order in found] == ["2024-07-28", "2024-07-01"]


def test_the_walk_stops_once_a_page_is_wholly_older(session: FakeSession) -> None:
    pages = iter([NEWEST, MIDDLE, WANTED, OLDER])
    session.pages = {"/my/orderlist": lambda: next(pages, OLDER)}
    orders.list_orders("completed", limit=100, date_from="2024-07-01", date_to="2024-07-31")
    # Four pages: three to arrive, one whose newest row is already older.
    assert len([url for url in session.fetched if "orderlist" in url]) == 4


def test_a_row_without_a_date_is_outside_the_window(session: FakeSession) -> None:
    session.pages = {"/my/orderlist": _archive([_row("0100", "Получен")], more=False)}
    assert orders.list_orders("completed", limit=10, date_from="2024-07-01", date_to="2024-07-31") == []
