"""Ozon distinguishes same-named widgets in the layout, not in the payload."""

from __future__ import annotations

import json

from ozon_mcp.parsing.catalog import parse_description
from ozon_mcp.parsing.common import state_by_layout


def _page() -> dict[str, object]:
    # A product page declares two webDescription widgets and their order in
    # widgetStates is not stable — here the specs table comes first.
    return {
        "layout": [
            {
                "component": "container",
                "placeholders": [
                    {
                        "widgets": [
                            {
                                "component": "webDescription",
                                "params": json.dumps({"descriptionMode": "characteristics"}),
                                "stateId": "webDescription-1-pdpPage2column-2",
                            },
                            {
                                "component": "webDescription",
                                "params": json.dumps({"descriptionMode": "full"}),
                                "stateId": "webDescription-2-pdpPage2column-2",
                            },
                        ]
                    }
                ],
            }
        ],
        "widgetStates": {
            "webDescription-1-pdpPage2column-2": json.dumps({"characteristics": [{"title": "Вес"}]}),
            "webDescription-2-pdpPage2column-2": json.dumps({"richAnnotation": "Настоящее описание"}),
        },
    }


def test_state_by_layout_resolves_declared_widget() -> None:
    state = state_by_layout(_page(), "webDescription", descriptionMode="full")
    assert state == {"richAnnotation": "Настоящее описание"}


def test_parse_description_uses_the_declared_widget() -> None:
    assert parse_description("1", _page()).description == "Настоящее описание"


def test_state_by_layout_without_a_match() -> None:
    assert state_by_layout(_page(), "webDescription", descriptionMode="nope") is None
