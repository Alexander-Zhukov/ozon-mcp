"""The small shapes every checkout widget is built from.

Ozon writes a caption as either a bare string or a ``{"text": …}`` atom, wraps
prices in styled spans, and hangs an action either on a node or under its
``common`` — so these three readings are shared rather than repeated.
"""

import re
from typing import Any, Final


def text(node: Any) -> str | None:
    """Text of a node that may be a bare string or a ``{"text": …}`` atom."""
    if isinstance(node, str):
        return str(node).strip() or None
    if isinstance(node, dict):
        value = node.get("text")
        if isinstance(value, str):
            return str(value).strip() or None
    return None


def plain(value: str | None) -> str | None:
    """Ozon wraps checkout titles and prices in styled spans."""
    if value is None:
        return None
    return " ".join(TAG_RE.sub(" ", value).split()) or None


def action_link(node: dict[str, Any]) -> str:
    """The link of a node's action, wherever Ozon hung it.

    Rows put their action directly on the node; controls inside a row put it
    under ``common``. Checking only one of the two reads as "no action" and
    makes a control silently do nothing.
    """
    for holder in (node, node.get("common") if isinstance(node.get("common"), dict) else {}):
        action = holder.get("action") if isinstance(holder, dict) else None
        link = action.get("link") if isinstance(action, dict) else None
        if isinstance(link, str) and link:
            return link
    return ""


TAG_RE: Final = re.compile(r"<[^>]+>")


BR_RE: Final = re.compile(r"<br\s*/?>", re.IGNORECASE)
