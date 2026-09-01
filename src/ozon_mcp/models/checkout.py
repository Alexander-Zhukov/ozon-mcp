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


class ShipmentItem(OzonModel):
    """One line of a shipment, as the shipment's own detail view states it."""

    title: str | None = None
    variant: str | None = None
    price: str | None = None
    quantity: str | None = None
    seller: str | None = None


class Shipment(OzonModel):
    """One shipment of a split order, and whether it has to be paid up front.

    Ozon splits an order into shipments and decides pay-on-delivery per
    shipment, but it never says which shipment the prepayment belongs to — only
    the total. ``prepaid`` is therefore derived by matching that total against
    the shipments' own sums: True/False once one combination accounts for it,
    and None when the amounts leave it ambiguous. None means "Ozon did not say
    and the arithmetic does not settle it", never "no prepayment".
    """

    split_key: str | None = None
    delivery: str | None = None
    summary: str | None = None
    total: str | None = None
    items: list[ShipmentItem] = Field(default_factory=list)
    prepaid: bool | None = None


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

    ``available`` is false for points Ozon cannot ship this cart to, and those
    cannot be selected. ``note`` is whatever Ozon says about the address for
    this cart — the reason when it will not ship there, a confirmation when it
    will.
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
    """Ozon's pay-on-delivery switch, and how much of the order it covers.

    A real toggle, not just a status: ``enabled`` mirrors the checkbox and
    ``configure_checkout`` flips it. It does not always cover everything — some
    items (imports, long-delivery FBS lines) have to be paid up front, and then
    Ozon offers the switch for the rest of the order only. ``scope`` says which
    case this is:

    - ``full`` — the whole order can be paid on delivery
    - ``partial`` — only part of it; ``prepayment_amount`` is charged now, and
      the two item lists say exactly which lines fall on which side
    - ``none`` — Ozon does not offer pay-on-delivery for this order at all

    The amounts are what is charged when the switch is on, so they are stated
    only then; with it off the whole order is prepaid by definition.
    """

    available: bool = False
    enabled: bool = False
    scope: str = "none"
    label: str | None = None
    prepayment: str | None = None
    prepayment_amount: str | None = None
    post_payment_amount: str | None = None
    pay_now_items: list[ShipmentItem] = Field(default_factory=list)
    pay_on_receipt_items: list[ShipmentItem] = Field(default_factory=list)
    note: str | None = None
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
    shipments: list[Shipment] = Field(default_factory=list)
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
