"""The instalment offer is found by the method's declared kind, not by a word."""

from __future__ import annotations

from ozon_mcp.parsing.checkout import payment_note


def _payments() -> dict[str, object]:
    return {
        "payments": [
            {
                "title": {"text": " "},
                "automatizationDescription": "OzonCard",
                "promoteLabel": {"text": "-661 ₽"},
            },
            {
                "title": {"text": "Ozon Рассрочка"},
                "automatizationDescription": "OzonCredit",
                "promoteLabel": {"text": "-128 ₽"},
            },
            {"title": {"text": "** 5898"}, "automatizationDescription": "Sberpay"},
        ]
    }


def test_the_instalment_offer_comes_from_its_own_entry() -> None:
    assert payment_note(_payments(), "OzonCredit") == "Ozon Рассрочка -128 ₽"


def test_a_method_without_a_promo_label_reads_its_title() -> None:
    assert payment_note(_payments(), "Sberpay") == "** 5898"


def test_a_kind_the_order_does_not_offer_reads_as_nothing() -> None:
    assert payment_note(_payments(), "YooMoney") is None
    assert payment_note({}, "OzonCredit") is None
