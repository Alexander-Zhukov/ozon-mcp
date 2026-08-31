"""Parse the favoritesListsSelect modal into list ids (для add/remove в списки)."""

from __future__ import annotations

from typing import Any

from ozon_mcp.models.lists import ListId
from ozon_mcp.parsing.common import find_all, widgets_all


def parse_lists(data: dict[str, Any]) -> list[ListId]:
    """List entries with id + name. The id lives in a favoriteListAdd/Remove
    action's ``params.id``; the name is a text atom in the same cell.
    """
    out: list[ListId] = []
    seen: set[str] = set()
    for state in widgets_all(data, "cellList"):
        for cell in _cells(state):
            actions = [
                d for d in _walk(cell) if isinstance(d, dict) and str(d.get("link", "")).startswith("favoriteList")
            ]
            if not actions:
                continue
            list_id = (actions[0].get("params") or {}).get("id")
            if not list_id or str(list_id) in seen:
                continue
            seen.add(str(list_id))
            names = [
                t
                for t in find_all(cell, "text")
                if isinstance(t, str) and 1 < len(t) < 30 and "подар" not in t and "товар" not in t
            ]
            out.append(ListId(id=int(list_id), name=names[0] if names else None))
    return out


def _cells(state: Any) -> list[Any]:
    return [c for cells in find_all(state, "cells") for c in cells]


def _walk(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        found.append(node)
        for value in node.values():
            found += _walk(value)
    elif isinstance(node, list):
        for value in node:
            found += _walk(value)
    return found
