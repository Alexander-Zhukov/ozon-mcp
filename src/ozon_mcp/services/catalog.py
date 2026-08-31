"""Catalog + purchase-history read services."""

from __future__ import annotations

import base64
import json
import re
from typing import TYPE_CHECKING

from ozon_mcp.constants import (
    PURCHASE_SORTS,
    PURCHASES_LIST_ID,
    SEARCH_SORTS,
    WEB_DELIVERY_CI,
    WEB_DELIVERY_STATE_ID,
)
from ozon_mcp.dependencies import get_session
from ozon_mcp.models.catalog import (
    Cheaper,
    Description,
    ProductCard,
    Reviews,
    SearchFilter,
    Tile,
)
from ozon_mcp.parsing import catalog as parse
from ozon_mcp.parsing.common import next_page
from ozon_mcp.parsing.orders import order_numbers_from_link, parse_order_products

if TYPE_CHECKING:
    from ozon_mcp.models.orders import OrderProduct

_ORDER_NUMBER_RE = re.compile(r"\d{6,}-\d{3,}")

_DELIVERY_JS = r"""() => {
  const m = (document.body.innerText || '').match(
    /Доставим[^\n]{0,40}|Доставка[^\n]{0,40}|Послезавтра|Завтра|Сегодня/);
  return m ? m[0].trim() : null;
}"""


def _sku(sku_or_url: str) -> str:
    match = re.search(r"(\d{6,})", sku_or_url)
    return str(match.group(1)) if match else sku_or_url


def _price_number(price: str | None) -> int | None:
    digits = re.sub(r"\D", "", price or "")
    return int(digits) if digits else None


def _query_string(filters: dict[str, str] | None) -> str:
    return "".join(f"&{k}={v}" for k, v in (filters or {}).items() if v not in {None, ""})


def search(query: str, sort: str = "popular", page: int = 1, filters: dict[str, str] | None = None) -> list[Tile]:
    value = SEARCH_SORTS.get(sort, sort)
    url = f"/search/?text={query}&page={page}" + (f"&sorting={value}" if value else "") + _query_string(filters)
    return parse.parse_tiles(get_session().fetch(url))


def get_search_filters(query: str) -> list[SearchFilter]:
    return parse.parse_filters(
        get_session().fetch(
            f"/search/?text={query}&layout_container=filtersDesktop&layout_page_index=2", backend="entrypoint"
        )
    )


def browse_category(
    category: str, sort: str = "popular", page: int = 1, filters: dict[str, str] | None = None
) -> list[Tile]:
    value = SEARCH_SORTS.get(sort, sort)
    url = (
        f"/category/{category.strip('/')}/?page={page}"
        + (f"&sorting={value}" if value else "")
        + _query_string(filters)
    )
    return parse.parse_tiles(get_session().fetch(url))


def product_details(sku_or_url: str) -> ProductCard:
    sku = _sku(sku_or_url)
    return parse.parse_product(get_session().fetch(f"/product/{sku}/"))


def get_photos(sku_or_url: str) -> list[str]:
    return parse.parse_gallery(get_session().fetch(f"/product/{_sku(sku_or_url)}/"))


def get_reviews(sku_or_url: str) -> Reviews:
    return parse.parse_reviews(get_session().fetch(f"/product/{_sku(sku_or_url)}/reviews/"))


def get_characteristics(sku_or_url: str) -> list[parse.Characteristic]:
    return parse.parse_characteristics(get_session().fetch(f"/product/{_sku(sku_or_url)}/"))


def get_description(sku_or_url: str) -> Description:
    sku = _sku(sku_or_url)
    data = get_session().fetch(
        f"/product/{sku}/?layout_container=pdpPage2column&layout_page_index=2", backend="entrypoint"
    )
    return parse.parse_description(sku, data)


def delivery_estimate(sku_or_url: str) -> dict[str, str | None]:
    """Delivery estimate for a product, relative to the account's address.

    Served by the per-widget endpoint, which is ~100x faster than rendering the
    page. That endpoint is pinned to Ozon's current layout, so if it stops
    answering we read the rendered page instead rather than returning nothing.
    """
    sku = _sku(sku_or_url)
    async_data = base64.b64encode(
        json.dumps({"ci": WEB_DELIVERY_CI, "url": f"/product/{sku}/"}, ensure_ascii=False).encode()
    ).decode()
    state = get_session().widget_state(WEB_DELIVERY_STATE_ID, async_data).get("state")
    if state:
        return {"sku": sku, **parse.parse_delivery_widget(state)}
    delivery = get_session().page_extract(f"/product/{sku}/", _DELIVERY_JS)
    return {"sku": sku, "delivery": delivery, "address": None, "source": None}


def find_cheaper(sku_or_url: str, limit: int = 10) -> Cheaper:
    product = product_details(sku_or_url)
    base_price = _price_number(product.price)
    results = search(product.title or "")
    cheaper = [
        t for t in results if _price_number(t.price) and base_price and (_price_number(t.price) or 0) < base_price
    ]
    cheaper.sort(key=lambda t: _price_number(t.price) or 1 << 30)
    return Cheaper(base={"title": product.title, "price": product.price}, cheaper=cheaper[:limit])


def order_products(order: str) -> list[OrderProduct]:
    """Products of an order, over HTTP.

    Accepts either an order number ("44563249-0833") or the ``detail_link`` from
    list_orders, which encodes the parcels the row covers.
    """
    session = get_session()
    numbers = [order] if _ORDER_NUMBER_RE.fullmatch(order.strip()) else order_numbers_from_link(order)
    products: list[OrderProduct] = []
    seen: set[str] = set()
    for number in numbers:
        data = session.fetch(f"/my/orderdetails/?order={number}")
        for product in parse_order_products(data):
            if product.sku not in seen:
                seen.add(product.sku)
                products.append(product)
    return products


def _paginate_tiles(path: str, limit: int, backend: str = "composer") -> list[Tile]:
    session = get_session()
    tiles: list[Tile] = []
    seen: set[str] = set()
    data = session.fetch(path, backend=backend)
    for _ in range(200):
        for tile in parse.parse_tiles(data):
            if tile.sku and tile.sku not in seen:
                seen.add(tile.sku)
                tiles.append(tile)
        following = next_page(data)
        if len(tiles) >= limit or not following:
            break
        data = session.fetch(following, backend="entrypoint")
    return tiles[:limit]


def list_purchases(limit: int = 100, sort: str = "newest") -> list[Tile]:
    value = PURCHASE_SORTS.get(sort, sort)
    path = f"/my/favorites/list?list={PURCHASES_LIST_ID}" + (f"&sorting={value}" if value else "")
    return _paginate_tiles(path, limit)


def search_purchases(query: str, limit: int = 60) -> list[Tile]:
    return _paginate_tiles(f"/my/purchases/search?text={query}", limit, backend="entrypoint")
