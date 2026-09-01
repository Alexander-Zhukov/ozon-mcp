"""Which shipment the prepayment belongs to is derived, so it must refuse to guess."""

from __future__ import annotations

from ozon_mcp.models.checkout import Checkout, PayAfterReceipt, Shipment
from ozon_mcp.services.checkout import _attribute_prepayment


def _checkout(prepayment: str, *totals: str) -> Checkout:
    return Checkout(
        available=True,
        pay_after_receipt=PayAfterReceipt(available=True, enabled=True, scope="partial", prepayment_amount=prepayment),
        shipments=[Shipment(split_key=f"S{index}", total=total) for index, total in enumerate(totals)],
    )


def test_one_matching_shipment_is_the_prepaid_one() -> None:
    # The live case: 2 152 ₽ of a 6 691 ₽ order is exactly one shipment.
    checkout = _checkout("2 152 ₽", "656 ₽", "2 152 ₽", "3 883 ₽")
    _attribute_prepayment(checkout)
    assert [shipment.prepaid for shipment in checkout.shipments] == [False, True, False]


def test_a_combination_of_shipments_counts_too() -> None:
    checkout = _checkout("2 808 ₽", "656 ₽", "2 152 ₽", "3 883 ₽")
    _attribute_prepayment(checkout)
    assert [shipment.prepaid for shipment in checkout.shipments] == [True, True, False]


def test_ambiguous_amounts_stay_unattributed() -> None:
    # 500 ₽ could be either shipment; naming one would be a coin toss.
    checkout = _checkout("500 ₽", "500 ₽", "500 ₽")
    _attribute_prepayment(checkout)
    assert [shipment.prepaid for shipment in checkout.shipments] == [None, None]


def test_nothing_adding_up_stays_unattributed() -> None:
    checkout = _checkout("999 ₽", "656 ₽", "2 152 ₽")
    _attribute_prepayment(checkout)
    assert [shipment.prepaid for shipment in checkout.shipments] == [None, None]


def test_an_unknown_shipment_total_blocks_attribution() -> None:
    checkout = _checkout("656 ₽", "656 ₽", None)
    _attribute_prepayment(checkout)
    assert [shipment.prepaid for shipment in checkout.shipments] == [None, None]
