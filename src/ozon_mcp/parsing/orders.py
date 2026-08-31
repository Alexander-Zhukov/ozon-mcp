"""Parse order widgets into DTOs, including archive dates."""

from __future__ import annotations

import base64
import datetime
import json
import re
from typing import Any, Final

from ozon_mcp.models.orders import Order, OrderThumbnail
from ozon_mcp.parsing.common import find_all, prices, widget

_RU_MONTHS: Final = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "мая": 5,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}


def order_ids_from_link(link: str | None) -> list[int]:
    """Decode orderIds from an order's cacheOrderProducts ``data=`` blob (used as
    the archiveOrdersStart cursor for the completed-orders history).
    """
    match = re.search(r"data=([A-Za-z0-9_\-=]+)", link or "")
    if not match:
        return []
    try:
        token = match.group(1) + "=" * (-len(match.group(1)) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(token))
        return [int(x) for x in decoded.get("orderIds", [])]
    except (ValueError, TypeError):
        return []


def parse_ru_date(text: object) -> str | None:
    """Parse «Получен 24 августа [2025]» → ISO ``YYYY-MM-DD``. Year defaults to
    the current one; a future result rolls back a year.
    """
    if not isinstance(text, str):
        return None
    match = re.search(r"(\d{1,2})\s+([а-яё]+)\s*(\d{4})?", text.replace(" ", " "), re.IGNORECASE)
    if not match:
        return None
    month = next((v for k, v in _RU_MONTHS.items() if match.group(2).lower().startswith(k)), None)
    if not month:
        return None
    year = int(match.group(3)) if match.group(3) else datetime.date.today().year
    try:
        parsed = datetime.date(year, month, int(match.group(1)))
    except ValueError:
        return None
    if not match.group(3) and parsed > datetime.date.today():
        parsed = parsed.replace(year=year - 1)
    return parsed.isoformat()


def parse_orders(data: dict[str, Any]) -> list[Order]:
    """Orders from the ordersV2 widget (active list or archive)."""
    state = widget(data, "orderList")
    rows = state.get("ordersV2") if isinstance(state, dict) else None
    orders: list[Order] = []
    for row in rows or []:
        left = row.get("leftBlock") or {}
        products = ((row.get("rightBlock") or {}).get("products") or {}).get("products") or []
        action = (row.get("common") or {}).get("action") or {}
        status_texts = [
            t.get("text") for t in find_all(left.get("textIcon") or {}, "text") if isinstance(t, dict) and t.get("text")
        ]
        slot = (left.get("subtitle") or {}).get("text")
        thumbnails: list[OrderThumbnail] = []
        for product in products:
            media = (product.get("image") or {}).get("productMedia") or {}
            thumbnails.append(
                OrderThumbnail(
                    photo=(media.get("image") or {}).get("url"),
                    detail_link=((media.get("common") or {}).get("action") or {}).get("link"),
                )
            )
        orders.append(
            Order(
                pickup=(left.get("title") or {}).get("text"),
                slot=slot,
                delivery_eta=slot,
                status=status_texts[0] if status_texts else None,
                date=next((parse_ru_date(t) for t in [*status_texts, slot] if parse_ru_date(t)), None),
                total=next(iter(prices(products)), None),
                items_count=len(products),
                products=thumbnails,
                detail_link=action.get("link"),
                order_ids=order_ids_from_link(action.get("link")),
            )
        )
    return orders
