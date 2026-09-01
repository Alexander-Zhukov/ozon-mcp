"""The destination cell states the address then, after a <br>, the storage term.

Deciding which half was which by looking for "хранение" broke on a courier
address, which has no storage term but does have a flat and a floor — and the
delivery mode came from recognising the words "Самовывоз"/"Курьером" instead of
the tag Ozon marks as selected.
"""

from __future__ import annotations

from ozon_mcp.parsing.checkout import parse_delivery


def _state(mode: str, title: str, subtitle: str) -> dict[str, object]:
    return {
        "dynamicElements": [
            {
                "type": "tagList",
                "tagList": {
                    "buttons": [
                        {
                            "text": "Курьером",
                            "isSelected": mode == "Курьером",
                            "common": {"action": {"link": "/modal/miniaddressbook?filter=courier"}},
                        },
                        {
                            "text": "Самовывоз",
                            "isSelected": mode == "Самовывоз",
                            "common": {"action": {"link": "/modal/miniaddressbook?filter=pickup"}},
                        },
                    ]
                },
            },
            {
                "type": "cell",
                "cell": {
                    "leftBlock": {"icon": {"icon": {"icon": "ic_m_location_pin_filled"}}},
                    "centerBlock": {"title": {"text": title}, "subtitle": {"text": subtitle}},
                },
            },
            {
                "type": "cell",
                "blockName": "address",
                "cell": {
                    "leftBlock": {"icon": {"icon": {"icon": "ic_m_tabbar_profile"}}},
                    "centerBlock": {"title": {"text": "Александр Жуков 79218628920"}},
                    "common": {"action": {"link": "/modal/editAddressAndRecipient?addrbookid=x"}},
                },
            },
        ]
    }


def test_a_pickup_point_keeps_its_storage_term_apart() -> None:
    delivery = parse_delivery(
        _state("Самовывоз", "Пункт Ozon", "Санкт-Петербург, Плесецкая ул., 14 <br><br>Срок хранения заказа — 14 дней")
    )
    assert delivery.mode == "Самовывоз"
    assert delivery.address == "Пункт Ozon, Санкт-Петербург, Плесецкая ул., 14"
    assert delivery.storage == "Срок хранения заказа — 14 дней"
    assert delivery.recipient == "Александр Жуков 79218628920"
    assert delivery.change_link is not None


def test_a_courier_address_has_no_storage_and_keeps_its_detail() -> None:
    delivery = parse_delivery(_state("Курьером", "Доставка по адресу", "Выборг, Ленинградское ш., 15 <br>кв. 27"))
    assert delivery.mode == "Курьером"
    assert delivery.address == "Доставка по адресу, Выборг, Ленинградское ш., 15"
    # The floor and flat are notes on the address, not a storage term.
    assert delivery.storage == "кв. 27"


def test_an_empty_widget_answers_empty() -> None:
    delivery = parse_delivery({})
    assert delivery.mode is None
    assert delivery.address is None
