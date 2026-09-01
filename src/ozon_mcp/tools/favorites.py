"""Favorites and wishlists (вишлисты)."""

from typing import Annotated

from pydantic import Field

from ozon_mcp.dependencies import run_blocking
from ozon_mcp.mcp_server import mcp
from ozon_mcp.models.catalog import Tile
from ozon_mcp.models.common import WriteResult
from ozon_mcp.models.lists import ListRef, PriceDiff
from ozon_mcp.services import favorites
from ozon_mcp.utils.annotations import Limit, Sku


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
