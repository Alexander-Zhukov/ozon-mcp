"""Parse order widgets into DTOs, including archive dates."""

import base64
import datetime
import re
from typing import Any, Final

from ozon_mcp.models.enums import OrderState
from ozon_mcp.models.orders import Order, OrderLine, OrderProduct
from ozon_mcp.parsing.common import find_all, walk, widget, widgets_all
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


def parse_ru_date(text: object, *, upcoming: bool = False) -> str | None:
    """Parse «Получен 24 августа [2025]» → ISO ``YYYY-MM-DD``.

    Ozon omits the year on near dates, so it is inferred: a status looks back, a
    deadline («Хранится до 14 сентября») looks forward — ``upcoming`` picks which.
    """
    if not isinstance(text, str):
        return None
    match = re.search(r"(\d{1,2})\s+([а-яё]+)\s*(\d{4})?", text.replace(" ", " "), re.IGNORECASE)
    if not match:
        return None
    month = next((v for k, v in _RU_MONTHS.items() if match.group(2).lower().startswith(k)), None)
    if not month:
        return None
    today = datetime.date.today()
    year = int(match.group(3)) if match.group(3) else today.year
    try:
        parsed = datetime.date(year, month, int(match.group(1)))
    except ValueError:
        return None
    if not match.group(3):
        if upcoming and parsed < today:
            parsed = parsed.replace(year=year + 1)
        elif not upcoming and parsed > today:
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


# The row renders the item price, the item's payment badge and the group's
# pay-on-pickup sum as the same price atom, so the automatizationId Ozon tags
# each with is the only way to tell them apart.
_STATUS_TAG: Final = "tileStatus"
_POSTPAY_CELL_TAG: Final = "postpay_sum_cell"
_ITEM_PAYMENT_TAG: Final = "itemPay"
_ITEM_PRICE_TAG: Final = "payMoney"
_ITEM_QUANTITY_TAG: Final = "itemQuantity"
_ITEM_STORAGE_TAG: Final = "postingPvzExpiration"
_PAID_BADGE: Final = "Оплачен"
# Ozon's status vocabulary; anything else («В пути», «Можно забирать») is active.
_TERMINAL_STATUSES: Final = {"Получен": OrderState.RECEIVED, "Отменён": OrderState.CANCELLED}


def _atom(value: Any) -> str | None:
    """Text of a value that may be a plain string or a ``{"text": …}`` atom."""
    if isinstance(value, str):
        return str(value).strip() or None
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return str(text).strip() or None
    return None


def _tagged(node: Any, tag: str) -> dict[str, Any] | None:
    """The node Ozon tagged with this ``automatizationId``, which hangs either on
    the node itself or under its ``common``.
    """
    for candidate in walk(node):
        for holder in (candidate, candidate.get("common")):
            info = holder.get("testInfo") if isinstance(holder, dict) else None
            if isinstance(info, dict) and info.get("automatizationId") == tag:
                return candidate
    return None


def _tagged_text(node: Any, tag: str) -> str | None:
    return _atom(_tagged(node, tag))


def _money(node: Any) -> str | None:
    """The sum in a price node, rendered as a list of styled parts — either the
    price node itself (``price`` is the list) or a block holding one (``price.price``).
    """
    parts = node.get("price") if isinstance(node, dict) else None
    if isinstance(parts, dict):
        parts = parts.get("price")
    if not isinstance(parts, list):
        return None
    return next((_atom(part) for part in parts if _atom(part)), None)


def _state(status: str | None) -> OrderState:
    first = (status or "").split()
    return _TERMINAL_STATUSES.get(first[0], OrderState.ACTIVE) if first else OrderState.ACTIVE


def _line(product: dict[str, Any]) -> OrderLine:
    media = (product.get("image") or {}).get("productMedia") or {}
    link = ((media.get("common") or {}).get("action") or {}).get("link")
    badge = _tagged_text(product, _ITEM_PAYMENT_TAG)
    number = _ORDER_PARAM_RE.search(link) if isinstance(link, str) else None
    return OrderLine(
        photo=(media.get("image") or {}).get("url"),
        detail_link=link,
        order_number=number.group(1) if number else None,
        paid=badge.startswith(_PAID_BADGE) if badge else None,
        payment_status=badge,
        price=_money(_tagged(product, _ITEM_PRICE_TAG)),
        quantity=_tagged_text(product, _ITEM_QUANTITY_TAG),
        stored_until=parse_ru_date(_tagged_text(product, _ITEM_STORAGE_TAG), upcoming=True),
    )


def parse_orders(data: dict[str, Any]) -> list[Order]:
    """Orders from the ordersV2 widget (active list or archive).

    Money comes from the tagged nodes: the group's «К оплате при получении» from
    one cell of the row's cellList, the price and payment badge from each item.
    The row states no order total.
    """
    state = widget(data, "orderList")
    rows = state.get("ordersV2") if isinstance(state, dict) else None
    orders: list[Order] = []
    for row in rows or []:
        left = row.get("leftBlock") or {}
        products = ((row.get("rightBlock") or {}).get("products") or {}).get("products") or []
        action = (row.get("common") or {}).get("action") or {}
        numbers = order_numbers_in(row)
        status = _tagged_text(left.get("textIcon") or {}, _STATUS_TAG) or _atom(
            next(iter(find_all(left.get("textIcon") or {}, "text")), None)
        )
        slot = _atom(left.get("subtitle"))
        postpay = _tagged(left, _POSTPAY_CELL_TAG)
        orders.append(
            Order(
                pickup=_atom(left.get("title")),
                slot=slot,
                delivery_eta=slot,
                status=status,
                state=_state(status),
                date=next((parse_ru_date(text) for text in (status, slot) if parse_ru_date(text)), None),
                amount_due_at_pickup=_money((postpay or {}).get("rightBlock")),
                items_count=len(products),
                products=[_line(product) for product in products if isinstance(product, dict)],
                detail_link=action.get("link"),
                order_ids=order_ids_from_link(action.get("link")),
                order_number=next(iter(numbers), None),
                order_numbers=numbers,
            )
        )
    return orders


_PRODUCT_LINK_RE: Final = re.compile(r"/product/(?:[a-z0-9\-]+-)?(\d{6,})")


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
