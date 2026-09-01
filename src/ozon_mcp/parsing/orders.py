"""Parse order widgets into DTOs, including archive dates."""

import base64
import datetime
import re
from typing import Any, Final

from ozon_mcp.models.orders import Order, OrderProduct, OrderThumbnail
from ozon_mcp.parsing.common import find_all, prices, walk, widget, widgets_all
from ozon_mcp.utils.serde import loads

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
        decoded = loads(base64.urlsafe_b64decode(token))
        return [int(x) for x in decoded.get("orderIds", [])]
    except (ValueError, TypeError):
        return []


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
        postings = loads(base64.urlsafe_b64decode(token)).get("postings", [])
    except (ValueError, TypeError):
        return []
    numbers: list[str] = []
    for posting in postings:
        number = "-".join(str(posting).split("-")[:2])
        if number and number not in numbers:
            numbers.append(number)
    return numbers


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


# An order number as Ozon writes it: "44563249-0877".
ORDER_NUMBER_RE: Final = re.compile(r"\d{6,}-\d{3,}")
_ORDER_PARAM_RE: Final = re.compile(r"[?&]order=(\d{6,}-\d{3,})")


def order_numbers_in(row: Any) -> list[str]:
    """Order numbers a listed row is about.

    A row is a delivery group, not an order: its own link bundles the postings of
    every order arriving together, so decoding that link gives the whole bundle
    and pins nothing to this row. Each product on the row, though, links to its
    own order — ``/my/orderdetails/?order=44563249-0833`` — which is where the
    number for *this* row is.
    """
    found: list[str] = []
    for node in walk(row):
        link = node.get("link")
        match = _ORDER_PARAM_RE.search(link) if isinstance(link, str) else None
        if match and match.group(1) not in found:
            found.append(match.group(1))
    return found


def parse_orders(data: dict[str, Any]) -> list[Order]:
    """Orders from the ordersV2 widget (active list or archive)."""
    state = widget(data, "orderList")
    rows = state.get("ordersV2") if isinstance(state, dict) else None
    orders: list[Order] = []
    for row in rows or []:
        left = row.get("leftBlock") or {}
        products = ((row.get("rightBlock") or {}).get("products") or {}).get("products") or []
        action = (row.get("common") or {}).get("action") or {}
        numbers = order_numbers_in(row)
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
                order_number=next(iter(numbers), None),
                order_numbers=numbers,
            )
        )
    return orders


_PRODUCT_LINK_RE: Final = re.compile(r"/product/(?:[a-z0-9\-]+-)?(\d{6,})")


def _atom(value: Any) -> str | None:
    """Text of a value that may be a plain string or a ``{"text": …}`` atom."""
    if isinstance(value, str):
        return str(value).strip() or None
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return str(text).strip() or None
    return None


def parse_order_products(data: dict[str, Any]) -> list[OrderProduct]:
    """Products of an order-details page, read from their own fields.

    The page nests them as ``shipmentWidget.items[].sellers[].products[]`` — one
    shipmentWidget per parcel, grouped by seller — and each product carries its
    name, price, chosen variant and a link whose action id *is* the sku. Reading
    that structure avoids guessing: the page also renders statuses, tracking
    sentences and seller names that no text-shape heuristic can tell from a
    product name.
    """
    products: list[OrderProduct] = []
    seen: set[str] = set()
    for state in widgets_all(data, "shipmentWidget"):
        for item in state.get("items") or []:
            if not isinstance(item, dict):
                continue
            for seller in item.get("sellers") or []:
                if not isinstance(seller, dict):
                    continue
                seller_name = _atom(seller.get("name"))
                for product in seller.get("products") or []:
                    if not isinstance(product, dict):
                        continue
                    title = product.get("title") or {}
                    action = ((title.get("common") or {}).get("action")) or {}
                    sku = str(action.get("id") or "")
                    if not sku:
                        match = _PRODUCT_LINK_RE.search(str(action.get("link") or ""))
                        sku = match.group(1) if match else ""
                    if not sku or sku in seen:
                        continue
                    seen.add(sku)
                    price_texts = (product.get("price") or {}).get("price") or []
                    attributes = product.get("attributes") or []
                    products.append(
                        OrderProduct(
                            sku=sku,
                            title=_atom(title.get("name")),
                            price=next((_atom(entry) for entry in price_texts if _atom(entry)), None),
                            variant=next((_atom(entry) for entry in attributes if _atom(entry)), None),
                            seller=seller_name,
                            url=f"https://www.ozon.ru/product/{sku}/",
                        )
                    )
    return products
