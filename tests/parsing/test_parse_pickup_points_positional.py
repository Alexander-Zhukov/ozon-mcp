"""Address-book entries state their lines in order, and numberPVZ marks a point."""

from __future__ import annotations

from ozon_mcp.parsing.checkout import parse_delivery, parse_pickup_points


def _entry(title: str, lines: list[str], *, number: str | None, enabled: bool = True) -> dict[str, object]:
    entry: dict[str, object] = {
        "addressBookId": f"id-{title}",
        "title": {"text": title},
        "isEnabled": enabled,
        "isSelected": False,
        "elements": [{"text": line} for line in lines],
        "bottomElements": [],
        "webControls": [{"action": {"link": f"/gocheckout?address_book_id=id-{title}"}}],
    }
    if number:
        entry["numberPVZ"] = {
            "number": {"text": "№ 144-94-60"},
            "common": {"action": {"id": "copyText", "params": {"clipboardText": number}}},
        }
    return entry


def test_a_pickup_point_keeps_address_and_storage_apart() -> None:
    state = {
        "addresses": [
            _entry("Пункт Ozon", ["Выборг, ул. Данилова, 17", "Срок хранения заказа – 14 дней"], number="1449460")
        ]
    }
    point = parse_pickup_points(state)[0]
    assert point.title == "Пункт Ozon"
    assert point.address == "Выборг, ул. Данилова, 17"
    assert point.storage == "Срок хранения заказа – 14 дней"
    assert point.number == "1449460"


def test_a_courier_address_spans_its_lines_and_has_no_number() -> None:
    state = {
        "addresses": [
            _entry(
                "Доставка по адресу",
                ["Выборг, Ленинградское ш., 15", "кв./офис 27, этаж 2", "Жуков Александр, +7 921 862 89 20"],
                number=None,
            )
        ]
    }
    point = parse_pickup_points(state)[0]
    assert point.address == "Выборг, Ленинградское ш., 15, кв./офис 27, этаж 2, Жуков Александр, +7 921 862 89 20"
    assert point.number is None
    # Storage is a pickup-point notion; a courier address has none.
    assert point.storage is None


def test_recipient_comes_from_the_row_that_edits_it() -> None:
    # The old shape test ("two capitalised words then digits") missed anything
    # that is not a plain Russian first name and surname.
    state = {
        "items": [
            {
                "cell": {
                    "centerBlock": {"title": {"text": "Anna-Maria O'Brien 79218628920"}},
                    "common": {"action": {"link": "/modal/editAddressAndRecipient?addrbookid=x"}},
                }
            }
        ]
    }
    assert parse_delivery(state).recipient == "Anna-Maria O'Brien 79218628920"
