"""Payment methods resolve from what a person actually says."""

from __future__ import annotations

import pytest

from ozon_mcp.errors import OzonError
from ozon_mcp.models.checkout import PaymentOption
from ozon_mcp.services.checkout import _match_payment_option

OPTIONS = [
    PaymentOption(payment_type=1626, kind="FastPaymentSystem"),
    PaymentOption(payment_type=2044, kind="Sberpay"),
    PaymentOption(payment_type=2044, kind="Sberpay", label="** 5898"),
    PaymentOption(payment_type=3, kind="NewCard", label="Новой картой"),
    PaymentOption(payment_type=22, kind="YooMoney"),
]


@pytest.mark.parametrize(
    ("wanted", "expected"),
    [
        ("СБП", 1626),
        ("быстрые платежи", 1626),
        ("**5898", 2044),
        ("5898", 2044),
        ("новой картой", 3),
        ("ЮMoney", 22),
        ("22", 22),
    ],
)
def test_match_payment_accepts_words_and_cards(wanted: str, expected: int) -> None:
    assert _match_payment_option(OPTIONS, wanted).payment_type == expected


def test_match_payment_reports_options_when_unknown() -> None:
    with pytest.raises(OzonError, match="available:"):
        _match_payment_option(OPTIONS, "биткоин")
