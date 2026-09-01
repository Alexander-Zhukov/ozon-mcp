"""Catalog DTOs: search tiles, product cards, reviews, facets."""

from pydantic import Field

from ozon_mcp.models.base import OzonModel


class Tile(OzonModel):
    """A product tile as shown in search / favorites / purchases grids."""

    sku: str | None = None
    title: str | None = None
    price: str | None = None
    price_old: str | None = None
    url: str | None = None


class VariantOption(OzonModel):
    """One value of a product aspect — itself a purchasable SKU."""

    sku: str | None = None
    label: str | None = None
    price: int | None = None
    availability: str | None = None
    link: str | None = None


class Variant(OzonModel):
    """A product aspect (e.g. Цвет / Размер) and its options."""

    name: str
    options: list[VariantOption] = Field(default_factory=list)


class Characteristic(OzonModel):
    name: str
    value: str = ""


class Review(OzonModel):
    author: str | None = None
    score: int | None = None
    text: str | None = None
    date: int | None = None
    photos: list[str] = Field(default_factory=list)


class Reviews(OzonModel):
    score: list[str] = Field(default_factory=list)
    count: int = 0
    photos: list[str] = Field(default_factory=list)
    reviews: list[Review] = Field(default_factory=list)


class ProductCard(OzonModel):
    """Everything on a product card.

    ``description`` and ``reviews`` come from separate endpoints and are filled
    only when asked for, so the common case stays one cheap request.
    """

    title: str | None = None
    sku: str | None = None
    price: str | None = None
    price_list: list[str] = Field(default_factory=list)
    variants: list[Variant] = Field(default_factory=list)
    characteristics: list[Characteristic] = Field(default_factory=list)
    photos: list[str] = Field(default_factory=list)
    description: str | None = None
    description_images: list[str] = Field(default_factory=list)
    reviews: Reviews | None = None


class Description(OzonModel):
    sku: str
    description: str | None = None
    images: list[str] = Field(default_factory=list)


class FilterOption(OzonModel):
    label: str | None = None
    value: str | None = None
    selected: bool | None = None
    category_link: str | None = None


class SearchFilter(OzonModel):
    """A facet group and how to apply it via ``search(filters=...)``."""

    name: str | None = None
    key: str | None = None
    type: str | None = None
    options: list[FilterOption] = Field(default_factory=list)
    range: list[int | None] | None = None


class Cheaper(OzonModel):
    base: dict[str, str | None]
    cheaper: list[Tile] = Field(default_factory=list)


class DeliveryEstimate(OzonModel):
    """When a product would arrive, and what that estimate is relative to.

    The date means nothing without the address it was computed for, so both are
    returned together; ``source`` is the warehouse Ozon would ship it from.
    """

    sku: str
    delivery: str | None = None
    address: str | None = None
    source: str | None = None
