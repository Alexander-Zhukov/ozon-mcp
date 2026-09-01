"""Order DTOs."""

from pydantic import Field

from ozon_mcp.models.base import OzonModel
from ozon_mcp.models.enums import OrderState


class OrderLine(OzonModel):
    """One item on an order row.

    Payment state belongs here rather than on the row: Ozon marks each item
    «Оплачен» or «Не оплачен» separately, and a row can hold both.
    """

    photo: str | None = None
    detail_link: str | None = None
    order_number: str | None = Field(
        default=None, description="Which order this item belongs to; a row can mix several."
    )
    paid: bool | None = Field(
        default=None, description="Whether this item is already paid for. None means Ozon did not say."
    )
    payment_status: str | None = Field(default=None, description='Ozon\'s own badge: "Оплачен" / "Не оплачен".')
    price: str | None = Field(default=None, description="This item's price as Ozon renders it, not the order total.")
    quantity: str | None = Field(default=None, description='How many, when more than one — Ozon\'s wording, "2 шт".')
    stored_until: str | None = Field(
        default=None, description="Last day the pickup point holds it, YYYY-MM-DD, for orders awaiting pickup."
    )


class Order(OzonModel):
    """One order row as the order list shows it.

    A row is a delivery group, not a single order: items arriving together share
    one, so ``order_numbers`` can hold several. There is no order total — Ozon
    renders none here; the money is ``amount_due_at_pickup`` per group and a
    price per item.

    ``order_number`` is what every other order tool takes. Ozon does not print it
    on the row, so it is decoded from the row's links.
    """

    order_number: str | None = Field(
        default=None, description='The number every other order tool takes, e.g. "44563249-0877".'
    )
    order_numbers: list[str] = Field(
        default_factory=list, description="Every order in this row; a delivery group carries more than one."
    )
    state: OrderState = Field(
        default=OrderState.ACTIVE, description="active / received / cancelled, read from Ozon's status word."
    )
    pickup: str | None = None
    slot: str | None = None
    delivery_eta: str | None = None
    status: str | None = Field(default=None, description='Ozon\'s own words: "В пути", "Можно забирать", "Отменён".')
    date: str | None = Field(
        default=None,
        description="The date in the status as YYYY-MM-DD — when it was received or cancelled, not when it was bought.",
    )
    amount_due_at_pickup: str | None = Field(
        default=None,
        description=(
            "«К оплате при получении» for this group, as Ozon renders it — what is still owed on collection. "
            "Absent when nothing is owed."
        ),
    )
    items_count: int = Field(default=0, description="How many items the row shows.")
    products: list[OrderLine] = Field(default_factory=list)
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
