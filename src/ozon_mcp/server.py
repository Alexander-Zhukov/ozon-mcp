"""FastMCP server: thin tools that delegate to the service layer.

Read tools work off a saved authenticated session; mutation tools (cart /
favorites / lists) are gated behind ``OZON_ENABLE_WRITES`` because they change
the real account.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ozon_mcp.dependencies import run_blocking

# FastMCP introspects each tool's signature at registration (get_type_hints), so
# these return-type models must be importable at runtime, not TYPE_CHECKING-only.
from ozon_mcp.models.cart import Cart
from ozon_mcp.models.catalog import (
    Characteristic,
    Cheaper,
    Description,
    ProductCard,
    Reviews,
    SearchFilter,
    Tile,
)
from ozon_mcp.models.checkout import Checkout
from ozon_mcp.models.finance import Finances, Points
from ozon_mcp.models.lists import ListId, ListRef, PriceDiff
from ozon_mcp.models.orders import Order, OrderProduct
from ozon_mcp.services import cart, catalog, checkout, favorites, finance, orders

mcp = FastMCP("ozon")


# ── orders ───────────────────────────────────────────────────────────────────
@mcp.tool()
async def list_orders(scope: str = "active", limit: int = 100) -> list[Order]:
    """Orders with status, pickup point, delivery slot/ETA, total, product
    thumbnails and (for completed orders) a purchase date.
    scope: active (current) | completed (archive «Завершённые», dated) | all.
    """
    return await run_blocking(lambda: orders.list_orders(scope, limit))


@mcp.tool()
async def orders_by_date(date_from: str, date_to: str, max_orders: int = 300) -> list[Order]:
    """Completed orders whose date is in [date_from; date_to] (ISO YYYY-MM-DD).
    Dates come from the archive tab; pagination stops early past the range.
    """
    return await run_blocking(lambda: orders.orders_by_date(date_from, date_to, max_orders))


@mcp.tool()
async def order_products(order: str) -> list[OrderProduct]:
    """Products of one order as SKUs and links (order → product card).
    Accepts an order number ("44563249-0833") or a detail_link from
    list_orders()[].detail_link / .products[].detail_link.
    `title` is best-effort — the order page mixes product names with statuses and
    seller names; use product_details(sku) when the exact name matters.
    """
    return await run_blocking(lambda: catalog.order_products(order))


# ── purchase history ─────────────────────────────────────────────────────────
@mcp.tool()
async def list_purchases(limit: int = 100, sort: str = "newest") -> list[Tile]:
    """Purchase history — bought items as sku/title/price/url. Paginates the
    «Покупки» list. sort: newest | oldest (by purchase date) | cheap | discount.
    """
    return await run_blocking(lambda: catalog.list_purchases(limit, sort))


@mcp.tool()
async def search_purchases(query: str, limit: int = 60) -> list[Tile]:
    """Server-side search in purchase history (fast, ~0.1s). Returns matches
    only, as product tiles.
    """
    return await run_blocking(lambda: catalog.search_purchases(query, limit))


# ── catalog / product ────────────────────────────────────────────────────────
@mcp.tool()
async def search(query: str, sort: str = "popular", page: int = 1, filters: dict[str, str] | None = None) -> list[Tile]:
    """Ozon storefront search → product tiles (sku/title/price/url).
    sort: popular | new | cheap | expensive | rating | discount.
    filters (from get_search_filters): checkbox/category {key: option_value};
    range {key: "min;max"} e.g. {"currency_price": "200;600"}.
    """
    return await run_blocking(lambda: catalog.search(query, sort, page, filters))


@mcp.tool()
async def get_search_filters(query: str) -> list[SearchFilter]:
    """Facets for a query: {name, key, type, options|range}. Apply in
    search(filters={key: value}) — checkbox/category value = option.value;
    range value = "min;max". Flow: search → get_search_filters → search(filters).
    """
    return await run_blocking(lambda: catalog.get_search_filters(query))


@mcp.tool()
async def browse_category(
    category: str, sort: str = "popular", page: int = 1, filters: dict[str, str] | None = None
) -> list[Tile]:
    """Products of a category by slug (e.g. 'produkty-dlya-doma-9200'; slug from
    get_search_filters categoryFilter). sort/filters as in search. page >= 1.
    """
    return await run_blocking(lambda: catalog.browse_category(category, sort, page, filters))


@mcp.tool()
async def product_details(sku_or_url: str) -> ProductCard:
    """Product card: title, price, variants (each variant = sku+price+availability
    +link), characteristics, all gallery photos. Accepts a SKU or a product URL.
    Description → get_description; reviews → get_reviews; delivery → delivery_estimate.
    """
    return await run_blocking(lambda: catalog.product_details(sku_or_url))


@mcp.tool()
async def get_photos(sku_or_url: str) -> list[str]:
    """All product photo URLs from the gallery. Accepts SKU or URL."""
    return await run_blocking(lambda: catalog.get_photos(sku_or_url))


@mcp.tool()
async def get_reviews(sku_or_url: str) -> Reviews:
    """Reviews: overall score, individual reviews (author/score/text/date) and
    review photos. Accepts SKU or URL.
    """
    return await run_blocking(lambda: catalog.get_reviews(sku_or_url))


@mcp.tool()
async def get_characteristics(sku_or_url: str) -> list[Characteristic]:
    """Product characteristics (name/value). Accepts SKU or URL."""
    return await run_blocking(lambda: catalog.get_characteristics(sku_or_url))


@mcp.tool()
async def get_description(sku_or_url: str) -> Description:
    """Product description text + embedded images. Accepts SKU or URL."""
    return await run_blocking(lambda: catalog.get_description(sku_or_url))


@mcp.tool()
async def delivery_estimate(sku_or_url: str) -> dict[str, str | None]:
    """Delivery ETA (e.g. «Доставим с 9 сентября»), read from the rendered card.
    Accepts SKU or URL.
    """
    return await run_blocking(lambda: catalog.delivery_estimate(sku_or_url))


@mcp.tool()
async def find_cheaper(sku_or_url: str, limit: int = 10) -> Cheaper:
    """Find the same/similar product cheaper: takes the card title, searches the
    storefront and returns options below the current price. Accepts SKU or URL.
    """
    return await run_blocking(lambda: catalog.find_cheaper(sku_or_url, limit))


# ── cart ─────────────────────────────────────────────────────────────────────
@mcp.tool()
async def get_cart() -> Cart:
    """Current cart: items with title, price, quantity (current/max) and flags."""
    return await run_blocking(cart.get_cart)


@mcp.tool()
async def select_cart_items(skus: list[str] | None = None, mode: str = "only") -> Cart:
    """[GATED] Choose which cart items make up the order — this is what composes
    a checkout; get_checkout() is empty until something is selected.
    mode: only (order exactly these, unticking the rest) | add | remove |
    all (every item) | none (clear the selection).
    skus are `id` values from get_cart(); required for only/add/remove.
    """
    return await run_blocking(lambda: cart.select_cart_items(skus, mode))


@mcp.tool()
async def add_to_cart(sku: str, quantity: int = 1) -> dict[str, Any]:
    """[GATED] Add a product to the cart. For apparel pass the concrete variant
    SKU (the base SKU won't add without a chosen size).
    """
    return await run_blocking(lambda: cart.add_to_cart(sku, quantity))


@mcp.tool()
async def set_cart_quantity(sku: str, quantity: int) -> dict[str, Any]:
    """[GATED] Set a cart item quantity (0 removes it)."""
    return await run_blocking(lambda: cart.set_cart_quantity(sku, quantity))


@mcp.tool()
async def remove_from_cart(sku: str) -> dict[str, Any]:
    """[GATED] Remove a product from the cart."""
    return await run_blocking(lambda: cart.remove_from_cart(sku))


# ── favorites / collections / wishlists ──────────────────────────────────────
@mcp.tool()
async def list_favorites(page: int = 1) -> list[Tile]:
    """Favorites as product tiles: sku, title, price, old price, url."""
    return await run_blocking(lambda: favorites.list_favorites(page))


@mcp.tool()
async def favorites_price_snapshot() -> dict[str, int | None]:
    """{sku: price} snapshot of favorites — a building block for monitoring."""
    return await run_blocking(favorites.favorites_price_snapshot)


@mcp.tool()
async def check_favorite_price_drops() -> PriceDiff:
    """Record current favorites prices and return the diff vs the last run:
    {drops, rises, added, removed}. Run periodically (schedule externally).
    """
    return await run_blocking(favorites.check_favorite_price_drops)


@mcp.tool()
async def list_collections() -> list[ListRef]:
    """User collections (tab «Подборки»): name + item count."""
    return await run_blocking(favorites.list_collections)


@mcp.tool()
async def list_wishlists() -> list[ListRef]:
    """User wishlists (tab «Вишлисты»): name + item count."""
    return await run_blocking(favorites.list_wishlists)


@mcp.tool()
async def get_lists(sku: str) -> list[ListId]:
    """Collections and wishlists with their ids (for add_to_list/remove_from_list),
    from the list-select modal for a product. Accepts a SKU.
    """
    return await run_blocking(lambda: favorites.get_lists(sku))


@mcp.tool()
async def list_returns() -> dict[str, list[str]]:
    """Buyer returns."""
    return await run_blocking(favorites.list_returns)


@mcp.tool()
async def set_favorite(sku: str, add: bool = True) -> dict[str, Any]:
    """[GATED] Favorites. add=True adds the product, add=False removes it."""
    return await run_blocking(lambda: favorites.set_favorite(sku, add=add))


@mcp.tool()
async def add_to_list(sku: str, list_id: int) -> dict[str, Any]:
    """[GATED] Add a product to a collection/wishlist by its id (see get_lists)."""
    return await run_blocking(lambda: favorites.add_to_list(sku, list_id))


@mcp.tool()
async def remove_from_list(sku: str, list_id: int) -> dict[str, Any]:
    """[GATED] Remove a product from a collection/wishlist by its id."""
    return await run_blocking(lambda: favorites.remove_from_list(sku, list_id))


# ── checkout ─────────────────────────────────────────────────────────────────
@mcp.tool()
async def get_checkout() -> Checkout:
    """The order being formed from the cart, with every option that can be
    changed: payment methods (each with its payment_type), the pay-on-delivery
    switch, one entry per destination in `deliveries` (each with its shipments
    in split_keys and its selectable pickup_points), the per-shipment delivery
    dates, points choices and the money breakdown.
    Change any of it with configure_checkout; submit with place_order.
    Requires an intact OzonID login; returns available=false with a reason if the
    cart is empty or checkout is not reachable.
    """
    return await run_blocking(checkout.get_checkout)


@mcp.tool()
async def configure_checkout(
    payment: str | None = None,
    points: int | None = None,
    pay_after_receipt: bool | None = None,
    pickup_point: str | None = None,
    split_key: str | None = None,
) -> Checkout:
    """Set checkout options and return the recomputed order. Omit an argument to
    leave that option alone; everything you can pass comes from get_checkout().
    payment: a word, a masked card or the raw id — "СБП", "SberPay", "новой
      картой", "**5898", or 1626 / 2044 / 3 / 22.
    points: how many Ozon points to spend; 0 spends none. Allowed amounts are in
      the `points` field — Ozon caps what it accepts.
    pay_after_receipt: true/false for «Оплатить после получения» (pay on
      delivery for part of the order); only if pay_after_receipt.available.
    pickup_point: the point number ("№1449460" or "1449460"), a piece of its
      address ("Данилова"), or the address_book_id. Must be one whose
      `available` is true; unavailable ones carry Ozon's reason in `note`.
    split_key: which shipment to retarget, from deliveries[].split_keys. Only
      needed when the order has more than one destination — then it is required,
      since moving the wrong parcel is not something to guess at.
    """
    return await run_blocking(
        lambda: checkout.configure_checkout(
            payment=payment,
            points=points,
            pay_after_receipt=pay_after_receipt,
            pickup_point=pickup_point,
            split_key=split_key,
        )
    )


@mcp.tool()
async def place_order(confirm_total: str) -> dict[str, Any]:
    """[GATED — SPENDS MONEY] Submit the order that get_checkout() describes.
    confirm_total must equal get_checkout().totals.total (e.g. "12 648 ₽
    сегодня"); the call is refused if Ozon has since recalculated the order, so
    read get_checkout() immediately before calling and show the user that total.
    Disabled unless OZON_ENABLE_ORDERS=1, separately from OZON_ENABLE_WRITES.
    Irreversible from here: cancelling afterwards is done in Ozon itself.
    """
    return await run_blocking(lambda: checkout.place_order(confirm_total))


# ── finance ──────────────────────────────────────────────────────────────────
@mcp.tool()
async def get_finances() -> Finances:
    """Ozon Card balance and total points/bonuses. Breakdown → get_points."""
    return await run_blocking(finance.get_finances)


@mcp.tool()
async def get_points() -> Points:
    """Points by type (Ozon points, miles, WOW points, stars) with amounts,
    burning points, and per-store seller bonuses.
    """
    return await run_blocking(finance.get_points)
