"""Collection / wishlist and price-monitoring DTOs."""

from __future__ import annotations

from ozon_mcp.models.base import OzonModel


class ListRef(OzonModel):
    """A collection (подборка) or wishlist (вишлист).

    ``list_id`` is what ``set_list_membership`` and ``delete_list`` need; it
    comes from the link a list card carries, so the lists page supplies it.

    ``contains`` is only set when the lists were read for a particular product,
    and says whether that product is already in the list — which decides whether
    adding it is the right call at all.
    """

    name: str | None = None
    kind: str | None = None
    items: int | None = None
    saves: int | None = None
    list_id: int | None = None
    contains: bool | None = None


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
