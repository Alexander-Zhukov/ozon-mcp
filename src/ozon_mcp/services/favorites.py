"""Favorites, collections/wishlists and price-monitoring services.

Endpoints captured live:
- favorite toggle: ``v2/favoriteBatchAddItems`` / ``v2/favoriteBatchDeleteItems``
  with ``{"skus": [<int>]}``;
- list membership: ``v2/favoriteListAdd`` / ``v2/favoriteListRemove`` with
  ``{"skus": [<int>], "id": <listId>}``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ozon_mcp.dependencies import get_session
from ozon_mcp.errors import WritesDisabledError
from ozon_mcp.models.lists import ListRef
from ozon_mcp.parsing import catalog as catalog_parse
from ozon_mcp.parsing.common import PRICE_RE, find_all, widget
from ozon_mcp.parsing.lists import parse_list_page, parse_lists
from ozon_mcp.services import monitoring
from ozon_mcp.settings import get_settings

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


def list_favorites(page: int = 1) -> list[Tile]:
    return catalog_parse.parse_tiles(get_session().fetch(f"/my/favorites?page={page}"))


def check_favorite_price_drops() -> PriceDiff:
    tiles = catalog_parse.parse_tiles(get_session().fetch("/my/favorites"))
    prices = {tile.sku: _price_number(tile.price) or 0 for tile in tiles if tile.sku}
    titles = {tile.sku: tile.title or "" for tile in tiles if tile.sku}
    return monitoring.record(prices, titles)


def get_lists(sku: str | None = None) -> list[ListRef]:
    """Collections and wishlists in one answer.

    Without ``sku`` this is the lists page: names, kinds and counts. With a
    ``sku`` it is the membership modal for that product, which is the only place
    Ozon exposes list **ids** — and an id is what changing membership needs.
    """
    session = get_session()
    if sku is None:
        page = session.fetch(_LISTS_PATH)
        collections = [ref.model_copy(update={"kind": "collection"}) for ref in parse_list_page(page, wishlists=False)]
        wishlists = [ref.model_copy(update={"kind": "wishlist"}) for ref in parse_list_page(page, wishlists=True)]
        return collections + wishlists
    sku_match = re.search(r"(\d{6,})", str(sku))
    identifier = sku_match.group(1) if sku_match else sku
    entries = parse_lists(session.fetch(f"/modal/favoritesListsSelect?sku={identifier}", backend="entrypoint"))
    return [ListRef(name=entry.name, list_id=entry.id) for entry in entries]


def set_list_membership(sku: str, list_id: int, *, add: bool = True) -> dict[str, Any]:
    """Put a product into a collection/wishlist, or take it out."""
    _require_writes()
    path = "v2/favoriteListAdd" if add else "v2/favoriteListRemove"
    return get_session().action(path, {"skus": [int(sku)], "id": int(list_id)})


def list_returns() -> dict[str, list[str]]:
    state = widget(get_session().fetch("/my/returns"), "returnList") or {}
    titles = [t for t in find_all(state, "title") if isinstance(t, str)]
    return {"entries": list(dict.fromkeys(titles))[:30], "prices": PRICE_RE.findall(str(state))}


def set_favorite(sku: str, *, add: bool = True) -> dict[str, Any]:
    _require_writes()
    path = "v2/favoriteBatchAddItems" if add else "v2/favoriteBatchDeleteItems"
    return get_session().action(path, {"skus": [int(sku)]})
