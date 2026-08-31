"""Same-named widgets must be told apart by payload, not by position."""

from __future__ import annotations

import json

from ozon_mcp.parsing.common import widget_with


def _page(first: dict[str, object], second: dict[str, object]) -> dict[str, object]:
    # Two webDescription widgets, as a real product page ships them.
    return {
        "widgetStates": {
            "webDescription-1-pdpPage2column-2": json.dumps(first, ensure_ascii=False),
            "webDescription-2-pdpPage2column-2": json.dumps(second, ensure_ascii=False),
        }
    }


def test_widget_with_picks_by_content() -> None:
    characteristics = {"characteristics": [{"name": "Вес"}]}
    described = {"richAnnotation": "Описание товара"}

    # Either order must yield the described one.
    assert widget_with(_page(characteristics, described), "webDescription", "richAnnotation") == described
    assert widget_with(_page(described, characteristics), "webDescription", "richAnnotation") == described


def test_widget_with_returns_none_when_absent() -> None:
    assert widget_with({"widgetStates": {}}, "webDescription", "richAnnotation") is None
