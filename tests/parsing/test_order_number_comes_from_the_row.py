"""Every listed order has to carry the number the other order tools take.

A row's own link bundles the postings of every order arriving together, so
decoding it pins nothing to that row — one row came back with seven numbers and
twelve rows with none. Each product on a row links to its own order instead.
"""

from __future__ import annotations

import json

from ozon_mcp.parsing.orders import order_numbers_in, parse_orders


def _product(order: str, posting: str) -> dict[str, object]:
    return {
        "image": {
            "productMedia": {
                "image": {"url": "https://ir.ozone.ru/p.jpg"},
                "common": {"action": {"link": f"/my/orderdetails/?order={order}&postingId={posting}"}},
            }
        }
    }


def _page(*rows: dict[str, object]) -> dict[str, object]:
    return {"widgetStates": {"orderList-1": json.dumps({"ordersV2": list(rows)}, ensure_ascii=False)}}


def _row(*products: dict[str, object]) -> dict[str, object]:
    return {
        "common": {"action": {"link": "v2/cacheOrderProducts?data=BUNDLE"}},
        "leftBlock": {"title": {"text": "Пункт Ozon"}, "textIcon": {"text": {"text": "В пути"}}},
        "rightBlock": {"products": {"products": list(products)}},
    }


def test_a_row_reports_the_order_its_products_belong_to() -> None:
    orders = parse_orders(_page(_row(_product("44563249-0864", "47288826961"))))
    assert orders[0].order_number == "44563249-0864"
    assert orders[0].order_numbers == ["44563249-0864"]


def test_a_delivery_group_reports_every_order_in_it() -> None:
    row = _row(_product("44563249-0833", "1"), _product("44563249-0834", "2"), _product("44563249-0833", "3"))
    assert order_numbers_in(row) == ["44563249-0833", "44563249-0834"]
    assert parse_orders(_page(row))[0].order_number == "44563249-0833"


def test_a_row_with_no_product_links_has_no_number() -> None:
    assert order_numbers_in(_row()) == []
    assert parse_orders(_page(_row()))[0].order_number is None
