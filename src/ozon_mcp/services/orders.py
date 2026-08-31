"""Order + archive (completed-orders) services."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from ozon_mcp.dependencies import get_session
from ozon_mcp.parsing.orders import parse_orders

if TYPE_CHECKING:
    from ozon_mcp.models.orders import Order

_MAX_ARCHIVE_PAGES = 200


def _archive_pages(limit: int, stop_before: str | None = None) -> list[Order]:
    """Completed-orders history (tab «Завершённые»), paginated via the archive
    "load more" cursor embedded in each response. Archive is newest→oldest, so
    ``stop_before`` (ISO date) ends pagination once a whole page is older.
    """
    session = get_session()
    orders: list[Order] = []
    seen: set[str] = set()
    data = session.fetch("/my/orderlist?selectedTab=archive")
    for _ in range(_MAX_ARCHIVE_PAGES):
        page = parse_orders(data)
        for order in page:
            if order.detail_link and order.detail_link not in seen:
                seen.add(order.detail_link)
                orders.append(order)
        if len(orders) >= limit or not page:
            break
        if stop_before:
            page_dates = [o.date for o in page if o.date]
            if page_dates and max(page_dates) < stop_before:
                break
        match = re.search(
            r"/my/orderlist\?[^\"\\ ]*archiveOrdersStart=\d+[^\"\\ ]*", json.dumps(data, ensure_ascii=False)
        )
        if not match:
            break
        following = match.group(0).replace("\\u0026", "&").replace("\\/", "/")
        data = session.fetch(following, backend="entrypoint")
    return orders[:limit]


def list_orders(scope: str = "active", limit: int = 100) -> list[Order]:
    orders: list[Order] = []
    if scope in {"active", "all"}:
        orders += parse_orders(get_session().fetch("/my/orderlist"))
    if scope in {"completed", "all"}:
        orders += _archive_pages(limit)
    return orders if scope == "active" else orders[:limit]


def orders_by_date(date_from: str, date_to: str, max_orders: int = 300) -> list[Order]:
    return [o for o in _archive_pages(max_orders, stop_before=date_from) if o.date and date_from <= o.date <= date_to]
