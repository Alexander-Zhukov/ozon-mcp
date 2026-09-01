"""The pay-on-delivery switch: its checkbox status, and how far it reaches.

Ozon offers the same switch for a whole order and for part of one, and the two
charge different money — so the scope is read, not assumed.
"""

from __future__ import annotations

from ozon_mcp.models.checkout import Totals
from ozon_mcp.parsing.checkout import _state_postpay, parse_pay_after_receipt

# What the checkout layout declares for the two cases.
TEXTS = {
    "fullPostPayCheckboxText": "Оплатить после получения",
    "mixedPrepayCheckboxText": "Оплатить после получения часть заказа",
    "mixedPrepayDetailsText": "Есть предоплата",
}


def _widget(status: str, title: str, prepayment: str | None = None) -> dict[str, object]:
    items: list[dict[str, object]] = [
        {
            "leftBlock": {"control": {"type": "checkbox", "checkbox": {"status": status}}},
            "centerBlock": {"title": {"text": title}},
        }
    ]
    if prepayment:
        items.append({"centerBlock": {"title": {"text": prepayment}}})
    return {"items": items}


def test_parse_pay_after_receipt_toggle() -> None:
    widget = _widget("SELECTED", TEXTS["mixedPrepayCheckboxText"], "Есть предоплата 12 640 ₽")
    on = parse_pay_after_receipt(widget, TEXTS)
    assert on.available is True
    assert on.enabled is True
    assert on.prepayment == "Есть предоплата 12 640 ₽"

    off = parse_pay_after_receipt(_widget("UNSELECTED", TEXTS["mixedPrepayCheckboxText"]), TEXTS)
    assert off.available is True
    assert off.enabled is False

    assert parse_pay_after_receipt({}, TEXTS).available is False


def test_scope_comes_from_ozons_own_wording() -> None:
    partial = parse_pay_after_receipt(
        _widget("SELECTED", TEXTS["mixedPrepayCheckboxText"], "Есть предоплата 2 152 ₽"), TEXTS
    )
    assert partial.scope == "partial"
    assert partial.prepayment_amount == "2 152 ₽"

    full = parse_pay_after_receipt(_widget("SELECTED", TEXTS["fullPostPayCheckboxText"]), TEXTS)
    assert full.scope == "full"
    assert full.prepayment_amount is None


def test_reworded_label_falls_back_to_the_other_signal() -> None:
    # Ozon rewords the checkbox: "часть" still marks a split order, and a label
    # that no longer mentions a part still means the whole one.
    split = parse_pay_after_receipt(_widget("SELECTED", "Оплатить после получения часть товаров"), TEXTS)
    assert split.scope == "partial"

    whole = parse_pay_after_receipt(_widget("SELECTED", "Оплата после получения заказа"), TEXTS)
    assert whole.scope == "full"


def test_the_deferred_half_is_stated_not_left_to_the_reader() -> None:
    switch = parse_pay_after_receipt(
        _widget("SELECTED", TEXTS["mixedPrepayCheckboxText"], "Есть предоплата 2 152 ₽"), TEXTS
    )
    _state_postpay(switch, Totals(total="2 152 ₽ сегодня", order_total="6 691 ₽"))
    assert switch.post_payment_amount == "4 539 ₽"
    assert "2 152 ₽ is charged now" in (switch.note or "")


def test_a_switch_left_off_says_the_whole_order_is_charged_now() -> None:
    # Ozon stops printing the prepayment line once the switch is off, and
    # nothing is deferred then — so the useful figure is the whole order.
    switch = parse_pay_after_receipt(_widget("UNSELECTED", TEXTS["mixedPrepayCheckboxText"]), TEXTS)
    _state_postpay(switch, Totals(total="6 691 ₽", order_total="6 691 ₽"))
    assert switch.post_payment_amount is None
    assert switch.note == (
        "only part of this order can be paid on delivery; the switch is off, so all 6 691 ₽ is charged now"
    )


def test_a_full_order_says_nothing_is_charged_now() -> None:
    switch = parse_pay_after_receipt(_widget("SELECTED", TEXTS["fullPostPayCheckboxText"]), TEXTS)
    _state_postpay(switch, Totals(total="0 ₽ сегодня", order_total="777 ₽"))
    assert switch.post_payment_amount == "777 ₽"
    assert "nothing is charged now" in (switch.note or "")


def test_no_switch_at_all_is_said_out_loud() -> None:
    switch = parse_pay_after_receipt({}, TEXTS)
    _state_postpay(switch, Totals(order_total="2 152 ₽"))
    assert switch.scope == "none"
    assert switch.note == "Ozon does not offer pay-on-delivery for this order"
