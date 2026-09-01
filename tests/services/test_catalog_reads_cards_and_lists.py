"""The catalog tools take a sku or a url, and paginate to a declared ceiling."""

from __future__ import annotations

from ozon_mcp.services import catalog, favorites
from ozon_mcp.utils.serde import dumps
from support import FakeSession, page

CARD = {
    "webProductHeading": {"title": "Таблетница"},
    "webPrice": {"price": "119 ₽", "originalPrice": "3 000 ₽"},
}


def _tiles(*skus: str, counter: int | None = None, paginator: str | None = None) -> dict[str, object]:
    served = page(
        tileGridDesktop={
            "items": [
                {
                    "sku": sku,
                    "mainState": [
                        {"type": "priceV2", "priceV2": {"price": [{"text": "100 ₽", "textStyle": "PRICE"}]}},
                        {"type": "textDS", "id": "name", "textDS": {"text": f"Товар {sku}"}},
                    ],
                }
                for sku in skus
            ]
        }
    )
    if counter is not None:
        served["widgetStates"]["favoriteCounter-1-default-1"] = dumps({
            "iconHeader": {"counter": {"text": str(counter)}}
        })
    if paginator:
        served["widgetStates"]["paginator-1-default-1"] = dumps({"nextPage": paginator})
    return served


def test_a_url_is_accepted_where_a_sku_is(session: FakeSession) -> None:
    session.pages = {"/product/3077454533": page(**CARD)}
    card = catalog.product_details("https://www.ozon.ru/product/tabletnitsa-3077454533/?at=x")
    # The sku it was asked for is the sku it reports, page or no page.
    assert card.sku == "3077454533"
    assert card.title == "Таблетница"
    assert any("/product/3077454533" in path for path in session.fetched)


def test_search_reads_the_tiles_it_is_served(session: FakeSession) -> None:
    session.pages = {"/search": _tiles("1", "2")}
    found = catalog.search("таблетница")
    assert [tile.sku for tile in found] == ["1", "2"]
    assert found[0].title == "Товар 1"
    assert found[0].price == "100 ₽"


def test_the_walk_stops_at_the_count_the_page_displays(session: FakeSession) -> None:
    # Two tiles are served and the page says there are two favorites, so the
    # recommendation grid on the next page must not be walked into.
    session.pages = {
        "/my/favorites": _tiles("1", "2", counter=2, paginator="/my/favorites?layout_page_index=2"),
        "layout_page_index=2": _tiles("3", "4"),
    }
    assert [tile.sku for tile in favorites.list_favorites(100)] == ["1", "2"]


def test_a_delivery_estimate_names_what_it_is_relative_to(session: FakeSession) -> None:
    session.pages = {
        "webDelivery": {
            "state": {
                "sections": [
                    {
                        "type": "addressSelect",
                        "descriptionRs": [
                            {"type": "text", "content": "ул. Данилова, 17"},
                            {"type": "text", "content": "Со склада Ozon"},
                        ],
                        "trackingInfo": {"click": {"key": "MAIN"}},
                    },
                    {
                        "descriptionRs": [
                            {"type": "text", "content": "Пункты выдачи"},
                            {"type": "text", "content": "Завтра, 2 сентября"},
                        ],
                        "trackingInfo": {"click": {"key": "PVZ"}},
                    },
                ],
                "cellTrackingInfo": {"uis": {"main": "MAIN", "pvz": "PVZ"}},
            }
        }
    }
    estimate = catalog.delivery_estimate("3077454533")
    assert estimate.delivery == "Завтра, 2 сентября"
    assert estimate.address == "ул. Данилова, 17"
    assert estimate.source == "Со склада Ozon"
