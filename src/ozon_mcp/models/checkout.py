"""DTOs for the checkout page."""

from __future__ import annotations

from pydantic import Field

from ozon_mcp.models.base import OzonModel


class PaymentOption(OzonModel):
    """A selectable payment method.

    ``payment_type`` is what ``set_payment_method`` takes. Saved cards share one
    type and are told apart by ``label`` (masked number).
    """

    payment_type: int | None = None
    label: str | None = None
    kind: str | None = None
    selected: bool | None = None


class DeliveryPart(OzonModel):
    """One shipment of a split order."""

    title: str | None = None
    details: str | None = None


class Delivery(OzonModel):
    """One destination of the order.

    An order can be split into several shipments, and Ozon may let each one go
    to its own address — so destinations are a list, and ``split_keys`` says
    which shipments this one covers.
    """

    mode: str | None = None
    address: str | None = None
    storage: str | None = None
    recipient: str | None = None
    split_keys: list[str] = Field(default_factory=list)
    pickup_points: list[PickupPoint] = Field(default_factory=list)
    change_link: str | None = None


class PointsOption(OzonModel):
    """A points-spending choice ("Не списывать" / "Списать N")."""

    label: str | None = None
    amount: int | None = None
    selected: bool = False
    apply_link: str | None = None


class PickupPoint(OzonModel):
    """A saved delivery address / pickup point offered for this order.

    ``available`` is false for points Ozon cannot ship this cart to; those carry
    the reason in ``note`` and cannot be selected.
    """

    address_book_id: str | None = None
    title: str | None = None
    address: str | None = None
    number: str | None = None
    storage: str | None = None
    selected: bool = False
    available: bool = False
    note: str | None = None


class PayAfterReceipt(OzonModel):
    """Ozon's "pay on delivery for part of the order" switch.

    A real toggle, not just a status: ``enabled`` mirrors the checkbox and
    ``set_pay_after_receipt`` flips it. ``prepayment`` is what still has to be
    paid up front when it is on.
    """

    available: bool = False
    enabled: bool = False
    label: str | None = None
    prepayment: str | None = None


class TotalRow(OzonModel):
    title: str | None = None
    value: str | None = None


class Totals(OzonModel):
    rows: list[TotalRow] = Field(default_factory=list)
    total: str | None = None
    note: str | None = None


class Checkout(OzonModel):
    """The whole checkout state, read-only.

    ``pay_after_receipt`` is a switch, not a payment method: Ozon offers it per
    cart and it is flipped with ``set_pay_after_receipt``.
    """

    available: bool = False
    reason: str | None = None
    payment_options: list[PaymentOption] = Field(default_factory=list)
    pay_after_receipt: PayAfterReceipt = Field(default_factory=PayAfterReceipt)
    installment: str | None = None
    deliveries: list[Delivery] = Field(default_factory=list)
    parts: list[DeliveryPart] = Field(default_factory=list)
    points: list[PointsOption] = Field(default_factory=list)
    totals: Totals = Field(default_factory=Totals)
    place_order_action: str | None = None
