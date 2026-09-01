"""The sum owed on a row is Ozon's «К оплате при получении», not an item's price.

The row renders the group's sum, each item's price and each item's badge as the
same price atom, and taking the first of them read 2 534 ₽ where Ozon said 15 156 ₽.
"""

from __future__ import annotations

import json
from typing import Any

from ozon_mcp.parsing.orders import parse_orders


def _price(text: str, tag: str | None = None) -> dict[str, Any]:
    node: dict[str, Any] = {"price": [{"text": text, "textStyle": "PRICE"}], "priceStyle": {"styleType": "ACTUAL"}}
    if tag:
        node["testInfo"] = {"automatizationId": tag}
    return node


def _item(price: str) -> dict[str, Any]:
    return {
        "image": {"productMedia": {"image": {"url": "https://ir.ozone.ru/p.jpg"}}},
        "price": _price(price, "payMoney"),
    }


def _postpay_cell(sum_text: str) -> dict[str, Any]:
    return {
        "type": "dsCell",
        "dsCell": {
            "centerBlock": {"title": {"text": "К оплате при получении"}},
            "rightBlock": {"price": _price(sum_text)},
            "common": {"testInfo": {"automatizationId": "postpay_sum_cell"}},
        },
    }


def _page(row: dict[str, Any]) -> dict[str, Any]:
    return {"widgetStates": {"orderList-1": json.dumps({"ordersV2": [row]}, ensure_ascii=False)}}


def _row(*, cells: list[dict[str, Any]], items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "common": {"action": {"link": "v2/cacheOrderProducts?data=BUNDLE"}},
        "leftBlock": {
            "textIcon": {"text": {"text": "Можно забирать", "testInfo": {"automatizationId": "tileStatus"}}},
            "title": {"text": "Пункт Ozon: ул. Данилова, 17"},
            "subtitle": {"text": "Сегодня с 09:00 до 21:00"},
            "cellList": {"cells": cells},
        },
        "rightBlock": {"products": {"products": items}},
    }


def test_the_sum_is_the_pay_on_pickup_cell_not_the_first_item_price() -> None:
    row = _row(cells=[_postpay_cell("15 156 ₽")], items=[_item("2 534 ₽"), _item("3 201 ₽")])
    order = parse_orders(_page(row))[0]
    assert order.amount_due_at_pickup == "15 156 ₽"
    assert [item.price for item in order.products] == ["2 534 ₽", "3 201 ₽"]


def test_a_row_owing_nothing_reports_no_sum() -> None:
    order = parse_orders(_page(_row(cells=[], items=[_item("2 534 ₽")])))[0]
    assert order.amount_due_at_pickup is None
