"""Ozon stores a description either as HTML or as structured nodes."""

from __future__ import annotations

import json

from ozon_mcp.parsing.catalog import parse_description


def _page(state: dict[str, object]) -> dict[str, object]:
    return {"widgetStates": {"webDescription-1-pdpPage2column-2": json.dumps(state, ensure_ascii=False)}}


def test_parse_description_reads_plain_html() -> None:
    described = parse_description("1", _page({"richAnnotation": "Состав: пихта.<br/><br/>Хорошо горит."}))
    assert described.description == "Состав: пихта. Хорошо горит."


def test_parse_description_reads_structured_nodes() -> None:
    rich = {"content": ["Первый абзац описания", "Второй абзац описания"]}
    described = parse_description("2", _page({"richAnnotationJson": json.dumps(rich, ensure_ascii=False)}))
    assert described.description is not None
    assert "Первый абзац описания" in described.description


def test_parse_description_without_a_widget() -> None:
    assert parse_description("3", {"widgetStates": {}}).description is None
