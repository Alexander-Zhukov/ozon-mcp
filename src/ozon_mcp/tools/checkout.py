"""Forming, paying, submitting and cancelling an order."""

from typing import Annotated

from pydantic import Field

from ozon_mcp.dependencies import run_blocking
from ozon_mcp.mcp_server import mcp
from ozon_mcp.models.checkout import CancelReason, Checkout, OrderCancelled, OrderPlaced, PaymentRequested
from ozon_mcp.services import checkout, orders
from ozon_mcp.utils.annotations import OrderRef


@mcp.tool()
async def get_checkout(
    shipment_items: Annotated[
        bool | None,
        Field(
            description="Force loading each shipment's items on (true) or off (false); default loads them only "
            "when the order is split between prepaid and deferred parts."
        ),
    ] = None,
) -> Checkout:
    """The order being formed from the selected cart items, with everything that
    can be changed: payment methods (each with its payment_type), the
    pay-on-delivery switch, one entry per destination in `deliveries` (each with
    its shipments in split_keys and its selectable pickup_points), the
    `shipments` with their delivery dates, points choices and the money
    breakdown — totals.total is what Ozon charges today (0 ₽ on a fully
    deferred order) and totals.order_total is what the order costs.

    Pay-on-delivery does not always cover the whole order. pay_after_receipt
    .scope is one of "full", "partial" (some items must be paid up front:
    prepayment_amount now, post_payment_amount on receipt) or "none", and .note
    states it in words. On a partial order pay_now_items and pay_on_receipt_items
    name the lines on each side, as Ozon itself splits them, and the `shipments`
    are loaded with their items, each carrying `prepaid` (null when it holds
    items from both sides). shipment_items forces that loading on (true) or off
    (false); by default it happens only when scope is "partial".

    Forms the checkout itself if Ozon has not yet. If it reports
    available=false, `reason` says what to fix — usually: select cart items.
    Change it with configure_checkout, submit with place_order.
    """
    return await run_blocking(lambda: checkout.get_checkout(shipment_items))


@mcp.tool()
async def configure_checkout(
    payment: Annotated[
        str | None,
        Field(
            description='A payment method: a word ("СБП", "Ozon Карта", "новой картой"), a masked card '
            '("**5898") or a payment_type id. Must be one get_checkout() offers.'
        ),
    ] = None,
    points: Annotated[
        int | None,
        Field(ge=0, description="How many Ozon points to spend; 0 spends none. Offered amounts are in points[]."),
    ] = None,
    pay_after_receipt: Annotated[
        bool | None,
        Field(description="Turn «Оплатить после получения» on or off. Only when pay_after_receipt.available."),
    ] = None,
    pickup_point: Annotated[
        str | None,
        Field(
            description='Where to deliver: the point number ("№1449460"), part of its address ("Данилова") or '
            "its address_book_id. Must be one of deliveries[].pickup_points with available=true."
        ),
    ] = None,
    split_key: Annotated[
        str | None,
        Field(
            description="Which shipment to retarget, from deliveries[].split_keys. Only needed when the order "
            "has more than one destination — otherwise the choice is unambiguous."
        ),
    ] = None,
) -> Checkout:
    """Set checkout options and return the recomputed order — one call can set
    several. Omit an argument to leave that option alone.
    Every value comes from a get_checkout() answer, so read that first; passing
    something Ozon does not offer is refused with the list of what it does.
    Applied in the order Ozon recalculates them: destination, payment,
    pay-on-delivery, points. Turning points on can withdraw the pay-on-delivery
    offer, so check the result rather than assuming.
    """
    return await run_blocking(
        lambda: checkout.configure_checkout(
            payment=payment,
            points=points,
            pay_after_receipt=pay_after_receipt,
            pickup_point=pickup_point,
            split_key=split_key,
        )
    )


@mcp.tool()
async def place_order(
    confirm_total: Annotated[
        str,
        Field(
            description="The total the user agreed to, copied from get_checkout().totals — either order_total "
            '("777 ₽") or total ("0 ₽ сегодня"). Refused if Ozon has recalculated since.'
        ),
    ],
) -> OrderPlaced:
    """[GATED by orders_enabled — SPENDS REAL MONEY] Submit the order that
    get_checkout() describes. Not undoable from here except by cancel_order().
    Read get_checkout() immediately before, show the user totals.order_total —
    what the order costs — and pass back the figure they agreed to. The call is
    refused if that no longer matches, and nothing is ordered.
    Returns once the order actually exists, with its order_number: keep it, it
    is what cancel_order() and pay_order() need. Paying from the Ozon Card
    balance settles with the order; pay-on-delivery leaves nothing to pay today.
    """
    return await run_blocking(lambda: checkout.place_order(confirm_total))


@mcp.tool()
async def pay_order(order: OrderRef) -> PaymentRequested:
    """[GATED] Ask Ozon to charge an order left in «Ожидаем оплаты», and report
    what the user must still do.
    The result spells it out: `amount_due` is the charge, `shortfall` is set when
    the Ozon Card balance does not cover it (top up by that much), and
    `next_step` is the instruction to relay. `payment_url` is where the payment
    is completed — that page signs the account in to Ozon Bank, which is the
    owner's step, so this server never finishes the charge itself.
    Tell the user plainly: top up by `shortfall` if present, then finish at
    `payment_url`. Ordering with pay-on-delivery avoids all of it.
    """
    return await run_blocking(lambda: orders.pay_order(order))


@mcp.tool()
async def list_cancel_reasons(order: OrderRef) -> list[CancelReason]:
    """Reasons Ozon will accept for cancelling an order, with their reason_id.
    The catch-all one (needs_comment=true) is refused without a comment.
    """
    return await run_blocking(lambda: orders.list_cancel_reasons(order))


@mcp.tool()
async def cancel_order(
    order: OrderRef,
    skus: Annotated[
        list[str] | None,
        Field(
            description="Cancel only these lines (skus from order_products()) and leave the rest of the order "
            "standing. Omit to cancel the whole order."
        ),
    ] = None,
    reason_id: Annotated[
        str,
        Field(
            description='A reason_id from list_cancel_reasons(); "504" (изменить заказ и оформить заново) is '
            "the neutral default and needs no comment."
        ),
    ] = "504",
    comment: Annotated[
        str,
        Field(description="Free-text explanation. Required by the catch-all reason (needs_comment=true)."),
    ] = "",
    return_to_cart: Annotated[
        bool,
        Field(description="Put the cancelled items back in the cart, so the order can be recomposed."),
    ] = True,
) -> OrderCancelled:
    """[GATED by writes_enabled] Cancel an order, by default returning its items
    to the cart.
    skus cancels only those lines and leaves the rest of the order standing — an
    order can be cancelled item by item, in as many passes as it has items. Omit
    it to cancel the whole order. The selection is checked against what Ozon
    reports back and refused on a mismatch, since cancelling the wrong line is
    not undoable.
    reason_id from list_cancel_reasons; "504" (изменить заказ и оформить заново)
    is the neutral default, "508" needs a comment.
    Check `cancelled` in the result — Ozon may answer with a retention offer
    instead, and `detail` then carries what it asked.
    """
    return await run_blocking(
        lambda: orders.cancel_order(order, skus, reason_id, comment, return_to_cart=return_to_cart)
    )
