"""Orders, purchases and returns — what was bought and where it is."""

from typing import Annotated

from pydantic import Field

from ozon_mcp.dependencies import run_blocking
from ozon_mcp.mcp_server import mcp
from ozon_mcp.models.catalog import BoughtItems, Purchase
from ozon_mcp.models.orders import Order, OrderProduct, Return
from ozon_mcp.services import catalog, orders
from ozon_mcp.utils.annotations import IsoDate, Limit, OrderRef, OrderScope, PurchaseSort


@mcp.tool()
async def list_orders(
    scope: OrderScope = "active",
    limit: Limit = 100,
    date_from: IsoDate | None = None,
    date_to: IsoDate | None = None,
) -> list[Order]:
    """Orders with status, state (active/received/cancelled), pickup point,
    delivery slot/ETA and their items.
    No order total: Ozon states none on the list. Money is amount_due_at_pickup
    («К оплате при получении», what is owed on collection) per entry, and price
    plus paid true/false per item. An item's price is not the order's; paid null
    means unknown, not unpaid.
    An entry is a delivery group: items arriving together share it, so
    order_numbers can hold several and its items can be paid and unpaid.
    Giving either date searches the «Завершённые» archive by walking down to the
    window: limit counts the orders inside it, and paging stops once a page is
    wholly older. The cost is the depth, not the width — a recent fortnight comes
    back in under a second, a month two years back takes tens of seconds. The
    dates are status dates (received / cancelled), the only ones the archive
    prints, so an order placed on 30 June and received on 2 July lands in July.
    Pass an entry's order number or detail_link on to order_products(),
    cancel_order() or pay_order().
    """
    return await run_blocking(lambda: orders.list_orders(scope, limit, date_from, date_to))


@mcp.tool()
async def order_products(order: OrderRef) -> list[OrderProduct]:
    """Items of one order: sku, title, price paid, chosen variant, seller, a
    product-card link — and the outcome of the parcel each item travelled in.
    An order is delivered in parcels with separate fates: refusing an item at the
    pickup point cancels its parcel while the rest of the order is received, so
    `shipment_status` («Получен» / «Отменён») and `received` are per item, not per
    order. This is the only place that says what was actually taken home.
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
) -> list[Purchase]:
    """Everything ever **ordered**, as product tiles (sku/title/price/url) — the
    answer to "have I bought this before" and "buy that thing again".
    This is Ozon's «Купленные товары» list, and it is a list of products, not of
    outcomes: it includes items refused at the pickup point, and it states no
    status, no order and no purchase date. So it does not answer "did I actually
    get this" — do not read it as "bought".
    For "did I actually get this" use bought_items(), which matches the list
    against the orders.
    `price` is today's catalogue price, not what was paid; the price paid is in
    order_products().
    With `query` Ozon searches its own purchase history server-side, which is
    much cheaper than paging through all of it.
    """
    return await run_blocking(lambda: catalog.purchases(query, limit, sort))


@mcp.tool()
async def bought_items(
    query: Annotated[
        str | None,
        Field(description="Text to look for in the purchase history; omit to take it in order, newest first."),
    ] = None,
    skus: Annotated[
        list[str] | None,
        Field(
            description="Ask about these products only — the `unresolved` of a previous answer. Skips the purchase "
            "index, so it is the cheap way to keep looking further back."
        ),
    ] = None,
    limit: Limit = 100,
    scan_orders: Annotated[
        int,
        Field(
            ge=1,
            le=1000,
            description="How many orders to open, newest first. Each is a request, so this is the cost: 50 orders "
            "take roughly fifteen seconds, the whole archive minutes.",
        ),
    ] = 50,
    scan_before: IsoDate | None = None,
) -> BoughtItems:
    """What was actually received, not merely ordered — the honest answer to
    "have I bought this".
    Matches Ozon's purchase list (its only text index over the whole history)
    against the orders, where the outcome lives: per item `received` true when a
    parcel with it was «Получен», false when every one was «Отменён», null when
    it was not found in the orders scanned.
    The answer says how far it looked — `scanned_orders`, `scanned_back_to`,
    `complete` and the `unresolved` skus. It is bounded because each order costs
    a request and a full sweep of an old account takes minutes.
    «Отменён» is not the end of it: `provisional` lists items seen only as
    cancelled, because an older order may have been received — carry them on with
    `unresolved` when you continue.
    To keep looking, call again with skus=<unresolved + provisional> and
    scan_before=<scanned_back_to>, then merge by sku, preferring received. Do not
    simply raise scan_orders: that re-reads what was already covered. And do not
    repeat the query with scan_before alone — the items it already placed live in
    newer orders, so they would come back unresolved.
    Budget: with a query the first call takes about 40 s (the purchase index
    alone is ~20 s) and each continuation of 150 orders about 30 s. If your
    client's timeout is shorter, call purchases() for the skus first and then
    bought_items(skus=…) in chunks.
    Never report an unresolved sku as "not bought": it means nobody looked that
    far back.
    """
    return await run_blocking(lambda: catalog.bought_items(query, skus, limit, scan_orders, scan_before))


@mcp.tool()
async def list_returns(limit: Limit = 100) -> list[Return]:
    """Returns this account has opened, newest first: the return number, the
    date of the application, Ozon's own status badge ("Деньги отправлены", "Ждём
    товар") and the sentence under it, the amount, and the products going back.
    Paginated through — `limit` caps how many come back.
    """
    return await run_blocking(lambda: orders.list_returns(limit))
