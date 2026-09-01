"""Shipments carry the id every per-shipment call needs, so they are read
structurally rather than by pairing texts in page order.
"""

from __future__ import annotations

from ozon_mcp.parsing.checkout import parse_shipment_items, parse_shipments, shipment_detail_link, shipment_total


def _page() -> dict[str, object]:
    return {
        "widgetStates": {
            "rfbsSplit-1-checkout-2": (
                '{"id": "FBS-3769566873-S2532799",'
                ' "header": {"text": {"text": "Доставим 10 – 19 сентября"}},'
                ' "subHeader": {"text": "1 товар • 666 гр"},'
                ' "action": {"link": "/modal/splitdetailv2?current_address=abc'
                '&detail_split_key=FBS-3769566873-S2532799"}}'
            ),
            "rfbsSplit-2-checkout-2": (
                '{"id": "FBO-3583627022,FBO-812153408",'
                ' "header": {"text": {"text": "Доставим завтра при заказе до 17:00"}},'
                ' "subHeader": {"text": "2 товара • 613 гр"},'
                ' "action": {"link": "/modal/splitdetailv2?current_address=abc&detail_split_key=FBO-3583627022"}}'
            ),
            "rfbsSplitHeader-3-checkout-2": '{"header": {"text": "ДОСТАВКА OZON"}}',
        }
    }


def test_parse_shipments_reads_id_and_dates() -> None:
    shipments = parse_shipments(_page())
    assert [shipment.split_key for shipment in shipments] == [
        "FBO-3583627022,FBO-812153408",
        "FBS-3769566873-S2532799",
    ]
    assert shipments[1].delivery == "Доставим 10 – 19 сентября"
    assert shipments[1].summary == "1 товар • 666 гр"


def test_detail_link_comes_from_the_payload() -> None:
    # It carries the chosen address, so it cannot be assembled from the key.
    link = shipment_detail_link(_page(), "FBS-3769566873-S2532799")
    assert link is not None
    assert "current_address=abc" in link
    assert shipment_detail_link(_page(), "nope") is None


def test_parse_shipment_items_reads_titles_prices_and_seller() -> None:
    modal = {
        "widgetStates": {
            "splitDetailWebV2-1": (
                '{"vertical": {"splits": [{"title": {"text": "Bird Mountain Official Store"},'
                ' "items": [{"mainColumn": [{"textAtom": {"text": "Брюки бойфренды"}},'
                ' {"textAtom": {"text": "цвет брезентово-серый, размер 54, 666 гр"}}],'
                ' "price": {"price": "2 152 ₽", "originalPrice": "6 409 ₽"},'
                ' "sideColumn": [{"text": "1 шт."}]}]}]}}'
            )
        }
    }
    items = parse_shipment_items(modal)
    assert len(items) == 1
    assert items[0].title == "Брюки бойфренды"
    assert items[0].variant == "цвет брезентово-серый, размер 54, 666 гр"
    # The struck-through original price must not win over what is actually charged.
    assert items[0].price == "2 152 ₽"
    assert items[0].quantity == "1 шт."
    assert items[0].seller == "Bird Mountain Official Store"
    assert shipment_total(items) == "2 152 ₽"
