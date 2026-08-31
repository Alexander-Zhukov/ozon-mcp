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
from ozon_mcp.models.lists import ListId, ListRef, PriceDiff
from ozon_mcp.parsing import catalog as catalog_parse
from ozon_mcp.parsing.common import PRICE_RE, find_all, widget
from ozon_mcp.parsing.lists import parse_lists
from ozon_mcp.services import monitoring
from ozon_mcp.settings import get_settings

if TYPE_CHECKING:
    from ozon_mcp.models.catalog import Tile

# Collection cards render "<name> N товар(а)"; wishlists "<name> N подарков".
_CARDS_JS = r"""() => {
  const text = (document.body.innerText || '').replace(/\r/g, '');
  const re = /([^\n]{2,40}?)\s+(\d+)\s+(товар\w*|подарк\w*)/g;
  const out = []; const seen = new Set(); let m;
  while ((m = re.exec(text))) {
    const name = m[1].trim();
    if (/^(Избранное|Подборки|Вишлисты|Магазины|Создать|Новый|Мои|Товары за)/i.test(name)) continue;
    if (seen.has(name)) continue; seen.add(name);
    out.push({name, items: +m[2]});
  }
  return out;
}"""


def _price_number(price: str | None) -> int | None:
    digits = re.sub(r"\D", "", price or "")
    return int(digits) if digits else None


def _require_writes() -> None:
    if not get_settings().enable_writes:
        raise WritesDisabledError


def list_favorites(page: int = 1) -> list[Tile]:
    return catalog_parse.parse_tiles(get_session().fetch(f"/my/favorites?page={page}"))


def favorites_price_snapshot() -> dict[str, int | None]:
    tiles = catalog_parse.parse_tiles(get_session().fetch("/my/favorites"))
    return {tile.sku: _price_number(tile.price) for tile in tiles if tile.sku}


def check_favorite_price_drops() -> PriceDiff:
    tiles = catalog_parse.parse_tiles(get_session().fetch("/my/favorites"))
    prices = {tile.sku: _price_number(tile.price) or 0 for tile in tiles if tile.sku}
    titles = {tile.sku: tile.title or "" for tile in tiles if tile.sku}
    return monitoring.record(prices, titles)


def list_collections() -> list[ListRef]:
    raw = get_session().nav_click_extract("/my/favorites", "Подборк", _CARDS_JS)
    return [ListRef.model_validate(item) for item in raw or []]


def list_wishlists() -> list[ListRef]:
    raw = get_session().nav_click_extract("/my/favorites", "Вишлист", _CARDS_JS)
    return [ListRef.model_validate(item) for item in raw or []]


def get_lists(sku: str) -> list[ListId]:
    sku_match = re.search(r"(\d{6,})", str(sku))
    identifier = sku_match.group(1) if sku_match else sku
    return parse_lists(get_session().fetch(f"/modal/favoritesListsSelect?sku={identifier}", backend="entrypoint"))


def list_returns() -> dict[str, list[str]]:
    state = widget(get_session().fetch("/my/returns"), "returnList") or {}
    titles = [t for t in find_all(state, "title") if isinstance(t, str)]
    return {"entries": list(dict.fromkeys(titles))[:30], "prices": PRICE_RE.findall(str(state))}


def set_favorite(sku: str, *, add: bool = True) -> dict[str, Any]:
    _require_writes()
    path = "v2/favoriteBatchAddItems" if add else "v2/favoriteBatchDeleteItems"
    return get_session().action(path, {"skus": [int(sku)]})


def add_to_list(sku: str, list_id: int) -> dict[str, Any]:
    _require_writes()
    return get_session().action("v2/favoriteListAdd", {"skus": [int(sku)], "id": int(list_id)})


def remove_from_list(sku: str, list_id: int) -> dict[str, Any]:
    _require_writes()
    return get_session().action("v2/favoriteListRemove", {"skus": [int(sku)], "id": int(list_id)})
