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
from ozon_mcp.models.common import WriteResult
from ozon_mcp.models.lists import ListRef
from ozon_mcp.models.orders import Return
from ozon_mcp.parsing import catalog as catalog_parse
from ozon_mcp.parsing.common import walk, widget
from ozon_mcp.parsing.lists import parse_list_page, parse_lists
from ozon_mcp.services import monitoring
from ozon_mcp.settings import get_settings

# Every return card links to the return it stands for.
_RETURN_LINK = "/my/returns/"
# Ozon reports neither success nor refusal for these actions, so the honest
# answer names the read that settles it rather than claiming an outcome.
_ACCEPTED = "Ozon accepted the change and reports no outcome for it; confirm with {check} if it matters"

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

    return _paginate_tiles("/my/favorites", limit)


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


def set_list_membership(sku: str, list_id: int, *, add: bool = True) -> WriteResult:
    """Put a product into a collection/wishlist, or take it out."""
    _require_writes()
    path = "v2/favoriteListAdd" if add else "v2/favoriteListRemove"
    get_session().action(path, {"skus": [int(sku)], "id": int(list_id)})
    return WriteResult(detail=_ACCEPTED.format(check="get_lists(sku)"))


def list_returns() -> list[Return]:
    """Buyer returns, read from the cards that link to a return.

    The page also carries a FAQ accordion, and taking every title on it — which
    is what this did — reported «Почему товар недоступен для возврата?» to the
    caller as though it were a return. A card is identified by linking to a
    return, so an account with none answers with none.
    """
    state = widget(get_session().fetch("/my/returns"), "returnList") or {}
    out: list[Return] = []
    for node in walk(state):
        link = str(((node.get("action") or {}) if isinstance(node.get("action"), dict) else {}).get("link") or "")
        if _RETURN_LINK not in link:
            continue
        center: dict[str, Any] = node.get("centerBlock") or {}
        out.append(
            Return(
                title=_atom(center.get("title")) if isinstance(center, dict) else None,
                status=_atom(center.get("subtitle")) if isinstance(center, dict) else None,
                link=link,
            )
        )
    return out


def _atom(node: Any) -> str | None:
    if isinstance(node, str):
        return str(node).strip() or None
    if isinstance(node, dict):
        text = node.get("text")
        if isinstance(text, str):
            return str(text).strip() or None
    return None


def set_favorite(sku: str, *, add: bool = True) -> WriteResult:
    _require_writes()
    path = "v2/favoriteBatchAddItems" if add else "v2/favoriteBatchDeleteItems"
    get_session().action(path, {"skus": [int(sku)]})
    return WriteResult(detail=_ACCEPTED.format(check="list_favorites()"))
