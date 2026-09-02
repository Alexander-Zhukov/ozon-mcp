"""Catalog DTOs: search tiles, product cards, reviews, facets."""

from pydantic import Field

from ozon_mcp.models.base import OzonModel


class Tile(OzonModel):
    """A product tile as shown in search / favorites / purchases grids."""

    sku: str | None = None
    title: str | None = None
    price: str | None = Field(
        default=None, description="What this lot costs to pay — Ozon's «С банками» price when it prints one."
    )
    price_regular: str | None = Field(default=None, description="Ozon's «С другими банками» price, when it differs.")
    price_old: str | None = Field(default=None, description="The struck-through price Ozon compares against.")
    url: str | None = None
    seller: str | None = Field(default=None, description="Set on offers from other sellers, which carry no title.")
    delivery: str | None = Field(default=None, description='Ozon\'s own line, e.g. "Доставим 9 сентября".')


class Purchase(Tile):
    """A product from «Купленные товары», with what the orders say about it.

    Ozon's own list is a list of products, not of outcomes: it holds everything
    that was ever ordered, including what was refused at the pickup point, and
    it states no status at all. So the status is taken from the orders, and
    ``received`` is None when the item was not found among the orders scanned —
    which is not the same as "not received".
    """

    order_number: str | None = None
    order_status: str | None = Field(
        default=None, description='Ozon\'s word for the parcel this item came in: "Получен", "Отменён".'
    )
    received: bool | None = Field(
        default=None,
        description="True if a parcel with it was received, False if every one was cancelled, None if not found.",
    )


class BoughtItems(OzonModel):
    """What the orders say was bought, and how far the answer looked.

    The coverage is part of the answer on purpose: the archive is a newest-first
    cursor and each order costs a request, so any bounded scan is partial. Left
    unsaid, "nothing older found" is indistinguishable from "did not look that
    far" — which is exactly how 29 items became "all bought".
    """

    items: list[Purchase] = Field(default_factory=list)
    scanned_orders: int = Field(default=0, description="How many orders were opened for this answer.")
    scanned_back_to: str | None = Field(
        default=None, description="Status date of the oldest order scanned; everything older was not looked at."
    )
    complete: bool = Field(
        default=False,
        description="True when every item is settled — found received, or the scan reached the end of the archive.",
    )
    unresolved: list[str] = Field(
        default_factory=list, description="Skus not found in any order scanned — nobody looked far enough back."
    )
    provisional: list[str] = Field(
        default_factory=list,
        description=(
            "Skus seen only as «Отменён» so far. Not an answer to «did I ever get it»: an earlier order may have "
            "been received, so keep looking with these too."
        ),
    )


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
    price: str | None = Field(
        default=None, description="The payable price — Ozon's «С банками» figure, which is what the account pays."
    )
    price_regular: str | None = Field(default=None, description="Ozon's «С другими банками» price.")
    price_old: str | None = Field(default=None, description="The struck-through price Ozon compares against.")
    available: bool | None = Field(default=None, description="Whether Ozon offers it for sale at all.")
    cheaper_offers: int | None = Field(
        default=None,
        description="How many other-seller offers Ozon counts for this product; find_cheaper() lists them.",
    )
    cheaper_from: str | None = Field(
        default=None, description="Ozon's own «от N ₽» for those offers — the lowest it knows about."
    )
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
