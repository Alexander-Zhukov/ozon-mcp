"""parse_points breaks the balance down by point type."""

from __future__ import annotations

import json

from ozon_mcp.parsing.finance import parse_points


def _points() -> dict[str, dict[str, str]]:
    header = {
        "items": [
            {"text": "Баллы Ozon", "type": "ozon", "pointsAmount": "100"},
            {"text": "Мили Ozon", "type": "miles", "pointsAmount": "1 000"},
        ]
    }
    seller = {"totalAmount": 2, "items": [{"title": "LOFT52", "pointsAmount": "1294"}]}
    return {
        "widgetStates": {
            "premiumBalanceHeader-1-default-1": json.dumps(header, ensure_ascii=False),
            "premiumSellerPointsBalance-1-default-1": json.dumps(seller, ensure_ascii=False),
        }
    }


def test_parse_points_by_type() -> None:
    points = parse_points(_points())
    assert {p.type for p in points.by_type} == {"ozon", "miles"}
    assert points.seller_bonuses.total == 2
    assert points.seller_bonuses.items[0].seller == "LOFT52"
