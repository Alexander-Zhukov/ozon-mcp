"""Money crosses this boundary as text; the arithmetic has to survive it."""

from __future__ import annotations

import pytest

from ozon_mcp.services.orders import _kopecks, _money


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("656 ₽", 65_600),
        ("415,64 ₽", 41_564),
        # Ozon separates thousands with a narrow no-break space.
        ("12 640 ₽", 1_264_000),
        ("1 060 ₽", 106_000),
        ("", None),
    ],
)
def test_kopecks_reads_ozon_money(text: str, expected: int | None) -> None:
    assert _kopecks(text) == expected


@pytest.mark.parametrize(
    ("kopecks", "expected"),
    [("65600", "656 ₽"), ("24036", "240,36 ₽"), ("1264000", "12 640 ₽"), ("", None)],
)
def test_money_writes_roubles(kopecks: str, expected: str | None) -> None:
    assert _money(kopecks) == expected


def test_the_shortfall_is_the_difference() -> None:
    # 656 ₽ owed against 415,64 ₽ on the card is the 240,36 ₽ Ozon itself quotes.
    assert _money(str(_kopecks("656 ₽") - _kopecks("415,64 ₽"))) == "240,36 ₽"
