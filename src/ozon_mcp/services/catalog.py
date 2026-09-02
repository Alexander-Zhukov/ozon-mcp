"""Catalog + purchase-history read services."""

import base64
import re
from typing import Final
from urllib.parse import quote

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
    BoughtItems,
    Cheaper,
    DeliveryEstimate,
    Description,
    ProductCard,
    Purchase,
    Reviews,
    SearchFilter,
    Tile,
)
from ozon_mcp.models.orders import OrderProduct
from ozon_mcp.parsing import catalog as parse
from ozon_mcp.parsing.common import declared_counter, next_pages
from ozon_mcp.parsing.orders import ORDER_NUMBER_RE, order_numbers_from_link, parse_order_products
from ozon_mcp.utils.serde import dumps

_MAX_TILE_PAGES: Final = 200
# Deep enough to walk past the first pages, bounded so one query cannot crawl
# the whole category.
_MAX_SEARCH_PAGES: Final = 10
# The modal behind «Есть дешевле или быстрее»; its sort switcher offers price or
# delivery date, and price is the one this asks for.
_OFFERS_PATH: Final = "/modal/otherOffersFromSellers?product_id={sku}&sort=price"
# How far a comparison looks when the caller asked for a small top: the cheapest
# lot of a popular product is regularly a page or two down.
_CHEAPER_SEARCH_DEPTH: Final = 40
# Each order opened costs a request (0.16 s), and a tool call has to finish
# inside a client's timeout — so the default scan covers the recent months and
# says where it stopped, rather than spending minutes to be exhaustive.
_ORDER_SCAN_LIMIT: Final = 50


_DELIVERY_JS: Final = r"""() => {
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


def _payable(tile: Tile) -> int | None:
    """What this lot actually costs, in kopeck-free roubles.

    Ozon prints two live prices — one with its own bank cards, one with any
    other — and the first is what the account pays. Comparing on the other one
    calls a lot cheaper than a lot that is not.
    """
    return _price_number(tile.price)


def _query_string(filters: dict[str, str] | None) -> str:
    return "".join(f"&{k}={v}" for k, v in (filters or {}).items() if v not in {None, ""})


def search(
    query: str | None = None,
    category: str | None = None,
    sort: str = "popular",
    page: int = 1,
    filters: dict[str, str] | None = None,
    limit: int = 36,
) -> list[Tile]:
    """Storefront search, by text and/or inside a category.

    Ozon serves both from the same shape, and an agent usually has either a
    phrase, a category, or both — so this is one entry point rather than two
    tools that differ only in the path.

    ``limit`` is how deep to go, not how much of one page to keep: a page holds
    a few dozen tiles and the cheapest offer is regularly not on the first one,
    so pages are walked until there are enough or Ozon stops adding new ones.

    Ranking by price is redone here rather than trusted: Ozon's ``sorting=price``
    orders by its own figure, while the price actually charged is the one with
    the bank discount, and those two disagree per lot. So the walked results are
    re-sorted on the payable price — otherwise "the cheapest" is whatever Ozon
    felt like putting first.
    """
    value = SEARCH_SORTS.get(sort, sort)
    if not query and not category:
        msg = "search needs a query, a category, or both"
        raise OzonError(msg)
    base = f"/category/{category.strip('/')}/" if category else "/search/"
    tiles: list[Tile] = []
    seen: set[str] = set()
    for offset in range(_MAX_SEARCH_PAGES):
        url = f"{base}?page={page + offset}"
        if query:
            # Escaped here rather than by the transport, which leaves & and =
            # alone: a phrase holding one of those would otherwise detach into a
            # parameter of its own.
            url += f"&text={quote(query, safe='')}"
        if value:
            url += f"&sorting={value}"
        # Two mechanisms, and which one a query gets is Ozon's business: some
        # searches put results in the page, others leave it empty and serve them
        # through the page's own paginator. Reading the page alone answered "no
        # results" for a query whose results were all in the second kind.
        fresh = [
            tile for tile in _paginate_tiles(url + _query_string(filters), limit - len(tiles)) if tile.sku not in seen
        ]
        if not fresh:
            break
        seen.update(tile.sku for tile in fresh if tile.sku)
        tiles += fresh
        if len(tiles) >= limit:
            break
    if sort in {"cheap", "expensive"}:
        tiles.sort(key=lambda tile: _payable(tile) or (1 << 30), reverse=sort == "expensive")
    return tiles[:limit]


def get_search_filters(query: str) -> list[SearchFilter]:
    return parse.parse_filters(
        get_session().fetch(
            f"/search/?text={quote(query, safe='')}&layout_container=filtersDesktop&layout_page_index=2",
            backend="entrypoint",
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


def _resembles(base_title: str | None, candidate: str | None) -> bool:
    """Whether a search hit is plausibly the same thing as the base product.

    Only search results need this: Ozon's own offers are about this product by
    construction, while a title search ranks on words, so "cheaper" alone
    happily returns keycaps and drone cameras for a mouse. A candidate has to
    share at least half of the base title's own words — enough to keep the same
    product listed under a different seller's wording, and enough to drop a lot
    whose only common word is the brand.
    """
    words = set(re.findall(r"[\w]{4,}", (base_title or "").lower()))
    if not words:
        return True
    shared = words & set(re.findall(r"[\w]{4,}", (candidate or "").lower()))
    return len(shared) * 2 >= len(words)


def _other_offers(sku: str) -> list[Tile]:
    """What Ozon itself lists under «Есть дешевле или быстрее», cheapest first.

    The product card counts these offers and states the lowest price among them,
    and the modal behind it names them — which is the one source that is about
    *this* product rather than about a phrase that resembles its title.
    """
    data = get_session().fetch(_OFFERS_PATH.format(sku=sku), backend="entrypoint")
    return parse.parse_seller_offers(data)


def find_cheaper(sku_or_url: str, limit: int = 10) -> Cheaper:
    """The cheapest lots of the same thing, from both places Ozon puts them.

    Two sources, because each misses what the other finds: Ozon's own
    «Есть дешевле или быстрее» is about this exact product but only covers the
    offers it links, while a search by the card's title reaches lots that are the
    same product listed separately — and Ozon's text search is literal, so a lot
    whose title omits the brand does not come back for a query that includes it.

    They are merged into one ranking by payable price. The base price has to be
    readable for any of it to mean anything: answering "nothing is cheaper"
    because the price could not be parsed is the one outcome a caller cannot
    tell from good news, so it raises instead.
    """
    product = product_details(sku_or_url)
    base_price = _price_number(product.price)
    if base_price is None:
        msg = (
            f"could not read the price of {product.sku or sku_or_url}, so nothing can be called cheaper than it — "
            "read the card with product_details() and compare by hand"
        )
        raise OzonError(msg)

    offers = _other_offers(product.sku or _sku(sku_or_url))
    found = [
        tile
        for tile in search(product.title or "", sort="cheap", limit=max(limit * 4, _CHEAPER_SEARCH_DEPTH))
        if _resembles(product.title, tile.title)
    ]

    cheaper: list[Tile] = []
    seen: set[str] = {product.sku or ""}
    for tile in offers + found:
        payable = _payable(tile)
        if not tile.sku or tile.sku in seen or payable is None or payable >= base_price:
            continue
        seen.add(tile.sku)
        cheaper.append(tile)
    cheaper.sort(key=lambda tile: _payable(tile) or (1 << 30))
    return Cheaper(
        base={"title": product.title, "price": product.price, "sku": product.sku},
        cheaper=cheaper[:limit],
    )


def order_products(order: str) -> list[OrderProduct]:
    """Products of an order, over HTTP.

    Accepts either an order number ("44563249-0833") or the ``detail_link`` from
    list_orders, which encodes the parcels the row covers.
    """
    session = get_session()
    numbers = [order] if ORDER_NUMBER_RE.fullmatch(order.strip()) else order_numbers_from_link(order)
    products: list[OrderProduct] = []
    # One sku can travel in two parcels of the same order and end up received in
    # one and cancelled in the other, so the parcel is part of its identity.
    seen: set[tuple[str, str]] = set()
    for number in numbers:
        data = session.fetch(f"/my/orderdetails/?order={number}")
        for product in parse_order_products(data, order_number=number):
            key = (product.sku, product.shipment_id or "")
            if key not in seen:
                seen.add(key)
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


def purchases(query: str | None = None, limit: int = 100, sort: str = "newest") -> list[Purchase]:
    """Purchase history — everything ever ordered, or just what matches a query.

    Ozon has a dedicated server-side search over purchases which is far cheaper
    than paginating the whole list, so a query switches to it.

    The list itself says nothing about outcomes. «Купленные товары» holds every
    product that was ever ordered, refusals at the pickup point included, and its
    tiles carry a name and today's catalogue price — no order, no date, no
    status. Читая его одного, "куплено" is an assumption, and on this account a
    wrong one: two of the items in it came from an order Ozon shows as «Отменён».

    What it does not say is what became of any of it, so it does not answer
    "did I get this" — bought_items() does.
    """
    if query:
        found = _paginate_tiles(f"/my/purchases/search?text={quote(query, safe='')}", limit, backend="entrypoint")
    else:
        value = PURCHASE_SORTS.get(sort, sort)
        path = f"/my/favorites/list?list={PURCHASES_LIST_ID}" + (f"&sorting={value}" if value else "")
        found = _paginate_tiles(path, limit)
    return [Purchase(**tile.model_dump()) for tile in found]


def bought_items(
    query: str | None = None,
    skus: list[str] | None = None,
    limit: int = 100,
    scan_orders: int = _ORDER_SCAN_LIMIT,
    scan_before: str | None = None,
) -> BoughtItems:
    """What was actually received, by matching the purchase list against the orders.

    Two sources, because neither is enough alone: Ozon's «Купленные товары» is
    the only text index over the whole history (there is no search over orders),
    and the orders are the only place an outcome exists.

    Every order opened costs a request, and this account's archive holds 870 of
    them, so a full sweep runs into minutes and a client times out on it. Hence
    the scan is bounded and the answer says how far it looked: ``scanned_orders``,
    ``scanned_back_to`` and the skus still ``unresolved``.

    Going deeper is done by asking about the leftovers rather than by re-running
    the whole thing: pass ``skus`` — the ``unresolved`` of the previous answer —
    with ``scan_before=<scanned_back_to>``. That skips the index entirely and
    scans only older orders. Re-running with a bigger bound instead re-reads what
    was already covered, and a continuation that carried the query alone came
    back with every sku unresolved, because the ones it had placed live in orders
    newer than the window.

    A sku found in several parcels counts as received if any of them was, which
    is what "I have it" means when one of two was refused.
    """
    from ozon_mcp.services.orders import list_orders  # ruff: ignore[import-outside-top-level] - avoids a cycle

    found = (
        [Purchase(sku=str(sku), url=f"https://www.ozon.ru/product/{sku}/") for sku in skus]
        if skus
        else purchases(query, limit)
    )
    wanted = {purchase.sku: purchase for purchase in found if purchase.sku}
    if not wanted:
        return BoughtItems(items=found, complete=True)

    rows = (
        list_orders("completed", limit=scan_orders, date_to=scan_before)
        if scan_before
        else list_orders("all", limit=scan_orders)
    )
    numbers: list[str] = []
    for row in rows:
        for number in row.order_numbers or ([row.order_number] if row.order_number else []):
            if number not in numbers:
                numbers.append(number)

    # "Refused" is not an answer to "did I ever get it": the same product may
    # have been received in an older order, and stopping at the first match got
    # exactly that wrong — a jogger refused in August had been received in
    # February, and the scan never looked. Only a receipt settles a sku.
    settled: set[str] = set()
    seen: set[str] = set()
    scanned = 0
    oldest: str | None = None
    dates = {number: row.date for row in rows for number in row.order_numbers or []}
    for number in numbers[:scan_orders]:
        scanned += 1
        oldest = dates.get(number) or oldest
        for product in order_products(number):
            purchase = wanted.get(product.sku)
            if purchase is None or product.sku in settled:
                continue
            seen.add(product.sku)
            purchase.order_number = product.order_number or number
            purchase.order_status = product.shipment_status
            purchase.received = product.received
            if product.received is True:
                settled.add(product.sku)
        if settled == set(wanted):
            break
    exhausted = scanned < scan_orders  # the archive ran out before the bound did
    return BoughtItems(
        items=found,
        scanned_orders=scanned,
        scanned_back_to=oldest,
        complete=settled == set(wanted) or exhausted,
        unresolved=sorted(set(wanted) - seen),
        provisional=sorted(seen - settled),
    )
