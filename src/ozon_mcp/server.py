"""FastMCP server: thin tools that delegate to the service layer.

Read tools work off a saved authenticated session; mutation tools (cart /
favorites / lists) are gated behind ``OZON_ENABLE_WRITES`` because they change
the real account.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

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
def list_orders(scope: str = "active", limit: int = 100) -> list[Order]:
    """Orders with status, pickup point, delivery slot/ETA, total, product
    thumbnails and (for completed orders) a purchase date.
    scope: active (current) | completed (archive «Завершённые», dated) | all.
    """
    return orders.list_orders(scope, limit)


@mcp.tool()
def orders_by_date(date_from: str, date_to: str, max_orders: int = 300) -> list[Order]:
    """Completed orders whose date is in [date_from; date_to] (ISO YYYY-MM-DD).
    Dates come from the archive tab; pagination stops early past the range.
    """
    return orders.orders_by_date(date_from, date_to, max_orders)


@mcp.tool()
def order_products(order_detail_link: str) -> list[OrderProduct]:
    """Products of one order as SKUs + links (order → product card). Pass a
    detail_link from list_orders()[].detail_link or .products[].detail_link.
    """
    return catalog.order_products(order_detail_link)


# ── purchase history ─────────────────────────────────────────────────────────
@mcp.tool()
def list_purchases(limit: int = 100, sort: str = "newest") -> list[Tile]:
    """Purchase history — bought items as sku/title/price/url. Paginates the
    «Покупки» list. sort: newest | oldest (by purchase date) | cheap | discount.
    """
    return catalog.list_purchases(limit, sort)


@mcp.tool()
def search_purchases(query: str, limit: int = 60) -> list[Tile]:
    """Server-side search in purchase history (fast, ~0.1s). Returns matches
    only, as product tiles.
    """
    return catalog.search_purchases(query, limit)


# ── catalog / product ────────────────────────────────────────────────────────
@mcp.tool()
def search(query: str, sort: str = "popular", page: int = 1, filters: dict[str, str] | None = None) -> list[Tile]:
    """Ozon storefront search → product tiles (sku/title/price/url).
    sort: popular | new | cheap | expensive | rating | discount.
    filters (from get_search_filters): checkbox/category {key: option_value};
    range {key: "min;max"} e.g. {"currency_price": "200;600"}.
    """
    return catalog.search(query, sort, page, filters)


@mcp.tool()
def get_search_filters(query: str) -> list[SearchFilter]:
    """Facets for a query: {name, key, type, options|range}. Apply in
    search(filters={key: value}) — checkbox/category value = option.value;
    range value = "min;max". Flow: search → get_search_filters → search(filters).
    """
    return catalog.get_search_filters(query)


@mcp.tool()
def browse_category(
    category: str, sort: str = "popular", page: int = 1, filters: dict[str, str] | None = None
) -> list[Tile]:
    """Products of a category by slug (e.g. 'produkty-dlya-doma-9200'; slug from
    get_search_filters categoryFilter). sort/filters as in search. page >= 1.
    """
    return catalog.browse_category(category, sort, page, filters)


@mcp.tool()
def product_details(sku_or_url: str) -> ProductCard:
    """Product card: title, price, variants (each variant = sku+price+availability
    +link), characteristics, all gallery photos. Accepts a SKU or a product URL.
    Description → get_description; reviews → get_reviews; delivery → delivery_estimate.
    """
    return catalog.product_details(sku_or_url)


@mcp.tool()
def get_photos(sku_or_url: str) -> list[str]:
    """All product photo URLs from the gallery. Accepts SKU or URL."""
    return catalog.get_photos(sku_or_url)


@mcp.tool()
def get_reviews(sku_or_url: str) -> Reviews:
    """Reviews: overall score, individual reviews (author/score/text/date) and
    review photos. Accepts SKU or URL.
    """
    return catalog.get_reviews(sku_or_url)


@mcp.tool()
def get_characteristics(sku_or_url: str) -> list[Characteristic]:
    """Product characteristics (name/value). Accepts SKU or URL."""
    return catalog.get_characteristics(sku_or_url)


@mcp.tool()
def get_description(sku_or_url: str) -> Description:
    """Product description text + embedded images. Accepts SKU or URL."""
    return catalog.get_description(sku_or_url)


@mcp.tool()
def delivery_estimate(sku_or_url: str) -> dict[str, str | None]:
    """Delivery ETA (e.g. «Доставим с 9 сентября»), read from the rendered card.
    Accepts SKU or URL.
    """
    return catalog.delivery_estimate(sku_or_url)


@mcp.tool()
def find_cheaper(sku_or_url: str, limit: int = 10) -> Cheaper:
    """Find the same/similar product cheaper: takes the card title, searches the
    storefront and returns options below the current price. Accepts SKU or URL.
    """
    return catalog.find_cheaper(sku_or_url, limit)


# ── cart ─────────────────────────────────────────────────────────────────────
@mcp.tool()
def get_cart() -> Cart:
    """Current cart: items with title, price, quantity (current/max) and flags."""
    return cart.get_cart()


@mcp.tool()
def add_to_cart(sku: str, quantity: int = 1) -> dict[str, Any]:
    """[GATED] Add a product to the cart. For apparel pass the concrete variant
    SKU (the base SKU won't add without a chosen size).
    """
    return cart.add_to_cart(sku, quantity)


@mcp.tool()
def set_cart_quantity(sku: str, quantity: int) -> dict[str, Any]:
    """[GATED] Set a cart item quantity (0 removes it)."""
    return cart.set_cart_quantity(sku, quantity)


@mcp.tool()
def remove_from_cart(sku: str) -> dict[str, Any]:
    """[GATED] Remove a product from the cart."""
    return cart.remove_from_cart(sku)


# ── favorites / collections / wishlists ──────────────────────────────────────
@mcp.tool()
def list_favorites(page: int = 1) -> list[Tile]:
    """Favorites as product tiles: sku, title, price, old price, url."""
    return favorites.list_favorites(page)


@mcp.tool()
def favorites_price_snapshot() -> dict[str, int | None]:
    """{sku: price} snapshot of favorites — a building block for monitoring."""
    return favorites.favorites_price_snapshot()


@mcp.tool()
def check_favorite_price_drops() -> PriceDiff:
    """Record current favorites prices and return the diff vs the last run:
    {drops, rises, added, removed}. Run periodically (schedule externally).
    """
    return favorites.check_favorite_price_drops()


@mcp.tool()
def list_collections() -> list[ListRef]:
    """User collections (tab «Подборки»): name + item count."""
    return favorites.list_collections()


@mcp.tool()
def list_wishlists() -> list[ListRef]:
    """User wishlists (tab «Вишлисты»): name + item count."""
    return favorites.list_wishlists()


@mcp.tool()
def get_lists(sku: str) -> list[ListId]:
    """Collections and wishlists with their ids (for add_to_list/remove_from_list),
    from the list-select modal for a product. Accepts a SKU.
    """
    return favorites.get_lists(sku)


@mcp.tool()
def list_returns() -> dict[str, list[str]]:
    """Buyer returns."""
    return favorites.list_returns()


@mcp.tool()
def set_favorite(sku: str, add: bool = True) -> dict[str, Any]:  # ruff: ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]
    """[GATED] Favorites. add=True adds the product, add=False removes it."""
    return favorites.set_favorite(sku, add=add)


@mcp.tool()
def add_to_list(sku: str, list_id: int) -> dict[str, Any]:
    """[GATED] Add a product to a collection/wishlist by its id (see get_lists)."""
    return favorites.add_to_list(sku, list_id)


@mcp.tool()
def remove_from_list(sku: str, list_id: int) -> dict[str, Any]:
    """[GATED] Remove a product from a collection/wishlist by its id."""
    return favorites.remove_from_list(sku, list_id)


# ── finance ──────────────────────────────────────────────────────────────────
@mcp.tool()
def get_finances() -> Finances:
    """Ozon Card balance and total points/bonuses. Breakdown → get_points."""
    return finance.get_finances()


@mcp.tool()
def get_points() -> Points:
    """Points by type (Ozon points, miles, WOW points, stars) with amounts,
    burning points, and per-store seller bonuses.
    """
    return finance.get_points()
