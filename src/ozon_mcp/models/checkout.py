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
    apply_link: str | None = None


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
    toggle_link: str | None = None


class TotalRow(OzonModel):
    title: str | None = None
    value: str | None = None


class Totals(OzonModel):
    """The money breakdown.

    ``total`` is what Ozon charges *today*, which is 0 ₽ on a pay-on-delivery
    order — so ``order_total`` carries what the order actually costs. They differ
    whenever payment is deferred or split, and a caller quoting the wrong one
    tells the user the order is free.
    """

    rows: list[TotalRow] = Field(default_factory=list)
    total: str | None = None
    order_total: str | None = None
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


class OrderPlaced(OzonModel):
    """Result of a submitted order, once Ozon has actually created it.

    Paying from the Ozon Card balance settles with the order — no confirmation
    step. ``payment_url`` is the page Ozon names for the payment anyway; it is
    worth passing on when a payment does need finishing (another card, an
    insufficient balance), but its presence alone does not mean the order is
    unpaid.
    """

    order_number: str | None = None
    total: str | None = None
    order_total: str | None = None
    link: str | None = None
    payment_url: str | None = None


class CancelReason(OzonModel):
    """One reason Ozon offers for cancelling.

    ``needs_comment`` marks the catch-all option, which Ozon refuses without a
    free-text explanation.
    """

    reason_id: str
    label: str | None = None
    needs_comment: bool = False


class OrderCancelled(OzonModel):
    """Result of a cancellation, with what Ozon reported back.

    ``skus`` is empty when the whole order was cancelled, and lists the lines
    when only part of it was — an order can be cancelled item by item.
    """

    order_number: str
    cancelled: bool = False
    reason_id: str | None = None
    skus: list[str] = Field(default_factory=list)
    returned_to_cart: bool = False
    detail: str | None = None


class PaymentRequested(OzonModel):
    """Where a card payment stands after asking Ozon to charge it.

    The charge runs on Ozon's bank domain, which signs the account in to the
    bank before it will settle — a credential this server neither holds nor
    should. So the useful answer is not "paid" but exactly what is left to do:
    how much is due, whether the card balance covers it, and where to finish.
    """

    order_number: str
    amount_due: str | None = None
    shortfall: str | None = None
    payment_url: str | None = None
    needs_bank_passcode: bool = False
    next_step: str | None = None
    detail: str | None = None
