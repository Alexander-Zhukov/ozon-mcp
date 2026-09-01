"""Cancelling part of an order means finding the right line to tick."""

from __future__ import annotations

from ozon_mcp.services.orders import _postings


def _modal() -> dict[str, object]:
    # The real modal mixes the select-all row and the shipment in with the lines.
    return {
        "title": "Выберите товары для отмены",
        "items": [
            {"type": "selectAll", "selectAll": {"title": "Выбрать всё"}},
            {
                "type": "shipment",
                "shipment": {
                    "title": "2 сентября",
                    "action": {"params": {"Current": "43470406961"}},
                },
            },
            {
                "type": "monoposting",
                "monoposting": {
                    "title": "656 ₽",
                    "subtitle": "Салфетки для уборки в рулоне, тряпки для кухни",
                    "action": {"params": {"Current": "44563249-0877-1"}},
                },
            },
            {
                "type": "monoposting",
                "monoposting": {
                    "title": "121 ₽",
                    "subtitle": "Таблетница на день 3 приема органайзер",
                    "action": {"params": {"Current": "44563249-0877-2"}},
                },
            },
        ],
    }


def test_postings_lists_only_the_product_lines() -> None:
    lines = _postings(_modal())
    assert [pid for pid, _ in lines] == ["44563249-0877-1", "44563249-0877-2"]
    assert lines[0][1].startswith("Салфетки")


def test_postings_without_items() -> None:
    assert _postings({}) == []
