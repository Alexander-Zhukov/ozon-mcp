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


def test_bought_items_takes_the_outcome_from_the_orders(session: FakeSession) -> None:
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
    answer = catalog.bought_items()
    bought = {purchase.sku: purchase for purchase in answer.items}
    assert bought[RECEIVED_SKU].received is True
    assert bought[REFUSED_SKU].received is False
    assert bought[REFUSED_SKU].order_status == "Отменён"
    # The answer states its own coverage, so a partial one cannot pass for whole.
    assert answer.complete is True
    assert answer.scanned_orders == 1
    assert answer.scanned_back_to == "2026-08-11"
    assert answer.unresolved == []


def test_a_sku_missing_from_a_fully_scanned_history_is_named_and_settled(session: FakeSession) -> None:
    """Looking at everything there is and not finding it is an answer."""
    session.pages = {
        "/my/favorites/list": page(tileGridDesktop={"items": [{"sku": "999999999"}]}),
        "/my/orderdetails/": ORDER,
        "/my/orderlist": page(orderList={"ordersV2": []}),
    }
    answer = catalog.bought_items()
    assert answer.unresolved == ["999999999"]
    assert answer.items[0].received is None
    # The archive ran out before the bound did, so nothing is left to look at.
    assert answer.complete is True


def test_a_refusal_is_provisional_while_older_orders_remain(session: FakeSession) -> None:
    """«Отменён» is not "never had it": an older order may have been received.

    Treating the first match as final got that wrong on the live account — an
    item refused in August had been received in February, and the scan stopped
    at August.
    """
    rows = page(
        orderList={
            "ordersV2": [
                {
                    "common": {"action": {"link": f"v2/cacheOrderProducts?data={index}"}},
                    "leftBlock": {
                        "textIcon": {
                            "text": {"text": f"Отменён {index} августа", "testInfo": {"automatizationId": "tileStatus"}}
                        }
                    },
                    "rightBlock": {
                        "products": {
                            "products": [
                                {
                                    "image": {
                                        "productMedia": {
                                            "common": {
                                                "action": {
                                                    "link": f"/my/orderdetails/?order=44563249-08{index}&postingId=1"
                                                }
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    },
                }
                for index in (10, 11)
            ]
        }
    )
    session.pages = {
        "/my/favorites/list": page(tileGridDesktop={"items": [{"sku": REFUSED_SKU}]}),
        "/my/orderdetails/": _order_page(_shipment("1", "Отменён", REFUSED_SKU, "Джоггеры")),
        "/my/orderlist": rows,
    }
    answer = catalog.bought_items(scan_orders=1)
    assert answer.provisional == [REFUSED_SKU]
    assert answer.unresolved == []
    # The bound stopped the scan, so an older receipt may still be out there.
    assert answer.complete is False
