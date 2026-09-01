"""Parse the wishlists page and the membership modal.

Two sources answering different halves of one question: the wishlists page names
every list with its id and count, while the ``favoritesListsSelect`` modal says
which of them a given product is in. Neither is complete on its own — the modal
drops the id of any list the product is already in.

Ozon's «Подборки» are *not* these lists: they live on ``/selections/list``, are
not created by the same action, and are not covered here.
"""

from __future__ import annotations

import re
from typing import Any

from ozon_mcp.models.lists import ListRef
from ozon_mcp.parsing.common import widgets_all
from ozon_mcp.utils.serde import dumps

# A card states its size in words — "8 подарков", or "Нет подарков" when empty,
# so the number is optional and its absence means none. The wording is also what
# separates a list card from the "create a new one" cell, which has no subtitle.
_COUNT_RE = re.compile(r"(?:(\d+)\s+)?(товар\w*|подарк\w*|подарок)")
_LIST_ID_RE = re.compile(r"[?&]list=(\d+)")
# A list the product is already in loses its add action and gets a tick instead.
_MEMBER_ICON = "ic_m_check_filled"
_ADD_ACTION = "favoriteListAdd"


def _cell_text(block: Any, key: str) -> str | None:
    node = block.get(key) if isinstance(block, dict) else None
    text = node.get("text") if isinstance(node, dict) else node
    return str(text).strip() or None if isinstance(text, str) else None


def _cell_body(cell: dict[str, Any]) -> dict[str, Any]:
    """A cell's payload, which Ozon nests under the cell's own type name."""
    body = cell.get(cell.get("type") or "") if isinstance(cell.get("type"), str) else None
    return body if isinstance(body, dict) else cell


def _cells(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _cell_body(cell)
        for state in widgets_all(data, "cellList")
        if isinstance(state, dict)
        for cell in state.get("cells") or []
        if isinstance(cell, dict)
    ]


def parse_wishlists(data: dict[str, Any]) -> list[ListRef]:
    """Wishlists from ``/my/favorites/lists``.

    Each card is one cell stating its own name and size — the name in
    ``centerBlock.title``, the size in ``centerBlock.subtitle`` — and linking to
    the list, id and all. A card with no subtitle is the "create a new one"
    cell, not a list.
    """
    out: list[ListRef] = []
    seen: set[str] = set()
    for body in _cells(data):
        center = body.get("centerBlock") if isinstance(body.get("centerBlock"), dict) else {}
        name = _cell_text(center, "title")
        count = _COUNT_RE.search(_cell_text(center, "subtitle") or "")
        if not name or count is None or name in seen:
            continue
        link = ((body.get("common") or {}).get("action") or {}).get("link") or ""
        found = _LIST_ID_RE.search(str(link))
        seen.add(name)
        out.append(
            ListRef(
                name=name,
                kind="wishlist",
                items=int(count.group(1)) if count.group(1) else 0,
                list_id=int(found.group(1)) if found else None,
            )
        )
    return out


def parse_list_membership(data: dict[str, Any]) -> dict[str, bool]:
    """Which lists a product is in, keyed by list name, from its own modal.

    Ozon marks a list the product is already in by taking its add action away
    and putting a tick where it was. Reading the actions alone — which is what
    this did — therefore returned exactly the lists the product was *not* in and
    silently dropped every list it was.
    """
    membership: dict[str, bool] = {}
    for body in _cells(data):
        center = body.get("centerBlock") if isinstance(body.get("centerBlock"), dict) else {}
        name = _cell_text(center, "title")
        if not name:
            continue
        right = dumps(body.get("rightBlock") or {})
        action = dumps((body.get("common") or {}).get("action") or {})
        if _MEMBER_ICON in right:
            membership[name] = True
        elif _ADD_ACTION in action:
            membership[name] = False
    return membership
