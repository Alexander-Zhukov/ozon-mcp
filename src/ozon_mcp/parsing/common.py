"""Shared helpers for turning OZON ``widgetStates`` into DTOs.

composer-api returns a ``widgetStates`` map keyed by ``<widgetName>-<id>-...``;
each value is a JSON string of that widget's UI-shaped state. Extraction is
best-effort (deep search by key rather than fixed paths) so it survives layout
churn.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

PRICE_RE = re.compile(r"\d[\d\s\u00a0\u2009]*\s?₽")
PRICE_WITH_KOPECKS_RE = re.compile(r"\d[\d\s\u00a0\u2009]*,\d{2}\s?₽")
IMAGE_RE = re.compile(r"https://ir\.ozone\.ru/[^\"\\]+?\.(?:jpg|jpeg|png|webp)")


def widget(data: dict[str, Any], prefix: str) -> Any:
    """Parsed state of the first widget whose key starts with ``prefix``."""
    for state in widgets_all(data, prefix):
        return state
    return None


def widgets_all(data: dict[str, Any], prefix: str) -> list[Any]:
    """Parsed states of every widget whose key starts with ``prefix`` (e.g. each
    cartSplit — the cart is split across «доступны»/«недоступны»).
    """
    out: list[Any] = []
    for key, raw in (data.get("widgetStates") or {}).items():
        if key.split("-", 1)[0] == prefix or key.startswith(prefix):
            try:
                out.append(json.loads(raw) if isinstance(raw, str) else raw)
            except (ValueError, TypeError):
                continue
    return out


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def find_all(node: Any, key: str) -> list[Any]:
    """Every value stored under ``key`` anywhere in a nested structure."""
    return [d[key] for d in _walk(node) if isinstance(d, dict) and key in d]


def prices(node: Any) -> list[str]:
    return list(dict.fromkeys(PRICE_RE.findall(json.dumps(node, ensure_ascii=False))))


def next_page(data: dict[str, Any]) -> str | None:
    """Next scroll-page path. Prefers a paginator.nextPage; otherwise (favorites/
    purchases scroll) rebuilds it from pageInfo.url by advancing
    layout_page_index and swapping in the next embedded ``page=`` cursor token.
    """
    for state in widgets_all(data, "paginator"):
        if isinstance(state, dict) and state.get("nextPage"):
            return str(state["nextPage"])
    current = (data.get("pageInfo") or {}).get("url") or ""
    if "layout_page_index" not in current:
        return None
    current_token_match = re.search(r"[?&]page=(\d{6,})", current)
    current_token = current_token_match.group(1) if current_token_match else None
    index_match = re.search(r"layout_page_index=(\d+)", current)
    index = int(index_match.group(1)) if index_match else 1
    tokens = re.findall(r"[?&]page=(\d{6,})", json.dumps(data, ensure_ascii=False))
    next_token = next((t for t in tokens if t != current_token), None)
    if not next_token:
        return None
    url = re.sub(r"layout_page_index=\d+", f"layout_page_index={index + 1}", current)
    return re.sub(r"([?&]page=)\d+", rf"\g<1>{next_token}", url)
