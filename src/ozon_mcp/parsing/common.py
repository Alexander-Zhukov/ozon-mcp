"""Shared helpers for turning OZON ``widgetStates`` into DTOs.

composer-api returns a ``widgetStates`` map keyed by ``<widgetName>-<id>-...``;
each value is a JSON string of that widget's UI-shaped state. Extraction is
best-effort (deep search by key rather than fixed paths) so it survives layout
churn.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ozon_mcp.utils.serde import dumps, loads

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


def layout_widgets(data: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Every widget declared in the page layout, containers included.

    The layout is a tree: containers nest their children under
    ``placeholders[].widgets[]``, so a flat read of the top level misses most of
    the page.
    """

    def descend(entries: Any) -> Iterator[dict[str, Any]]:
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            yield entry
            for placeholder in entry.get("placeholders") or []:
                if isinstance(placeholder, dict):
                    yield from descend(placeholder.get("widgets"))

    return descend(data.get("layout"))


def state_by_layout(data: dict[str, Any], component: str, **params: str) -> Any:
    """The widget state whose *layout declaration* matches, by component and params.

    Ozon reuses one component name for different blocks and tells them apart in
    the layout, not in the payload: a product page declares two
    ``webDescription`` widgets, ``descriptionMode=full`` for the description and
    ``descriptionMode=characteristics`` for the specs table. Their order in
    ``widgetStates`` is not stable, so resolving the declared stateId is the
    only reliable way to get the one that was asked for.
    """
    states = data.get("widgetStates") or {}
    for entry in layout_widgets(data):
        if entry.get("component") != component:
            continue
        try:
            declared = loads(entry.get("params") or "{}")
        except (ValueError, TypeError):
            declared = {}
        if any(str(declared.get(key)) != value for key, value in params.items()):
            continue
        raw = states.get(entry.get("stateId"))
        if raw is None:
            continue
        try:
            return loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            return None
    return None


def widget_with(data: dict[str, Any], prefix: str, *keys: str) -> Any:
    """The instance of ``prefix`` that actually carries one of ``keys``.

    A page can ship several widgets under the same name with different payloads
    — a product page has two ``webDescription`` widgets, one holding the
    description and one holding characteristics — and their order in the
    response is not stable. Picking the first match therefore returns the wrong
    one at random; picking by content does not.
    """
    for state in widgets_all(data, prefix):
        if isinstance(state, dict) and any(state.get(key) for key in keys):
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
                out.append(loads(raw) if isinstance(raw, str) else raw)
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


def walk(node: Any) -> Iterator[dict[str, Any]]:
    """Every dict inside a nested structure, for callers that need whole nodes
    (an action link plus the title next to it) rather than one key.
    """
    return _walk(node)


def find_all(node: Any, key: str) -> list[Any]:
    """Every value stored under ``key`` anywhere in a nested structure."""
    return [d[key] for d in _walk(node) if isinstance(d, dict) and key in d]


def prices(node: Any) -> list[str]:
    return list(dict.fromkeys(PRICE_RE.findall(dumps(node))))


def continues_this_list(url: str) -> bool:
    """Whether a paginator's next page continues the list being read.

    A page carries a paginator per scrolling block, and one of those blocks is
    always "you might also like": the favorites page offers
    ``recoms_pagination_favorites_web`` beside the favorites cursor itself.
    Following the first paginator found therefore walked into recommendations
    and stopped there, which reads exactly like the end of the list — 39
    favorites came back as 20, and 12 of those 20 were not favorites at all.

    Only recommendation containers are excluded, and by name. The rest are the
    list: the cart continues through ``SplitInCartPaginator``, because its items
    are rendered as splits, so a stricter rule would truncate it instead.
    """
    container = re.search(r"layout_container=([^&]+)", url)
    return container is None or "recom" not in str(container.group(1)).lower()


def _rebuilt_next(data: dict[str, Any]) -> str | None:
    """The next scroll page rebuilt from ``pageInfo``.

    Favorites and purchases advertise no paginator past the first page: the
    cursor is a ``page=`` token embedded in the payload, and the next page is
    the current url with the index advanced and that token swapped in.
    """
    current = (data.get("pageInfo") or {}).get("url") or ""
    if "layout_page_index" not in current:
        return None
    current_token_match = re.search(r"[?&]page=(\d{6,})", current)
    current_token = current_token_match.group(1) if current_token_match else None
    index_match = re.search(r"layout_page_index=(\d+)", current)
    index = int(index_match.group(1)) if index_match else 1
    tokens = re.findall(r"[?&]page=(\d{6,})", dumps(data))
    next_token = next((token for token in tokens if token != current_token), None)
    if not next_token:
        return None
    url = re.sub(r"layout_page_index=\d+", f"layout_page_index={index + 1}", current)
    return re.sub(r"([?&]page=)\d+", rf"\g<1>{next_token}", url)


def next_pages(data: dict[str, Any]) -> list[str]:
    """Every way this list can continue, in a stable order.

    Two things make a single answer unreliable. Ozon shuffles the paginators
    between identical requests, so taking "the first one" is a coin toss — the
    cart came back with 38 items or with 4 depending on which of its two
    paginators happened to lead. And some lists advertise no paginator at all
    past the first page, continuing through a cursor rebuilt from ``pageInfo``.

    So the candidates are sorted for repeatability, with the rebuilt cursor last:
    a caller walks them in order and tries the next when one is a dead end.
    """
    offered = {
        str(state["nextPage"])
        for state in widgets_all(data, "paginator")
        if isinstance(state, dict) and state.get("nextPage")
    }
    candidates = sorted(url for url in offered if continues_this_list(url))
    rebuilt = _rebuilt_next(data)
    if rebuilt and rebuilt not in candidates:
        candidates.append(rebuilt)
    return candidates


def next_page(data: dict[str, Any]) -> str | None:
    """The most likely next scroll page of the list being read."""
    return next(iter(next_pages(data)), None)


def declared_count(data: dict[str, Any], *, tab: str) -> int | None:
    """How many entries Ozon says the list has.

    The page states it in its own header — the cart tab carries ``count`` — and
    that number is what tells a short read from a complete one: pages arrive
    four at a time and a walk that stops early looks exactly like a small cart.
    """
    for state in widgets_all(data, "header"):
        for node in walk(state):
            if node.get("name") == tab and isinstance(node.get("count"), int):
                return int(node["count"])
    return None


def declared_counter(data: dict[str, Any], widget_name: str) -> int | None:
    """A badge count, as the favorites and lists pages render it."""
    state = widget(data, widget_name) or {}
    for node in walk(state):
        counter = node.get("counter")
        text = counter.get("text") if isinstance(counter, dict) else None
        if isinstance(text, str) and text.strip().isdigit():
            return int(text.strip())
    return None
