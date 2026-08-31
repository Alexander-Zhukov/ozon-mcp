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
from ozon_mcp.models.finance import Finances, Points
from ozon_mcp.models.lists import ListId, ListRef, PriceDiff
from ozon_mcp.models.orders import Order, OrderProduct
from ozon_mcp.services import cart, catalog, favorites, finance, orders

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
async def order_products(order_detail_link: str) -> list[OrderProduct]:
    """Products of one order as SKUs + links (order → product card). Pass a
    detail_link from list_orders()[].detail_link or .products[].detail_link.
    """
    return await run_blocking(lambda: catalog.order_products(order_detail_link))


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
