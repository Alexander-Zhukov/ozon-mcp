"""The pay-on-delivery switch is read from its checkbox status."""

from __future__ import annotations

from ozon_mcp.parsing.checkout import parse_pay_after_receipt


def _widget(status: str) -> dict[str, object]:
    return {
        "items": [
            {
                "leftBlock": {"control": {"type": "checkbox", "checkbox": {"status": status}}},
                "centerBlock": {"title": {"text": "Оплатить после получения часть заказа"}},
            },
            {"centerBlock": {"title": {"text": "Есть предоплата 12 640 ₽"}}},
        ]
    }


def test_parse_pay_after_receipt_toggle() -> None:
    on = parse_pay_after_receipt(_widget("SELECTED"))
    assert on.available is True
    assert on.enabled is True
    assert on.prepayment == "Есть предоплата 12 640 ₽"

    off = parse_pay_after_receipt(_widget("UNSELECTED"))
    assert off.available is True
    assert off.enabled is False

    assert parse_pay_after_receipt({}).available is False
