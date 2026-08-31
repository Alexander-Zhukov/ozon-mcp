"""Collection / wishlist and price-monitoring DTOs."""

from __future__ import annotations

from ozon_mcp.models.base import OzonModel


class ListRef(OzonModel):
    """A collection (подборка) or wishlist (вишлист): name + item count."""

    name: str | None = None
    items: int | None = None
    saves: int | None = None


class ListId(OzonModel):
    """A list identified by id, for add_to_list / remove_from_list."""

    id: int
    name: str | None = None


class PriceChange(OzonModel):
    sku: str
    title: str | None = None
    was: int
    now: int
    delta: int


class PriceDiff(OzonModel):
    drops: list[PriceChange] = []
    rises: list[PriceChange] = []
    added: list[str] = []
    removed: list[str] = []
