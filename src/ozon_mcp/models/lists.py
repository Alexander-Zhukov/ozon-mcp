"""Collection / wishlist and price-monitoring DTOs."""

from pydantic import Field

from ozon_mcp.models.base import OzonModel
from ozon_mcp.models.enums import ListKind


class ListRef(OzonModel):
    """A collection (подборка) or wishlist (вишлист).

    ``list_id`` is what ``set_list_membership`` and ``delete_list`` need; it
    comes from the link a list card carries, so the lists page supplies it.

    ``contains`` is only set when the lists were read for a particular product,
    and says whether that product is already in the list — which decides whether
    adding it is the right call at all.
    """

    name: str | None = None
    kind: ListKind | None = None
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
    drops: list[PriceChange] = Field(default_factory=list)
    rises: list[PriceChange] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)


class Selection(OzonModel):
    """One «Подборка» — a curated list of products, publishable to a profile.

    A different entity from a wishlist: identified by a ``uuid`` rather than a
    numeric id, it carries a cover, a description and a visibility, and reading
    it needs ``owner_id`` alongside the uuid.

    ``status`` is Ozon's own wording for where the selection stands — "Личная
    подборка" while it is private, "N сохранений" once public, "На модерации"
    while it is being reviewed — because publishing is not instant. It is not a
    substitute for ``public``: a selection under review reads "На модерации"
    whichever way its visibility is set, so the two are reported separately.

    ``description`` and ``public`` are only known when the selection is read on
    its own (``get_selection``); listing them all does not carry either.
    """

    uuid: str
    owner_id: str | None = None
    name: str | None = None
    description: str | None = None
    items: int | None = None
    status: str | None = None
    public: bool | None = None
    cover: str | None = None
    link: str | None = None
