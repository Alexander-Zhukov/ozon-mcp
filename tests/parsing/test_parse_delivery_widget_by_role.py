"""The delivery widget names the role of each section; the roles are resolved."""

from __future__ import annotations

from ozon_mcp.parsing.catalog import parse_delivery_widget


def _state() -> dict[str, object]:
    return {
        "sections": [
            {
                "type": "addressSelect",
                "descriptionRs": [
                    {"type": "text", "content": "ул. Данилова, 17"},
                    {"type": "newLine"},
                    {"type": "text", "content": "Со склада Ozon, Санкт-Петербург"},
                ],
                "trackingInfo": {"click": {"actionType": "click", "key": "KEY-MAIN"}},
            },
            {"type": "separator"},
            {
                "descriptionRs": [
                    {"type": "text", "content": "Пункты выдачи и постаматы"},
                    {"type": "newLine"},
                    {"type": "text", "content": "Завтра, 2 сентября"},
                ],
                "trackingInfo": {"click": {"actionType": "click", "key": "KEY-PVZ"}},
            },
        ],
        "cellTrackingInfo": {"uis": {"main": "KEY-MAIN", "pvz": "KEY-PVZ", "returnInfo": "KEY-RET"}},
        "returnInfo": {"text": "Можно вернуть в течение 7 дней"},
    }


def test_each_field_comes_from_the_section_ozon_named() -> None:
    read = parse_delivery_widget(_state())
    assert read == {
        "delivery": "Завтра, 2 сентября",
        "address": "ул. Данилова, 17",
        "source": "Со склада Ozon, Санкт-Петербург",
    }


def test_the_returns_line_is_not_mistaken_for_a_date() -> None:
    # It is a section role like any other, and it is excluded by name.
    state = _state()
    state["cellTrackingInfo"] = {"uis": {"main": "KEY-MAIN", "returnInfo": "KEY-PVZ"}}
    assert parse_delivery_widget(state)["delivery"] is None


def test_an_empty_widget_answers_empty() -> None:
    assert parse_delivery_widget({}) == {"delivery": None, "address": None, "source": None}
