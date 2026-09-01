"""Parse the buyer's returns.

The returns page ships with no returns on it: they live in a container the page
fetches after itself, paginated, and what the page itself carries is the returns
FAQ. Reading the page and taking its titles therefore reported «Почему товар
недоступен для возврата?» as a return — and on an account that had returns, it
reported none of them.
"""

from __future__ import annotations

import re
from typing import Any, Final

from ozon_mcp.models.orders import Return, ReturnProduct
from ozon_mcp.parsing.common import widget
from ozon_mcp.parsing.orders import parse_ru_date

# The return addresses itself in the link to its own details.
_NUMBER_RE: Final = re.compile(r"returnNumber=([\w\-]+)")
_SKU_RE: Final = re.compile(r"/product/(?:[a-z0-9\-]+-)?(\d{6,})")
_TAG_RE: Final = re.compile(r"<[^>]+>")


def _plain(value: Any) -> str | None:
    """Ozon writes these sentences as HTML, non-breaking spaces and all."""
    if not isinstance(value, str):
        return None
    text = _TAG_RE.sub(" ", value).replace("&nbsp;", " ")
    return " ".join(text.split()) or None


def _text(node: Any) -> str | None:
    return _plain(node.get("text")) if isinstance(node, dict) else _plain(node)


def _products(total: dict[str, Any]) -> list[ReturnProduct]:
    out: list[ReturnProduct] = []
    for photo in total.get("itemPhotos") or []:
        if not isinstance(photo, dict):
            continue
        media = (
            ((photo.get("itemImage") or {}).get("productMedia") or {})
            if isinstance(photo.get("itemImage"), dict)
            else {}
        )
        link = str(((media.get("common") or {}).get("action") or {}).get("link") or "")
        found = _SKU_RE.search(link)
        out.append(ReturnProduct(sku=found.group(1) if found else None, title=_plain(photo.get("hint"))))
    return out


def parse_returns(data: dict[str, Any]) -> list[Return]:
    """Returns from the list container, one entry per application."""
    state = widget(data, "returnList") or {}
    out: list[Return] = []
    for item in (state.get("items") if isinstance(state, dict) else None) or []:
        if not isinstance(item, dict):
            continue
        header = item.get("header") if isinstance(item.get("header"), dict) else {}
        status = item.get("status") if isinstance(item.get("status"), dict) else {}
        total = item.get("total") if isinstance(item.get("total"), dict) else {}
        link = str(((item.get("common") or {}).get("action") or {}).get("link") or "")
        found = _NUMBER_RE.search(link)
        title = _text(header.get("newTitle")) or _text(header.get("title"))
        amount = next(
            (
                _plain(row.get("textRight"))
                for row in total.get("amountDetailing") or []
                if isinstance(row, dict) and row.get("textRight")
            ),
            None,
        )
        out.append(
            Return(
                number=found.group(1) if found else None,
                title=title,
                date=parse_ru_date(title),
                status=_text(status.get("badge")),
                detail=_text(status.get("description")),
                amount=amount,
                products=_products(total),
                link=link or None,
            )
        )
    return out
