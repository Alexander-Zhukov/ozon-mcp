"""Collection / wishlist and price-monitoring DTOs."""

from __future__ import annotations

from ozon_mcp.models.base import OzonModel


class ListRef(OzonModel):
    """A collection (подборка) or wishlist (вишлист).

    ``list_id`` is only known when the list is read in the context of a product,
    because Ozon exposes ids on the membership modal rather than the lists page;
    it is what ``set_list_membership`` needs.
    """

    name: str | None = None
    kind: str | None = None
    items: int | None = None
    saves: int | None = None
    list_id: int | None = None


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
