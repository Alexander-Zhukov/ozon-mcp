"""«Дешевле» has to come from both places Ozon keeps it, and never from silence.

Ozon's text search is literal: a lot whose own title omits the brand is not
returned for a query that includes it, which is how the cheapest lot of a mouse
stayed invisible while the answer was presented as "the cheapest". Ozon's own
«Есть дешевле или быстрее» knows that lot, so both are read and merged.

And a base price that could not be parsed used to mean an empty answer —
indistinguishable from "nothing is cheaper", which is the one wrong thing to say.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from ozon_mcp.errors import OzonError
from ozon_mcp.services import catalog
from ozon_mcp.utils.serde import dumps
from support import page

if TYPE_CHECKING:
    from support import FakeSession

BASE_SKU = "3662719065"
OFFER_SKU = "5523443610"


def _card(price: dict[str, Any] | None) -> dict[str, Any]:
    widgets: dict[str, Any] = {
        "webProductHeading": {"title": "Razer Игровая мышь беспроводная, зеленый"},
        "webDetailSKU": {"sku": BASE_SKU},
        "webBestSeller": {
            "textRs": [{"content": "Есть дешевле или быстрее"}, {"content": "от 4 110 ₽"}],
            "count": "46",
        },
    }
    if price is not None:
        widgets["webPrice"] = price
    return page(**widgets)


OFFERS = page(
    webSellerList={
        "sellers": [
            {
                "sku": OFFER_SKU,
                "name": "LFY1",
                "price": {"cardPrice": {"price": "4 110 ₽"}},
                "productLink": f"https://www.ozon.ru/product/{OFFER_SKU}/",
                "advantages": [{"contentRs": {"headRs": [{"type": "text", "content": "Доставим 19 сентября"}]}}],
            }
        ]
    }
)


def _tile(sku: str, price: str, title: str) -> dict[str, Any]:
    return {
        "sku": sku,
        "price": [{"text": price, "textStyle": "PRICE"}],
        "tileName": {"id": "name", "text": title},
    }


SEARCH_PAGE = page(
    tileGridDesktop={
        "items": [
            _tile("4544893697", "4 200 ₽", "Razer Игровая мышь беспроводная, черный матовый"),
            _tile("2529431089", "5 114 ₽", "Мышь Razer Basilisk V3 X Hyperspeed черный"),
            # Cheaper than the base and not the same thing: a title search ranks
            # on words, so this is what used to come back as "cheaper".
            _tile("5605423013", "1 303 ₽", "Кейкапы для механической клавиатуры"),
        ]
    }
)


def _wired(session: FakeSession, *, price: dict[str, Any] | None) -> None:
    session.pages = {
        "otherOffersFromSellers": OFFERS,
        f"/product/{BASE_SKU}/": _card(price),
        "/search/": SEARCH_PAGE,
    }


def test_the_offers_ozon_itself_lists_are_included(session: FakeSession) -> None:
    _wired(session, price={"cardPrice": "4 321 ₽", "price": "4 544 ₽"})
    answer = catalog.find_cheaper(BASE_SKU)
    offer = answer.cheaper[0]
    assert offer.sku == OFFER_SKU
    assert offer.seller == "LFY1"
    assert offer.delivery == "Доставим 19 сентября"
    assert any("sort=price" in url for url in session.fetched)


def test_search_results_are_merged_and_ranked_together(session: FakeSession) -> None:
    _wired(session, price={"cardPrice": "4 321 ₽", "price": "4 544 ₽"})
    ranked = [(tile.sku, tile.price) for tile in catalog.find_cheaper(BASE_SKU).cheaper]
    assert ranked == [(OFFER_SKU, "4 110 ₽"), ("4544893697", "4 200 ₽")], (
        "the 5 114 ₽ lot is not cheaper, and the keycaps are not the same product"
    )


def test_an_unreadable_base_price_fails_instead_of_saying_nothing_is_cheaper(session: FakeSession) -> None:
    _wired(session, price=None)
    with pytest.raises(OzonError, match="could not read the price"):
        catalog.find_cheaper(BASE_SKU)


def test_the_search_walks_deeper_than_one_page(session: FakeSession) -> None:
    pages = iter([
        page(tileGridDesktop={"items": [{"sku": "1000001", "price": [{"text": "999 ₽", "textStyle": "PRICE"}]}]}),
        page(tileGridDesktop={"items": [{"sku": "1000002", "price": [{"text": "888 ₽", "textStyle": "PRICE"}]}]}),
    ])
    session.pages = {"/search/": lambda: next(pages, page())}
    found = catalog.search("мышь", sort="cheap", limit=2)
    assert [tile.sku for tile in found] == ["1000002", "1000001"], "ranked on price, not on page order"
    assert dumps(session.fetched).count("page=") >= 2
