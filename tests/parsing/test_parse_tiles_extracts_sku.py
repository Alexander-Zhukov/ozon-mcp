"""parse_tiles pulls sku, title and price out of a product tile."""

from __future__ import annotations

import json

from ozon_mcp.parsing.catalog import parse_tiles


def _grid() -> dict[str, dict[str, str]]:
    grid = {
        "items": [
            {
                "action": {"link": "/product/sol-tabletirovannaya-489647252/"},
                "mainState": [{"atom": {"text": {"text": "Соль таблетированная 25 кг"}}}],
                "price": "1 650 ₽",
            }
        ]
    }
    return {"widgetStates": {"tileGridDesktop-1-default-1": json.dumps(grid, ensure_ascii=False)}}


def test_parse_tiles_extracts_sku() -> None:
    tiles = parse_tiles(_grid())
    assert len(tiles) == 1
    assert tiles[0].sku == "489647252"
    assert tiles[0].url == "https://www.ozon.ru/product/489647252/"
    assert "1" in (tiles[0].price or "")
