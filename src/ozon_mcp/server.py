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
    Cheaper,
    Description,
    ProductCard,
    Reviews,
    SearchFilter,
    Tile,
)
from ozon_mcp.models.checkout import (
    CancelReason,
    Checkout,
    OrderCancelled,
    OrderPlaced,
    PaymentRequested,
)
from ozon_mcp.models.finance import Finances, Points
from ozon_mcp.models.lists import ListRef, PriceDiff
from ozon_mcp.models.orders import Order, OrderProduct
from ozon_mcp.services import cart, catalog, checkout, favorites, finance, orders

mcp = FastMCP("ozon")


# ── orders ───────────────────────────────────────────────────────────────────
@mcp.tool()
async def list_orders(
    scope: str = "active",
    limit: int = 100,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[Order]:
    """Orders with status, pickup point, delivery slot/ETA, total, product
    thumbnails and (for completed ones) the purchase date.
    scope: active (current) | completed (archive «Завершённые») | all.
    date_from / date_to: ISO YYYY-MM-DD. Giving either one searches the archive
    and stops paginating once past the window — use it for "what did I buy in
    July" instead of pulling the whole history.
    """
    return await run_blocking(lambda: orders.list_orders(scope, limit, date_from, date_to))


@mcp.tool()
async def order_products(order: str) -> list[OrderProduct]:
    """Items of one order: sku, title, price paid, chosen variant, seller and a
    product-card link.
    Accepts an order number ("44563249-0865") or a detail_link from
    list_orders()[].detail_link.
    """
    return await run_blocking(lambda: catalog.order_products(order))


@mcp.tool()
async def purchases(query: str | None = None, limit: int = 100, sort: str = "newest") -> list[Tile]:
    """Purchase history as product tiles. With `query` this uses Ozon's
    server-side search over purchases (fast); without it, the full list.
    sort (ignored when query is given): newest | oldest | cheap | discount.
    """
    return await run_blocking(lambda: catalog.purchases(query, limit, sort))


@mcp.tool()
async def list_returns() -> dict[str, list[str]]:
    """Buyer returns."""
    return await run_blocking(favorites.list_returns)


# ── catalog / product ────────────────────────────────────────────────────────
@mcp.tool()
async def search(
    query: str | None = None,
    category: str | None = None,
    sort: str = "popular",
    page: int = 1,
    filters: dict[str, str] | None = None,
) -> list[Tile]:
    """Storefront search → product tiles (sku/title/price/url). Pass a text
    query, a category slug (e.g. 'produkty-dlya-doma-9200'), or both.
    sort: popular | new | cheap | expensive | rating | discount.
    filters (from get_search_filters): checkbox/category {key: option_value};
    range {key: "min;max"}, e.g. {"currency_price": "200;600"}.
    """
    return await run_blocking(lambda: catalog.search(query, category, sort, page, filters))


@mcp.tool()
async def get_search_filters(query: str) -> list[SearchFilter]:
    """Facets available for a query: {name, key, type, options|range}. Apply them
    with search(filters={key: value}) — checkbox/category value = option.value,
    range value = "min;max". Flow: search → get_search_filters → search(filters).
    """
    return await run_blocking(lambda: catalog.get_search_filters(query))


@mcp.tool()
async def product_details(
    sku_or_url: str,
    with_description: bool = False,
    with_reviews: bool = False,
) -> ProductCard:
    """Product card: title, price, variants (each variant = sku + price +
    availability + link), characteristics and all gallery photos.
    with_description / with_reviews pull those in too — they are separate
    requests, so leave them off unless needed. Accepts a SKU or a product URL.
    """
    return await run_blocking(
        lambda: catalog.product_details(sku_or_url, with_description=with_description, with_reviews=with_reviews)
    )


@mcp.tool()
async def get_reviews(sku_or_url: str) -> Reviews:
    """Reviews on their own: overall score, individual reviews
    (author/score/text/date) and review photos.
    """
    return await run_blocking(lambda: catalog.get_reviews(sku_or_url))


@mcp.tool()
async def get_description(sku_or_url: str) -> Description:
    """Product description text plus the images embedded in it."""
    return await run_blocking(lambda: catalog.get_description(sku_or_url))


@mcp.tool()
async def delivery_estimate(sku_or_url: str) -> dict[str, str | None]:
    """When a product would arrive at the account's address, plus which
    warehouse it ships from ("С 9 сентября" / "ул. Данилова, 17" / "Со склада
    продавца").
    """
    return await run_blocking(lambda: catalog.delivery_estimate(sku_or_url))


@mcp.tool()
async def find_cheaper(sku_or_url: str, limit: int = 10) -> Cheaper:
    """Find the same or a similar product cheaper: takes the card's title,
    searches the storefront and returns options below the current price.
    """
    return await run_blocking(lambda: catalog.find_cheaper(sku_or_url, limit))


# ── cart ─────────────────────────────────────────────────────────────────────
@mcp.tool()
async def get_cart() -> Cart:
    """The whole cart (paginated through): items with title, price, quantity and
    `checked` — the tick is what decides the order's contents — plus Ozon's own
    group headings ("Доступны для заказа", «Бронирование товаров»).
    """
    return await run_blocking(cart.get_cart)


@mcp.tool()
async def set_cart_quantity(sku: str, quantity: int) -> dict[str, Any]:
    """[GATED] Set how many of a product are in the cart. quantity=0 removes it;
    adding is the same call with the quantity you want.
    For apparel pass the concrete variant SKU — a base SKU will not add without
    a chosen size.
    """
    return await run_blocking(lambda: cart.set_cart_quantity(sku, quantity))


@mcp.tool()
async def select_cart_items(skus: list[str] | None = None, mode: str = "only") -> Cart:
    """[GATED] Choose which cart items make up the order — this is what composes
    a checkout, and get_checkout() is empty until something is selected.
    mode: only (order exactly these, unticking the rest) | add | remove |
    all (every item) | none (clear).
    skus are `id` values from get_cart(); required for only/add/remove.
    """
    return await run_blocking(lambda: cart.select_cart_items(skus, mode))


# ── favorites, collections, wishlists ────────────────────────────────────────
@mcp.tool()
async def list_favorites(page: int = 1) -> list[Tile]:
    """Favorites as product tiles: sku, title, price, old price, url."""
    return await run_blocking(lambda: favorites.list_favorites(page))


@mcp.tool()
async def set_favorite(sku: str, add: bool = True) -> dict[str, Any]:
    """[GATED] Add the product to favorites (add=true) or remove it."""
    return await run_blocking(lambda: favorites.set_favorite(sku, add=add))


@mcp.tool()
async def get_lists(sku: str | None = None) -> list[ListRef]:
    """Collections and wishlists, each with its kind and item count.
    Pass a `sku` to get the same lists **with their list_id** — Ozon only
    exposes ids in a product's membership modal, and set_list_membership needs
    one.
    """
    return await run_blocking(lambda: favorites.get_lists(sku))


@mcp.tool()
async def set_list_membership(sku: str, list_id: int, add: bool = True) -> dict[str, Any]:
    """[GATED] Put a product into a collection/wishlist (add=true) or take it
    out. list_id comes from get_lists(sku).
    """
    return await run_blocking(lambda: favorites.set_list_membership(sku, list_id, add=add))


@mcp.tool()
async def check_favorite_price_drops() -> PriceDiff:
    """Record the current favorites prices and return the diff against the last
    run: {drops, rises, added, removed}. Call it periodically — the comparison
    is only as old as the previous call.
    """
    return await run_blocking(favorites.check_favorite_price_drops)


# ── checkout ─────────────────────────────────────────────────────────────────
@mcp.tool()
async def get_checkout() -> Checkout:
    """The order being formed from the selected cart items, with everything that
    can be changed: payment methods (each with its payment_type), the
    pay-on-delivery switch, one entry per destination in `deliveries` (each with
    its shipments in split_keys and its selectable pickup_points), per-shipment
    delivery dates, points choices and the money breakdown.
    Forms the checkout itself if Ozon has not yet. If it reports
    available=false, `reason` says what to fix — usually: select cart items.
    Change it with configure_checkout, submit with place_order.
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
    leave that option alone; everything passable comes from get_checkout().
    payment: a word, a masked card or the raw id — "СБП", "SberPay", "новой
      картой", "**5898", or 1626 / 2044 / 3 / 22.
    points: how many Ozon points to spend; 0 spends none.
    pay_after_receipt: true/false for «Оплатить после получения»; only when
      pay_after_receipt.available.
    pickup_point: the point number ("№1449460"), a piece of its address
      ("Данилова"), or its address_book_id. Must be one whose available is true.
    split_key: which shipment to retarget, from deliveries[].split_keys —
      required only when the order has more than one destination.
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
async def place_order(confirm_total: str) -> OrderPlaced:
    """[GATED — SPENDS MONEY] Submit the order that get_checkout() describes.
    confirm_total must equal get_checkout().totals.total (e.g. "0 ₽ сегодня");
    the call is refused if Ozon recalculated the order since, so read
    get_checkout() immediately before and show the user that total.
    Requires OZON_ENABLE_ORDERS=1, separately from OZON_ENABLE_WRITES.
    Returns only once the order actually exists, with its order_number — pass
    that to cancel_order to undo.
    """
    return await run_blocking(lambda: checkout.place_order(confirm_total))


@mcp.tool()
async def pay_order(order: str) -> PaymentRequested:
    """[GATED] Ask Ozon to charge an order left in «Ожидаем оплаты».
    Returns the page where the charge is completed. That page is on Ozon's bank
    domain and asks for the account's bank passcode, so hand `payment_url` to the
    user — this server does not hold banking credentials.
    Ordering with pay-on-delivery avoids this entirely.
    """
    return await run_blocking(lambda: orders.pay_order(order))


@mcp.tool()
async def list_cancel_reasons(order: str) -> list[CancelReason]:
    """Reasons Ozon will accept for cancelling an order, with their reason_id.
    The catch-all one (needs_comment=true) is refused without a comment.
    """
    return await run_blocking(lambda: orders.list_cancel_reasons(order))


@mcp.tool()
async def cancel_order(
    order: str,
    reason_id: str = "504",
    comment: str = "",
    return_to_cart: bool = True,
) -> OrderCancelled:
    """[GATED] Cancel an order by number ("44563249-0865"), by default returning
    its items to the cart.
    reason_id from list_cancel_reasons; "504" (изменить заказ и оформить заново)
    is the neutral default, "508" needs a comment.
    Check `cancelled` in the result — Ozon may answer with a retention offer
    instead of cancelling, and `detail` then carries what it asked.
    """
    return await run_blocking(lambda: orders.cancel_order(order, reason_id, comment, return_to_cart=return_to_cart))


# ── finance ──────────────────────────────────────────────────────────────────
@mcp.tool()
async def get_finances() -> Finances:
    """Ozon Card balance and the total points/bonuses. Breakdown → get_points."""
    return await run_blocking(finance.get_finances)


@mcp.tool()
async def get_points() -> Points:
    """Points by type (Ozon points, miles, WOW points, stars) with amounts,
    burning points, and per-store seller bonuses.
    """
    return await run_blocking(finance.get_points)
