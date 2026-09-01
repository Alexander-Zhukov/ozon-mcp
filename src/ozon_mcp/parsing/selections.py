"""Parse the «Подборки» list into DTOs.

The page shell carries no selections: they arrive in a lazily fetched container
whose cells each state their own name, size, status and — in the link — both ids
needed to address the selection. That link is the only place the owner id
appears, and reading a selection without it answers "она удалена".
"""

import re
from typing import Any, Final

from ozon_mcp.models.lists import Selection
from ozon_mcp.parsing.common import widgets_all

# Both ids at once: the selection's own uuid and the owner's.
_VIEW_RE: Final = re.compile(r"/selections/view/([0-9a-f-]{36})\?uId=([0-9a-f-]{36})")
_ITEMS_RE: Final = re.compile(r"(\d+)\s+товар")


def _text(node: Any) -> str | None:
    if isinstance(node, dict):
        value = node.get("text")
        if isinstance(value, str):
            return str(value).strip() or None
    return None


def parse_selections(data: dict[str, Any]) -> list[Selection]:
    """Selections from the list container.

    The subtitle holds two things Ozon writes as one line — how many products
    are in it and where it stands ("2 товара • Личная подборка") — so the count
    is taken from it and the rest kept as the status verbatim. The cell that
    creates a new selection has no view link and is skipped by that.
    """
    out: list[Selection] = []
    seen: set[str] = set()
    for state in widgets_all(data, "cellList"):
        for cell in state.get("cells") or [] if isinstance(state, dict) else []:
            if not isinstance(cell, dict):
                continue
            body = cell.get(cell.get("type") or "") if isinstance(cell.get("type"), str) else None
            body = body if isinstance(body, dict) else cell
            link = str(((body.get("common") or {}).get("action") or {}).get("link") or "")
            found = _VIEW_RE.search(link)
            if found is None or found.group(1) in seen:
                continue
            center = body.get("centerBlock") if isinstance(body.get("centerBlock"), dict) else {}
            subtitle = _text(center.get("subtitle")) or ""
            count = _ITEMS_RE.search(subtitle)
            status = subtitle.split("•")[-1].strip() if "•" in subtitle else subtitle or None
            icon = ((body.get("leftBlock") or {}).get("icon") or {}) if isinstance(body.get("leftBlock"), dict) else {}
            seen.add(found.group(1))
            out.append(
                Selection(
                    uuid=found.group(1),
                    owner_id=found.group(2),
                    name=_text(center.get("title")),
                    items=int(count.group(1)) if count else 0,
                    status=status,
                    cover=icon.get("backgroundImage") if isinstance(icon, dict) else None,
                    link=link,
                )
            )
    return out
