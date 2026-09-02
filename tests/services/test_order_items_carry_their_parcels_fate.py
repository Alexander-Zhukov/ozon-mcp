"""An item's outcome belongs to its parcel, not to its order.

Refusing something at the pickup point cancels that parcel while the rest of the
order is received, so one order holds «Получен» and «Отменён» at once. Flattening
the parcels lost it, and «Купленные товары» — which lists everything ever ordered
and states no status — then read as "bought" for items nobody took home.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ozon_mcp.services import catalog
from ozon_mcp.utils.serde import dumps
from support import page

if TYPE_CHECKING:
    from support import FakeSession

RECEIVED_SKU = "1660338200"
REFUSED_SKU = "1152100818"


def _shipment(shipment_id: str, status: str, sku: str, title: str) -> dict[str, Any]:
    return {
        "shipmentId": shipment_id,
        "header": [
            {
                "type": "textIcon",
                "textIcon": {"text": {"text": status, "testInfo": {"automatizationId": "shipment-status"}}},
            }
        ],
        "items": [
            {
                "sellers": [
                    {
                        "name": "Продавец",
                        "products": [
                            {
                                "title": {
                                    "name": {"text": title},
                                    "common": {"action": {"id": sku, "link": f"/product/{sku}/"}},
                                },
                                "price": {"price": [{"text": "4 020 ₽"}]},
                            }
                        ],
                    }
                ]
            }
        ],
    }


def _order_page(*shipments: dict[str, Any]) -> dict[str, Any]:
    served = page()
    for index, shipment in enumerate(shipments):
        served["widgetStates"][f"shipmentWidget-{index}-default-1"] = dumps(shipment)
    return served


ORDER = _order_page(
    _shipment("42641796961", "Получен", RECEIVED_SKU, "Джоггеры FERRON"),
    _shipment("42711916961", "Отменён", REFUSED_SKU, "Джоггеры Armed Forces"),
)


def test_each_item_reports_its_own_parcel(session: FakeSession) -> None:
    session.pages = {"/my/orderdetails/": ORDER}
    items = {item.sku: item for item in catalog.order_products("44563249-0835")}
    assert items[RECEIVED_SKU].shipment_status == "Получен"
    assert items[RECEIVED_SKU].received is True
    assert items[REFUSED_SKU].shipment_status == "Отменён"
    assert items[REFUSED_SKU].received is False
    assert items[RECEIVED_SKU].order_number == "44563249-0835"


def test_purchases_stay_silent_about_the_outcome_unless_asked(session: FakeSession) -> None:
    session.pages = {"/my/favorites/list": page(tileGridDesktop={"items": [{"sku": RECEIVED_SKU}]})}
    bought = catalog.purchases()
    assert bought[0].received is None
    assert bought[0].order_status is None
    assert not any("orderdetails" in url for url in session.fetched), "the orders were read without being asked for"


def test_with_status_takes_the_outcome_from_the_orders(session: FakeSession) -> None:
    rows = page(
        orderList={
            "ordersV2": [
                {
                    "common": {"action": {"link": "v2/cacheOrderProducts?data=X"}},
                    "leftBlock": {
                        "textIcon": {
                            "text": {"text": "Получен 11 августа", "testInfo": {"automatizationId": "tileStatus"}}
                        }
                    },
                    "rightBlock": {
                        "products": {
                            "products": [
                                {
                                    "image": {
                                        "productMedia": {
                                            "common": {
                                                "action": {"link": "/my/orderdetails/?order=44563249-0835&postingId=1"}
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    },
                }
            ]
        }
    )
    session.pages = {
        "/my/favorites/list": page(tileGridDesktop={"items": [{"sku": RECEIVED_SKU}, {"sku": REFUSED_SKU}]}),
        "/my/orderdetails/": ORDER,
        "/my/orderlist": rows,
    }
    bought = {purchase.sku: purchase for purchase in catalog.purchases(with_status=True)}
    assert bought[RECEIVED_SKU].received is True
    assert bought[REFUSED_SKU].received is False
    assert bought[REFUSED_SKU].order_status == "Отменён"
