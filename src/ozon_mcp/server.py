"""FastMCP server: thin tools that delegate to the service layer.

Read tools work off a saved authenticated session; mutation tools (cart /
favorites / lists) are gated behind ``OZON_ENABLE_WRITES`` because they change
the real account.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ozon_mcp.dependencies import run_blocking

# FastMCP introspects each tool's signature at registration (get_type_hints), so
# these return-type models must be importable at runtime, not TYPE_CHECKING-only.
from ozon_mcp.models.cart import Cart
from ozon_mcp.models.catalog import (
    Cheaper,
    DeliveryEstimate,
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
from ozon_mcp.models.common import WriteResult
from ozon_mcp.models.finance import Finances, Points
from ozon_mcp.models.lists import ListRef, PriceDiff
from ozon_mcp.models.orders import Order, OrderProduct, Return
from ozon_mcp.models.session import LoginStep, SessionStatus
from ozon_mcp.services import cart, catalog, checkout, favorites, finance, orders, session
from ozon_mcp.utils.annotations import (
    CartSelectMode,
    IsoDate,
    Limit,
    OrderRef,
    OrderScope,
    Page,
    PurchaseSort,
    SearchSort,
    Sku,
    SkuOrUrl,
)

INSTRUCTIONS = """Read-write access to one ozon.ru buyer account: orders, purchases, returns, cart,
favorites, collections, product cards, catalog search, checkout, Ozon Card balance and points.
Everything acts on the signed-in account of a real person, and money is real.

Start with session_status(). It answers three things you cannot guess: whether the session is
alive, whether you may change anything (writes_enabled) and whether you may place an order
(orders_enabled). Those two are the operator's settings — no tool can change them, so plan
around them instead of discovering them halfway through.

Buying, in order — each step is a precondition for the next:
  1. find the product: search() -> product_details() and take the SKU of the exact variant
     (apparel: the size's own SKU, not the base one)
  2. set_cart_quantity(sku, n)
  3. select_cart_items([sku, ...], mode="only") — the ticks ARE the order's contents, and
     get_checkout() sees nothing until something is ticked
  4. get_checkout() — read it before deciding anything: it lists the payment methods, the
     pickup points, the pay-on-delivery switch and the money
  5. configure_checkout(...) with values taken from that answer
  6. show the user totals.order_total, then place_order(confirm_total=<that figure>)
  7. if payment is still pending: pay_order(order_number)
Undo: cancel_order(order_number), optionally skus=[...] for single lines.

Two figures, never interchangeable: totals.total is what Ozon charges today, totals.order_total
is what the order costs. On a pay-on-delivery order today's charge is 0 ₽ — quote order_total to
the user, or you will tell them a 6 691 ₽ order is free. pay_after_receipt.scope says whether
deferral covers the whole order ("full"), part of it ("partial", and then pay_now_items /
pay_on_receipt_items name which lines fall on which side) or nothing ("none").

When a tool raises, the message says what to do next; it is written to be relayed. A signed-out
session raises everywhere rather than answering with an empty account: recover with
start_login(login) and submit_login_code(code), which needs a code only the account owner
receives — so ask, never guess.

Prices, dates and addresses are returned as Ozon renders them, in Russian and in roubles. Pass
identifiers back exactly as received."""

mcp = FastMCP("ozon", instructions=INSTRUCTIONS)


# ── orders ───────────────────────────────────────────────────────────────────
@mcp.tool()
async def list_orders(
    scope: OrderScope = "active",
    limit: Limit = 100,
    date_from: IsoDate | None = None,
    date_to: IsoDate | None = None,
) -> list[Order]:
    """Orders with status, pickup point, delivery slot/ETA, total, product
    thumbnails and (for completed ones) the purchase date. Use this for "where
    is my order" and "what did it cost"; for "what did I buy" use purchases().
    Giving either date searches the archive and stops paginating once past the
    window — cheaper than pulling the whole history for one month.
    Pass an entry's order number or detail_link on to order_products(),
    cancel_order() or pay_order().
    """
    return await run_blocking(lambda: orders.list_orders(scope, limit, date_from, date_to))


@mcp.tool()
async def order_products(order: OrderRef) -> list[OrderProduct]:
    """Items of one order: sku, title, price paid, chosen variant, seller and a
    product-card link.
    Accepts an order number ("44563249-0865") or a detail_link from
    list_orders()[].detail_link.
    """
    return await run_blocking(lambda: catalog.order_products(order))


@mcp.tool()
async def purchases(
    query: Annotated[
        str | None,
        Field(description="Text to search the purchase history for; omit to list all of it."),
    ] = None,
    limit: Limit = 100,
    sort: PurchaseSort = "newest",
) -> list[Tile]:
    """Everything ever bought, as product tiles (sku/title/price/url) — the
    answer to "have I bought this before" and "buy that thing again".
    With `query` Ozon searches its own purchase history server-side, which is
    much cheaper than paging through all of it.
    Orders, statuses and totals are not here: that is list_orders().
    """
    return await run_blocking(lambda: catalog.purchases(query, limit, sort))


@mcp.tool()
async def list_returns() -> list[Return]:
    """Returns this account has opened, with their status. Empty list means
    none are open — the page also carries Ozon's returns FAQ, which is not
    reported as data.
    """
    return await run_blocking(favorites.list_returns)


# ── catalog / product ────────────────────────────────────────────────────────
@mcp.tool()
async def search(
    query: Annotated[str | None, Field(description="Search text. Give this, a category, or both.")] = None,
    category: Annotated[
        str | None,
        Field(description='A category slug from a category URL, e.g. "produkty-dlya-doma-9200".'),
    ] = None,
    sort: SearchSort = "popular",
    page: Page = 1,
    filters: Annotated[
        dict[str, str] | None,
        Field(
            description="Facets from get_search_filters(): {key: option_value} for a checkbox or category, "
            '{key: "min;max"} for a range, e.g. {"currency_price": "200;600"}.'
        ),
    ] = None,
) -> list[Tile]:
    """Storefront search → product tiles (sku/title/price/url). Give a text
    query, a category slug ("produkty-dlya-doma-9200"), or both.
    A tile is not a card: for variants, characteristics, photos and stock call
    product_details() with its sku.
    filters comes from get_search_filters() — {key: option_value} for a
    checkbox or category facet, {key: "min;max"} for a range, e.g.
    {"currency_price": "200;600"}. Narrowing by price is a filter, not a sort.
    """
    return await run_blocking(lambda: catalog.search(query, category, sort, page, filters))


@mcp.tool()
async def get_search_filters(
    query: Annotated[str, Field(description="The same search text whose facets you want.")],
) -> list[SearchFilter]:
    """Facets available for a query: {name, key, type, options|range}. Apply them
    with search(filters={key: value}) — checkbox/category value = option.value,
    range value = "min;max". Flow: search → get_search_filters → search(filters).
    """
    return await run_blocking(lambda: catalog.get_search_filters(query))


@mcp.tool()
async def product_details(
    sku_or_url: SkuOrUrl,
    with_description: Annotated[
        bool,
        Field(description="Also fetch the description text and its images (one extra request)."),
    ] = False,
    with_reviews: Annotated[
        bool,
        Field(description="Also fetch the reviews (one extra request)."),
    ] = False,
) -> ProductCard:
    """Product card: title, price, variants, characteristics, gallery photos.
    Each variant carries its own sku, price and availability — that sku is what
    goes into the cart, and for apparel it is the only one that will add.
    with_description / with_reviews fetch those too (separate requests each);
    get_description() and get_reviews() do the same on their own.
    """
    return await run_blocking(
        lambda: catalog.product_details(sku_or_url, with_description=with_description, with_reviews=with_reviews)
    )


@mcp.tool()
async def get_reviews(sku_or_url: SkuOrUrl) -> Reviews:
    """Reviews on their own: overall score, individual reviews
    (author/score/text/date) and review photos.
    """
    return await run_blocking(lambda: catalog.get_reviews(sku_or_url))


@mcp.tool()
async def get_description(sku_or_url: SkuOrUrl) -> Description:
    """Product description text plus the images embedded in it."""
    return await run_blocking(lambda: catalog.get_description(sku_or_url))


@mcp.tool()
async def delivery_estimate(sku_or_url: SkuOrUrl) -> DeliveryEstimate:
    """When a product would arrive, to which of the account's addresses, and
    from which warehouse ("Завтра, 2 сентября" / "ул. Данилова, 17" / "Со
    склада Ozon"). The date is relative to that address, so quote both.
    This is per product, before ordering; for an existing order the dates are
    in list_orders(), and for an order being formed in get_checkout().
    """
    return await run_blocking(lambda: catalog.delivery_estimate(sku_or_url))


@mcp.tool()
async def find_cheaper(sku_or_url: SkuOrUrl, limit: Limit = 10) -> Cheaper:
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
async def set_cart_quantity(
    sku: Sku,
    quantity: Annotated[int, Field(ge=0, le=999, description="Desired quantity in the cart; 0 removes the item.")],
) -> WriteResult:
    """[GATED by writes_enabled] Set how many of a product are in the cart.
    Adding, changing and removing are all this one call: quantity=0 removes.
    Ozon reports nothing about the outcome, so the cart is read back: `ok=false`
    with the reason in `detail` means the call was accepted and changed nothing
    — an out-of-stock product, or an apparel base SKU with no size chosen (use
    the variant sku from product_details()).
    Being in the cart is not being in the order: tick it with
    select_cart_items() before checkout.
    """
    return await run_blocking(lambda: cart.set_cart_quantity(sku, quantity))


@mcp.tool()
async def select_cart_items(
    skus: Annotated[
        list[str] | None,
        Field(description='Cart item ids (the `id` field of get_cart().items). Required for "only", "add", "remove".'),
    ] = None,
    mode: CartSelectMode = "only",
) -> Cart:
    """[GATED by writes_enabled] Choose which cart items make up the order.
    This is the step that composes a checkout: get_checkout() reports nothing
    orderable until something is ticked, and it orders exactly what is ticked —
    so "buy these two" is mode="only" with those two skus, whatever else the
    cart holds. Returns the cart as it is afterwards, so the ticks can be
    checked before ordering.
    """
    return await run_blocking(lambda: cart.select_cart_items(skus, mode))


# ── favorites, collections, wishlists ────────────────────────────────────────
@mcp.tool()
async def list_favorites(limit: Limit = 100) -> list[Tile]:
    """Favorites as product tiles: sku, title, price, old price, url.
    Paginated through for you — `limit` caps how many come back, there is no
    page to ask for.
    """
    return await run_blocking(lambda: favorites.list_favorites(limit))


@mcp.tool()
async def set_favorite(
    sku: Sku,
    add: Annotated[bool, Field(description="True adds to favorites, False removes.")] = True,
) -> WriteResult:
    """[GATED by writes_enabled] Add a product to favorites or remove it.
    Ozon reports no outcome for this, so `detail` names the read that confirms
    it — list_favorites(). Favorites are what check_favorite_price_drops()
    watches.
    """
    return await run_blocking(lambda: favorites.set_favorite(sku, add=add))


@mcp.tool()
async def get_lists(
    sku: Annotated[
        str | None,
        Field(description="A product SKU: the same lists, each with `contains` saying whether it holds that product."),
    ] = None,
) -> list[ListRef]:
    """The account's wishlists (вишлисты), each with its size and list_id — which
    is what set_list_membership() and delete_list() take. With a sku, every list
    also carries `contains`, so a product already in a list is not added twice.
    Ozon's «Подборки» are a different thing, kept elsewhere and not exposed.
    """
    return await run_blocking(lambda: favorites.get_lists(sku))


@mcp.tool()
async def create_list(
    name: Annotated[str, Field(min_length=1, description="Name for the new wishlist, as the user would read it.")],
) -> ListRef:
    """[GATED by writes_enabled] Create an empty wishlist and return it with its
    list_id, ready for set_list_membership(). An empty name is refused by Ozon.
    Wishlists are the only list this account can create — «Подборки» are not
    made this way.
    """
    return await run_blocking(lambda: favorites.create_list(name))


@mcp.tool()
async def delete_list(
    list_id: Annotated[int, Field(description="The list to delete, from get_lists()[].list_id.")],
) -> WriteResult:
    """[GATED by writes_enabled] Delete a wishlist. The products in it are not
    deleted — they stay in favorites and in any other list. Not undoable: the
    list itself is gone, so confirm with the user first.
    """
    return await run_blocking(lambda: favorites.delete_list(list_id))


@mcp.tool()
async def set_list_membership(
    sku: Sku,
    list_id: Annotated[int, Field(description="Target list, from get_lists()[].list_id.")],
    add: Annotated[bool, Field(description="True puts the product in the list, False takes it out.")] = True,
) -> WriteResult:
    """[GATED by writes_enabled] Put a product into a collection or wishlist,
    or take it out. Ozon reports no outcome for this, so `detail` names the read
    that confirms it — get_lists(sku).
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
async def get_checkout(
    shipment_items: Annotated[
        bool | None,
        Field(
            description="Force loading each shipment's items on (true) or off (false); default loads them only "
            "when the order is split between prepaid and deferred parts."
        ),
    ] = None,
) -> Checkout:
    """The order being formed from the selected cart items, with everything that
    can be changed: payment methods (each with its payment_type), the
    pay-on-delivery switch, one entry per destination in `deliveries` (each with
    its shipments in split_keys and its selectable pickup_points), the
    `shipments` with their delivery dates, points choices and the money
    breakdown — totals.total is what Ozon charges today (0 ₽ on a fully
    deferred order) and totals.order_total is what the order costs.

    Pay-on-delivery does not always cover the whole order. pay_after_receipt
    .scope is one of "full", "partial" (some items must be paid up front:
    prepayment_amount now, post_payment_amount on receipt) or "none", and .note
    states it in words. On a partial order pay_now_items and pay_on_receipt_items
    name the lines on each side, as Ozon itself splits them, and the `shipments`
    are loaded with their items, each carrying `prepaid` (null when it holds
    items from both sides). shipment_items forces that loading on (true) or off
    (false); by default it happens only when scope is "partial".

    Forms the checkout itself if Ozon has not yet. If it reports
    available=false, `reason` says what to fix — usually: select cart items.
    Change it with configure_checkout, submit with place_order.
    """
    return await run_blocking(lambda: checkout.get_checkout(shipment_items))


@mcp.tool()
async def configure_checkout(
    payment: Annotated[
        str | None,
        Field(
            description='A payment method: a word ("СБП", "Ozon Карта", "новой картой"), a masked card '
            '("**5898") or a payment_type id. Must be one get_checkout() offers.'
        ),
    ] = None,
    points: Annotated[
        int | None,
        Field(ge=0, description="How many Ozon points to spend; 0 spends none. Offered amounts are in points[]."),
    ] = None,
    pay_after_receipt: Annotated[
        bool | None,
        Field(description="Turn «Оплатить после получения» on or off. Only when pay_after_receipt.available."),
    ] = None,
    pickup_point: Annotated[
        str | None,
        Field(
            description='Where to deliver: the point number ("№1449460"), part of its address ("Данилова") or '
            "its address_book_id. Must be one of deliveries[].pickup_points with available=true."
        ),
    ] = None,
    split_key: Annotated[
        str | None,
        Field(
            description="Which shipment to retarget, from deliveries[].split_keys. Only needed when the order "
            "has more than one destination — otherwise the choice is unambiguous."
        ),
    ] = None,
) -> Checkout:
    """Set checkout options and return the recomputed order — one call can set
    several. Omit an argument to leave that option alone.
    Every value comes from a get_checkout() answer, so read that first; passing
    something Ozon does not offer is refused with the list of what it does.
    Applied in the order Ozon recalculates them: destination, payment,
    pay-on-delivery, points. Turning points on can withdraw the pay-on-delivery
    offer, so check the result rather than assuming.
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
async def place_order(
    confirm_total: Annotated[
        str,
        Field(
            description="The total the user agreed to, copied from get_checkout().totals — either order_total "
            '("777 ₽") or total ("0 ₽ сегодня"). Refused if Ozon has recalculated since.'
        ),
    ],
) -> OrderPlaced:
    """[GATED by orders_enabled — SPENDS REAL MONEY] Submit the order that
    get_checkout() describes. Not undoable from here except by cancel_order().
    Read get_checkout() immediately before, show the user totals.order_total —
    what the order costs — and pass back the figure they agreed to. The call is
    refused if that no longer matches, and nothing is ordered.
    Returns once the order actually exists, with its order_number: keep it, it
    is what cancel_order() and pay_order() need. Paying from the Ozon Card
    balance settles with the order; pay-on-delivery leaves nothing to pay today.
    """
    return await run_blocking(lambda: checkout.place_order(confirm_total))


@mcp.tool()
async def pay_order(order: OrderRef) -> PaymentRequested:
    """[GATED] Ask Ozon to charge an order left in «Ожидаем оплаты», and report
    what the user must still do.
    The result spells it out: `amount_due` is the charge, `shortfall` is set when
    the Ozon Card balance does not cover it (top up by that much), and
    `next_step` is the instruction to relay. `payment_url` is where the payment
    is completed — that page signs the account in to Ozon Bank, which is the
    owner's step, so this server never finishes the charge itself.
    Tell the user plainly: top up by `shortfall` if present, then finish at
    `payment_url`. Ordering with pay-on-delivery avoids all of it.
    """
    return await run_blocking(lambda: orders.pay_order(order))


@mcp.tool()
async def list_cancel_reasons(order: OrderRef) -> list[CancelReason]:
    """Reasons Ozon will accept for cancelling an order, with their reason_id.
    The catch-all one (needs_comment=true) is refused without a comment.
    """
    return await run_blocking(lambda: orders.list_cancel_reasons(order))


@mcp.tool()
async def cancel_order(
    order: OrderRef,
    skus: Annotated[
        list[str] | None,
        Field(
            description="Cancel only these lines (skus from order_products()) and leave the rest of the order "
            "standing. Omit to cancel the whole order."
        ),
    ] = None,
    reason_id: Annotated[
        str,
        Field(
            description='A reason_id from list_cancel_reasons(); "504" (изменить заказ и оформить заново) is '
            "the neutral default and needs no comment."
        ),
    ] = "504",
    comment: Annotated[
        str,
        Field(description="Free-text explanation. Required by the catch-all reason (needs_comment=true)."),
    ] = "",
    return_to_cart: Annotated[
        bool,
        Field(description="Put the cancelled items back in the cart, so the order can be recomposed."),
    ] = True,
) -> OrderCancelled:
    """[GATED by writes_enabled] Cancel an order, by default returning its items
    to the cart.
    skus cancels only those lines and leaves the rest of the order standing — an
    order can be cancelled item by item, in as many passes as it has items. Omit
    it to cancel the whole order. The selection is checked against what Ozon
    reports back and refused on a mismatch, since cancelling the wrong line is
    not undoable.
    reason_id from list_cancel_reasons; "504" (изменить заказ и оформить заново)
    is the neutral default, "508" needs a comment.
    Check `cancelled` in the result — Ozon may answer with a retention offer
    instead, and `detail` then carries what it asked.
    """
    return await run_blocking(
        lambda: orders.cancel_order(order, skus, reason_id, comment, return_to_cart=return_to_cart)
    )


# ── session ──────────────────────────────────────────────────────────────────
@mcp.tool()
async def session_status() -> SessionStatus:
    """Start here. Reports whether the stored session still acts as the account
    and what this server is allowed to do: writes_enabled covers cart,
    favorites and lists, orders_enabled covers placing an order. Both are the
    operator's settings and no tool can change them — plan around them.
    When signed_in is false, every other tool raises instead of answering,
    because a signed-out session otherwise looks exactly like an empty account:
    no orders, no balances, no explanation. Recovery is start_login() +
    submit_login_code(), and backup_available=true means it will most likely
    recover by itself on the next call.
    """
    return await run_blocking(session.session_status)


@mcp.tool()
async def start_login(
    login: Annotated[str, Field(description="The account's email or phone, as registered with Ozon.")],
) -> LoginStep:
    """Ask Ozon to send a one-time login code to `login` (account email or
    phone). Use this when session_status() reports signed_in=false and the kept
    profile copy did not recover it.
    Ozon delivers the code out of band (email, SMS or a flash call), so ask the
    user for it and pass it to submit_login_code().
    """
    return await run_blocking(lambda: session.start_login(login))


@mcp.tool()
async def submit_login_code(
    code: Annotated[str, Field(description="The one-time code Ozon sent; digits only, as received.")],
) -> SessionStatus:
    """Finish the login with the code Ozon sent, and keep a copy of the restored
    profile so the next sign-out costs nobody a code.
    Codes expire and are single-use: if it is refused, call start_login() again.
    """
    return await run_blocking(lambda: session.submit_login_code(code))


# ── finance ──────────────────────────────────────────────────────────────────
@mcp.tool()
async def get_finances() -> Finances:
    """Ozon Card balance and the total points. This balance is what a card
    payment draws on, so it is what decides whether pay_order() will need a
    top-up. Breakdown by point type → get_points().
    """
    return await run_blocking(finance.get_finances)


@mcp.tool()
async def get_points() -> Points:
    """Points by type (Ozon points, miles, WOW points, stars) with amounts,
    burning points, and per-store seller bonuses.
    """
    return await run_blocking(finance.get_points)
