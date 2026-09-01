"""Checkout totals live under `summary` and arrive wrapped in styled spans."""

from __future__ import annotations

from ozon_mcp.parsing.checkout import parse_totals


def test_parse_totals_strips_markup() -> None:
    totals = parse_totals({
        "summary": {
            "prices": [
                {
                    "left": {"title": '<span style="color: #070707;">Товары (4)</span>'},
                    "right": {"price": '<span style="color: #070707;">46 353 ₽</span>'},
                }
            ],
            "footer": {"title": "Итого", "price": "12 640 ₽ сегодня"},
        }
    })
    assert totals.total == "12 640 ₽ сегодня"
    assert totals.rows[0].title == "Товары (4)"
    assert totals.rows[0].value == "46 353 ₽"
