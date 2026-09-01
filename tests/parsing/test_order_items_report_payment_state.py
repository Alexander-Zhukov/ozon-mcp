"""Payment state is per item: one row holds paid and unpaid items at once.

An item with no badge reports ``paid`` as None — "Ozon did not say" is not "not paid".
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from ozon_mcp.parsing.orders import parse_orders


def _item(*, badge: str | None = None, price: str = "2 534 ₽", quantity: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "image": {
            "productMedia": {
                "image": {"url": "https://ir.ozone.ru/p.jpg"},
                "common": {
                    "action": {"link": "/my/orderdetails/?order=44563249-0833&postingId=47288826961"},
                    "testInfo": {"automatizationId": "itemImage"},
                },
            }
        },
        "price": {"price": [{"text": price}], "testInfo": {"automatizationId": "payMoney"}},
        "caption": {"text": "Хранится до 14 сентября", "testInfo": {"automatizationId": "postingPvzExpiration"}},
    }
    if badge is not None:
        item["badgeStatus"] = {"text": badge, "common": {"testInfo": {"automatizationId": "itemPay"}}}
    if quantity is not None:
        item["quantity"] = {"text": quantity, "testInfo": {"automatizationId": "itemQuantity"}}
    return item


def _page(*items: dict[str, Any]) -> dict[str, Any]:
    row = {
        "common": {"action": {"link": "v2/cacheOrderProducts?data=BUNDLE"}},
        "leftBlock": {"textIcon": {"text": {"text": "Можно забирать", "testInfo": {"automatizationId": "tileStatus"}}}},
        "rightBlock": {"products": {"products": list(items)}},
    }
    return {"widgetStates": {"orderList-1": json.dumps({"ordersV2": [row]}, ensure_ascii=False)}}


def test_paid_and_unpaid_items_of_one_row_are_told_apart() -> None:
    items = parse_orders(_page(_item(badge="Оплачен"), _item(badge="Не оплачен")))[0].products
    assert [item.paid for item in items] == [True, False]
    assert [item.payment_status for item in items] == ["Оплачен", "Не оплачен"]


def test_an_item_without_a_badge_leaves_payment_unknown() -> None:
    item = parse_orders(_page(_item()))[0].products[0]
    assert item.paid is None
    assert item.payment_status is None


def test_an_item_reports_its_own_price_order_quantity_and_storage_date() -> None:
    item = parse_orders(_page(_item(badge="Оплачен", quantity="2 шт")))[0].products[0]
    assert item.price == "2 534 ₽"
    assert item.order_number == "44563249-0833"
    assert item.quantity == "2 шт"
    # The year is Ozon's to leave out; what matters is that a deadline is read as
    # the coming 14 September and not as last year's.
    assert item.stored_until is not None
    assert item.stored_until.endswith("-09-14")
    assert item.stored_until >= datetime.date.today().isoformat()
