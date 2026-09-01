"""Orders, purchases and returns — what was bought and where it is."""

from typing import Annotated

from pydantic import Field

from ozon_mcp.dependencies import run_blocking
from ozon_mcp.mcp_server import mcp
from ozon_mcp.models.catalog import Tile
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
async def list_returns(limit: Limit = 100) -> list[Return]:
    """Returns this account has opened, newest first: the return number, the
    date of the application, Ozon's own status badge ("Деньги отправлены", "Ждём
    товар") and the sentence under it, the amount, and the products going back.
    Paginated through — `limit` caps how many come back.
    """
    return await run_blocking(lambda: orders.list_returns(limit))
