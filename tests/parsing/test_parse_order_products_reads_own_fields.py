"""Order products are read from their own fields, not from nearby text.

The fixture mirrors the live shape: shipmentWidget → items → sellers → products,
where the sku is the link action's id and the name is title.name. Statuses and
the seller name are included precisely because a text-shape heuristic picks
those up instead of the product name.
"""

from __future__ import annotations

import json

from ozon_mcp.parsing.orders import parse_order_products


def _page() -> dict[str, object]:
    shipment = {
        "dynamicElements": [{"type": "text", "text": {"text": "Заказ покинул сортировочный центр"}}],
        "items": [
            {
                "sellers": [
                    {
                        "name": {"text": "Sikang Department Store"},
                        "products": [
                            {
                                "title": {
                                    "name": {"text": "Аромат сандала"},
                                    "common": {
                                        "action": {
                                            "link": "/product/aromat-sandala-3207911181/",
                                            "id": "3207911181",
                                        }
                                    },
                                },
                                "price": {"price": [{"text": "114 ₽"}]},
                                "attributes": [{"text": "Коричневый"}],
                            }
                        ],
                    }
                ]
            }
        ],
    }
    return {"widgetStates": {"shipmentWidget-1-default-1": json.dumps(shipment, ensure_ascii=False)}}


def test_parse_order_products_reads_own_fields() -> None:
    products = parse_order_products(_page())
    assert len(products) == 1
    product = products[0]
    assert product.sku == "3207911181"
    assert product.title == "Аромат сандала"
    assert product.price == "114 ₽"
    assert product.variant == "Коричневый"
    assert product.seller == "Sikang Department Store"
    assert product.url == "https://www.ozon.ru/product/3207911181/"


def test_parse_order_products_ignores_pages_without_shipments() -> None:
    assert parse_order_products({"widgetStates": {}}) == []
