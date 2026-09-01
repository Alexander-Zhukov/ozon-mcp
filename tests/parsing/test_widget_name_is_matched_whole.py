"""A widget name that is a prefix of another must not be confused with it.

A product card carries both ``webPrice`` and ``webPriceDecreasedCompact``, and
matching by prefix returned whichever Ozon happened to serve first — so the same
card answered with its price or with «Стало дешевле», at random. That is how
find_cheaper came to report "nothing is cheaper" for a product it had failed to
price.
"""

from __future__ import annotations

from ozon_mcp.parsing.catalog import parse_product
from ozon_mcp.parsing.common import widget
from ozon_mcp.utils.serde import dumps

PRICE = {"isAvailable": True, "cardPrice": "4 110 ₽", "price": "4 327 ₽", "originalPrice": "12 074 ₽"}
DECREASED = {"textRs": [{"type": "text", "content": "Стало дешевле"}], "link": "/modal/web_pdp_lower_price"}


def _card(*, decreased_first: bool) -> dict[str, object]:
    keys = [("webPriceDecreasedCompact-1-default-1", DECREASED), ("webPrice-2-default-1", PRICE)]
    if not decreased_first:
        keys.reverse()
    return {"widgetStates": {key: dumps(state) for key, state in keys}}


def test_the_exact_name_wins_whatever_the_order() -> None:
    for decreased_first in (True, False):
        assert widget(_card(decreased_first=decreased_first), "webPrice") == PRICE


def test_the_card_reads_its_three_prices() -> None:
    card = parse_product(_card(decreased_first=True))
    assert card.price == "4 110 ₽"
    assert card.price_regular == "4 327 ₽"
    assert card.price_old == "12 074 ₽"
    assert card.available is True
