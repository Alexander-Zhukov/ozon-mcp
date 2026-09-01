"""Favorites, collections/wishlists and price-monitoring services.

Endpoints captured live:
- favorite toggle: ``v2/favoriteBatchAddItems`` / ``v2/favoriteBatchDeleteItems``
  with ``{"skus": [<int>]}``;
- list membership: ``v2/favoriteListAdd`` / ``v2/favoriteListRemove`` with
  ``{"skus": [<int>], "id": <listId>}``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ozon_mcp.dependencies import get_session
from ozon_mcp.errors import OzonError, WritesDisabledError
from ozon_mcp.models.common import WriteResult
from ozon_mcp.models.lists import ListRef
from ozon_mcp.parsing import catalog as catalog_parse
from ozon_mcp.parsing.common import find_all
from ozon_mcp.parsing.lists import parse_list_membership, parse_wishlists
from ozon_mcp.services import monitoring
from ozon_mcp.settings import get_settings

# Ozon reports neither success nor refusal for these actions, so the honest
# answer names the read that settles it rather than claiming an outcome.
_ACCEPTED = "Ozon accepted the change and reports no outcome for it; confirm with {check} if it matters"
_CREATE_LIST_ACTION = "favoriteCreateList"
_DELETE_LIST_ACTION = "favoriteDeleteList"

if TYPE_CHECKING:
    from ozon_mcp.models.catalog import Tile
    from ozon_mcp.models.lists import PriceDiff

_LISTS_PATH = "/my/favorites/lists"


def _price_number(price: str | None) -> int | None:
    digits = re.sub(r"\D", "", price or "")
    return int(digits) if digits else None


def _require_writes() -> None:
    if not get_settings().enable_writes:
        raise WritesDisabledError


def list_favorites(limit: int = 100) -> list[Tile]:
    """Favorites, following the scroll pagination.

    The page number is not a parameter here: asking for ``?page=1`` makes Ozon
    return the page *without* its product grid, so the first page has to be
    requested bare and the rest followed through the embedded cursor.
    """
    from ozon_mcp.services.catalog import _paginate_tiles  # ruff: ignore[import-outside-top-level] - avoids a cycle

    return _paginate_tiles("/my/favorites", limit, counter="favoriteCounter")


def check_favorite_price_drops() -> PriceDiff:
    tiles = catalog_parse.parse_tiles(get_session().fetch("/my/favorites"))
    prices = {tile.sku: _price_number(tile.price) or 0 for tile in tiles if tile.sku}
    titles = {tile.sku: tile.title or "" for tile in tiles if tile.sku}
    return monitoring.record(prices, titles)


def get_lists(sku: str | None = None) -> list[ListRef]:
    """The account's wishlists, with their ids and sizes.

    The wishlists page is always the source of the list itself, because it is
    the one place that names every list with its id — the membership modal drops
    the id of any list the product is already in. With a ``sku`` the modal is
    read as well, for the one thing it does know: which lists hold that product.

    Ozon's «Подборки» are a different entity, kept on ``/selections/list`` and
    not created by these actions; they are deliberately not mixed in here.
    """
    session = get_session()
    lists = parse_wishlists(session.fetch(_LISTS_PATH))
    if sku is None:
        return lists
    sku_match = re.search(r"(\d{6,})", str(sku))
    identifier = sku_match.group(1) if sku_match else sku
    modal = session.fetch(f"/modal/favoritesListsSelect?sku={identifier}", backend="entrypoint")
    membership = parse_list_membership(modal)
    return [ref.model_copy(update={"contains": membership.get(ref.name or "")}) for ref in lists]


def create_list(name: str) -> ListRef:
    """Create an empty wishlist and return it with its id.

    Only wishlists: the action takes an ``isWishlist`` flag, but passing false
    creates a wishlist all the same — «Подборки» are made elsewhere — so the
    flag is not offered rather than promising a kind Ozon will not produce.

    Ozon does report a refusal here — an empty name comes back as «Пустое
    название вишлиста» — so a failure raises instead of returning a list that
    does not exist.
    """
    _require_writes()
    response = get_session().action(_CREATE_LIST_ACTION, {"title": name, "isWishlist": True})
    complaint = response.get("errorForUser") or response.get("error") if isinstance(response, dict) else None
    if complaint or not isinstance(response, dict) or not response.get("id"):
        msg = f"Ozon refused to create the list: {complaint or 'no id came back'}"
        raise OzonError(msg)
    return ListRef(name=str(response.get("title") or name), kind="wishlist", items=0, list_id=int(response["id"]))


def delete_list(list_id: int) -> WriteResult:
    """Delete a wishlist. The products in it are not deleted.

    Ozon confirms this one in words ("Вишлист удалён из избранного"), so its own
    wording is passed back rather than an assumption.
    """
    _require_writes()
    response = get_session().action(_DELETE_LIST_ACTION, {"ids": [int(list_id)]})
    complaint = response.get("errorForUser") or response.get("error") if isinstance(response, dict) else None
    if complaint:
        return WriteResult(ok=False, detail=str(complaint))
    said = [text for text in find_all(response, "title") if isinstance(text, str) and text.strip()]
    return WriteResult(detail=said[0] if said else None)


def set_list_membership(sku: str, list_id: int, *, add: bool = True) -> WriteResult:
    """Put a product into a collection/wishlist, or take it out."""
    _require_writes()
    path = "v2/favoriteListAdd" if add else "v2/favoriteListRemove"
    get_session().action(path, {"skus": [int(sku)], "id": int(list_id)})
    return WriteResult(detail=_ACCEPTED.format(check="get_lists(sku)"))


def set_favorite(sku: str, *, add: bool = True) -> WriteResult:
    _require_writes()
    path = "v2/favoriteBatchAddItems" if add else "v2/favoriteBatchDeleteItems"
    get_session().action(path, {"skus": [int(sku)]})
    return WriteResult(detail=_ACCEPTED.format(check="list_favorites()"))
