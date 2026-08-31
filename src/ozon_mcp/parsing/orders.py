"""Parse order widgets into DTOs, including archive dates."""

from __future__ import annotations

import base64
import datetime
import json
import operator
import re
from typing import Any, Final

from ozon_mcp.models.orders import Order, OrderProduct, OrderThumbnail
from ozon_mcp.parsing.common import find_all, prices, walk, widget, widgets_all

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


def order_numbers_from_link(link: str | None) -> list[str]:
    """Order numbers behind an order row.

    The row's ``detail_link`` is a cacheOrderProducts blob listing *postings*
    ("44563249-0833-6"); the order page is keyed by the number without the
    trailing parcel segment.
    """
    match = re.search(r"data=([A-Za-z0-9_\-=]+)", link or "")
    if not match:
        return []
    try:
        token = match.group(1) + "=" * (-len(match.group(1)) % 4)
        postings = json.loads(base64.urlsafe_b64decode(token)).get("postings", [])
    except (ValueError, TypeError):
        return []
    numbers: list[str] = []
    for posting in postings:
        number = "-".join(str(posting).split("-")[:2])
        if number and number not in numbers:
            numbers.append(number)
    return numbers


_PRODUCT_LINK_RE = re.compile(r"/product/(?:[a-z0-9\-]+-)?(\d{6,})")

# Phrases the order page shows next to a product that are not its name.
_NOT_A_TITLE_RE = re.compile(
    r"^(Причина отмены|Можно забирать|В службе доставки|Заказ (от|покинул)|Доставим|Отменён|Из пункта выдачи|Доставка)",
    re.IGNORECASE,
)


def parse_order_products(data: dict[str, Any]) -> list[OrderProduct]:
    """Products of an order-details page.

    They live in the shipmentWidget instances — one per parcel — so the page's
    recommendation grids are skipped by only reading those.

    The sku is authoritative. The title is **best-effort**: a product's name is
    a sibling of its link rather than a child, and the page is dense with
    statuses, tracking sentences, cancellation reasons and seller names, none of
    which can be told from a product name by shape alone. The tightest node
    still containing exactly one product is used as that product's card, with
    the obvious service phrases filtered out — good enough to recognise an item,
    not something to display verbatim. For a reliable name, resolve the sku with
    product_details.
    """
    products: dict[str, OrderProduct] = {}
    for state in widgets_all(data, "shipmentWidget"):
        cards: list[tuple[int, str, str | None]] = []
        for node in walk(state):
            blob = json.dumps(node, ensure_ascii=False)
            skus = set(_PRODUCT_LINK_RE.findall(blob))
            if len(skus) != 1:
                continue
            titles = [
                text.strip()
                for text in find_all(node, "text")
                if isinstance(text, str) and 15 < len(text.strip()) < 200 and not _NOT_A_TITLE_RE.match(text.strip())
            ]
            cards.append((len(blob), skus.pop(), max(titles, key=len, default=None)))
        # Tightest wrapper first, so a product's own card wins over its section.
        for _, sku, title in sorted(cards, key=operator.itemgetter(0)):
            existing = products.get(sku)
            if existing is None or (existing.title is None and title is not None):
                products[sku] = OrderProduct(sku=sku, title=title, url=f"https://www.ozon.ru/product/{sku}/")
    return list(products.values())
