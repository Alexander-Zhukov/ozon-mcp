"""Catalog + purchase-history read services."""

from __future__ import annotations

import base64
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
from ozon_mcp.errors import OzonError
from ozon_mcp.models.catalog import (
    Cheaper,
    DeliveryEstimate,
    Description,
    ProductCard,
    Reviews,
    SearchFilter,
    Tile,
)
from ozon_mcp.parsing import catalog as parse
from ozon_mcp.parsing.common import declared_counter, next_pages
from ozon_mcp.parsing.orders import order_numbers_from_link, parse_order_products
from ozon_mcp.utils.serde import dumps

if TYPE_CHECKING:
    from ozon_mcp.models.orders import OrderProduct

_MAX_TILE_PAGES = 200

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


def search(
    query: str | None = None,
    category: str | None = None,
    sort: str = "popular",
    page: int = 1,
    filters: dict[str, str] | None = None,
) -> list[Tile]:
    """Storefront search, by text and/or inside a category.

    Ozon serves both from the same shape, and an agent usually has either a
    phrase, a category, or both — so this is one entry point rather than two
    tools that differ only in the path.
    """
    value = SEARCH_SORTS.get(sort, sort)
    if not query and not category:
        msg = "search needs a query, a category, or both"
        raise OzonError(msg)
    base = f"/category/{category.strip('/')}/" if category else "/search/"
    url = f"{base}?page={page}"
    if query:
        url += f"&text={query}"
    if value:
        url += f"&sorting={value}"
    return parse.parse_tiles(get_session().fetch(url + _query_string(filters)))


def get_search_filters(query: str) -> list[SearchFilter]:
    return parse.parse_filters(
        get_session().fetch(
            f"/search/?text={query}&layout_container=filtersDesktop&layout_page_index=2", backend="entrypoint"
        )
    )


def product_details(
    sku_or_url: str,
    *,
    with_description: bool = False,
    with_reviews: bool = False,
) -> ProductCard:
    """The product card, optionally with its description and reviews.

    Those two live behind their own endpoints, so they are opt-in: the common
    "what is this and what does it cost" stays a single request.
    """
    sku = _sku(sku_or_url)
    card = parse.parse_product(get_session().fetch(f"/product/{sku}/"))
    # The card is asked for by sku, so that is the sku it has — the page does not
    # always repeat it, and answering None for what the caller just passed in is
    # no help to anyone.
    card.sku = card.sku or sku
    if with_description:
        described = get_description(sku)
        card.description = described.description
        card.description_images = described.images
    if with_reviews:
        card.reviews = get_reviews(sku)
    return card


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


def delivery_estimate(sku_or_url: str) -> DeliveryEstimate:
    """Delivery estimate for a product, relative to the account's address.

    Served by the per-widget endpoint, which is ~100x faster than rendering the
    page. That endpoint is pinned to Ozon's current layout, so if it stops
    answering we read the rendered page instead rather than returning nothing.
    """
    sku = _sku(sku_or_url)
    async_data = base64.b64encode(dumps({"ci": WEB_DELIVERY_CI, "url": f"/product/{sku}/"}).encode()).decode()
    state = get_session().widget_state(WEB_DELIVERY_STATE_ID, async_data).get("state")
    if state:
        return DeliveryEstimate(sku=sku, **parse.parse_delivery_widget(state))
    delivery = get_session().page_extract(f"/product/{sku}/", _DELIVERY_JS)
    return DeliveryEstimate(sku=sku, delivery=delivery)


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


def _paginate_tiles(path: str, limit: int, backend: str = "composer", counter: str | None = None) -> list[Tile]:
    """Walk a scroll-paginated tile list.

    A page that comes back empty is retried once before the walk ends: an
    upstream hiccup looks exactly like the end of the list from here, and
    treating it as the end silently returns a short list that the caller has no
    way to tell from a complete one.
    """
    session = get_session()
    tiles: list[Tile] = []
    seen: set[str] = set()
    data = session.fetch(path, backend=backend)
    # A page offers a paginator per block, and one of them is always
    # "you might also like" — followed by mistake, it fills the answer with
    # products that are not on the list at all.
    ceiling = declared_counter(data, counter) if counter else None
    target = min(limit, ceiling) if ceiling else limit
    for _ in range(_MAX_TILE_PAGES):
        for tile in parse.parse_tiles(data):
            if tile.sku and tile.sku not in seen:
                seen.add(tile.sku)
                tiles.append(tile)
        if len(tiles) >= target:
            break
        advanced = False
        for following in next_pages(data):
            page = session.fetch(following, backend="entrypoint")
            if parse.parse_tiles(page):
                data, advanced = page, True
                break
            # An upstream hiccup reads the same as the end of the list.
            page = session.fetch(following, backend="entrypoint")
            if parse.parse_tiles(page):
                data, advanced = page, True
                break
        if not advanced:
            break
    return tiles[:target]


def purchases(query: str | None = None, limit: int = 100, sort: str = "newest") -> list[Tile]:
    """Purchase history — everything ever bought, or just what matches a query.

    Ozon has a dedicated server-side search over purchases which is far cheaper
    than paginating the whole list, so a query switches to it.
    """
    if query:
        return _paginate_tiles(f"/my/purchases/search?text={query}", limit, backend="entrypoint")
    value = PURCHASE_SORTS.get(sort, sort)
    path = f"/my/favorites/list?list={PURCHASES_LIST_ID}" + (f"&sorting={value}" if value else "")
    return _paginate_tiles(path, limit)
