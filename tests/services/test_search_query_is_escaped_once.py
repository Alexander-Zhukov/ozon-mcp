"""A search phrase reaches Ozon escaped exactly once.

The transport leaves ``&`` and ``=`` alone so a caller can build a query, and it
now leaves ``%`` alone too. Escaping the phrase twice turned "тунец" into
``%25D1%2582…`` — a nonsense query, which Ozon answered with car accessories.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ozon_mcp.services import catalog
from support import page

if TYPE_CHECKING:
    from support import FakeSession

TILES = page(tileGridDesktop={"items": [{"sku": "5261712329", "price": [{"text": "162 ₽", "textStyle": "PRICE"}]}]})


def test_a_cyrillic_phrase_is_escaped_once(session: FakeSession) -> None:
    session.pages = {"/search/": TILES}
    catalog.search("тунец в собственном соку", limit=1)
    asked = next(url for url in session.fetched if url.startswith("/search/"))
    assert "text=%D1%82%D1%83%D0%BD%D0%B5%D1%86" in asked
    assert "%25" not in asked, "the phrase was escaped twice"


def test_an_ampersand_in_a_phrase_cannot_add_a_parameter(session: FakeSession) -> None:
    session.pages = {"/search/": TILES}
    catalog.search("кофе & чай", limit=1)
    asked = next(url for url in session.fetched if url.startswith("/search/"))
    assert "%26" in asked
    assert "&text=" in asked
    assert asked.count("&") == asked.count("&text=") + asked.count("&sorting=") + asked.count("&page=")
