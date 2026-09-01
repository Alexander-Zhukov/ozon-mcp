"""Order DTOs."""

from pydantic import Field

from ozon_mcp.models.base import OzonModel


class OrderThumbnail(OzonModel):
    """A product thumbnail on an order row + its order-detail link."""

    photo: str | None = None
    detail_link: str | None = None


class Order(OzonModel):
    """One order as the order list shows it.

    ``order_number`` is what every other order tool takes — cancelling, paying,
    listing reasons. Ozon does not print it on the row: it is encoded in the
    row's link, so it is decoded here rather than left for the caller to dig
    out. An order split across parcels has one number per parcel, and
    ``order_numbers`` holds them all.
    """

    order_number: str | None = Field(
        default=None, description='The number every other order tool takes, e.g. "44563249-0877".'
    )
    order_numbers: list[str] = Field(
        default_factory=list, description="Every order in this row; a delivery group carries more than one."
    )
    pickup: str | None = None
    slot: str | None = None
    delivery_eta: str | None = None
    status: str | None = Field(default=None, description='Ozon\'s own words: "В пути", "Можно забирать", "Отменён".')
    date: str | None = Field(default=None, description="Purchase date as YYYY-MM-DD, for completed orders.")
    total: str | None = Field(default=None, description="What the order cost, as Ozon renders it.")
    items_count: int = 0
    products: list[OrderThumbnail] = Field(default_factory=list)
    detail_link: str | None = None
    order_ids: list[int] = Field(default_factory=list)


class OrderProduct(OzonModel):
    """A product as it appears in an order."""

    sku: str
    title: str | None = None
    price: str | None = None
    variant: str | None = None
    seller: str | None = None
    url: str | None = None


class ReturnProduct(OzonModel):
    """A product being returned."""

    sku: str | None = None
    title: str | None = None


class Return(OzonModel):
    """One buyer return.

    ``status`` is Ozon's own badge — "Деньги отправлены", "Ждём товар" — and
    ``detail`` the sentence under it, which is where a refund says where the
    money went. ``number`` is what the return is addressed by.
    """

    number: str | None = None
    title: str | None = None
    date: str | None = None
    status: str | None = None
    detail: str | None = None
    amount: str | None = None
    products: list[ReturnProduct] = Field(default_factory=list)
    link: str | None = None
