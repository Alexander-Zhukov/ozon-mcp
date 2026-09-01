"""Parse the favoritesListsSelect modal into list ids (для add/remove в списки)."""

from __future__ import annotations

import re
from typing import Any

from ozon_mcp.models.lists import ListId, ListRef
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


# Ozon counts a collection in товары and a wishlist in подарки — that wording is
# the only thing on this page that distinguishes the two kinds.
_COUNT_RE = re.compile(r"(\d+)\s+(товар\w*|подарк\w*|подарок)")
_LIST_ID_RE = re.compile(r"[?&]list=(\d+)")


def _cell_text(block: Any, key: str) -> str | None:
    node = block.get(key) if isinstance(block, dict) else None
    text = node.get("text") if isinstance(node, dict) else node
    return str(text).strip() or None if isinstance(text, str) else None


def parse_list_page(data: dict[str, Any], *, wishlists: bool) -> list[ListRef]:
    """Collections or wishlists from ``/my/favorites/lists``.

    Each card is one cell that states its own name and count — the name in
    ``centerBlock.title``, the count in ``centerBlock.subtitle`` — and links to
    the list, id and all. Reading the cell means the two never have to be paired
    by their position in a flattened list of every string on the page.
    """
    out: list[ListRef] = []
    seen: set[str] = set()
    for state in widgets_all(data, "cellList"):
        for cell in state.get("cells") or [] if isinstance(state, dict) else []:
            if not isinstance(cell, dict):
                continue
            body = cell.get(cell.get("type") or "") if isinstance(cell.get("type"), str) else None
            body = body if isinstance(body, dict) else cell
            center = body.get("centerBlock") if isinstance(body.get("centerBlock"), dict) else {}
            name = _cell_text(center, "title")
            count = _COUNT_RE.search(_cell_text(center, "subtitle") or "")
            if not name or count is None or name in seen:
                continue
            if count.group(2).startswith("подар") is not wishlists:
                continue
            link = ((body.get("common") or {}).get("action") or {}).get("link") or ""
            found = _LIST_ID_RE.search(str(link))
            seen.add(name)
            out.append(ListRef(name=name, items=int(count.group(1)), list_id=int(found.group(1)) if found else None))
    return out
