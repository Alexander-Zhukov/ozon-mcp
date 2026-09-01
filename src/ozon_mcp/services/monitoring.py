"""Favorites price monitoring: snapshot store + diff.

Building block for "watch my favorites and tell me when something drops":
persist a ``{sku: price}`` snapshot, compare a fresh one against the last, and
report drops/rises. Scheduling lives outside — this only computes the diff.
"""

import time
from typing import Any, Final

from ozon_mcp.models.lists import PriceChange, PriceDiff
from ozon_mcp.settings import get_settings
from ozon_mcp.utils.serde import dumps, loads

_MAX_SNAPSHOTS: Final = 50


def _load() -> dict[str, Any]:
    try:
        return loads(get_settings().monitor_store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"snapshots": [], "titles": {}}


def _save(history: dict[str, Any]) -> None:
    store = get_settings().monitor_store
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(dumps(history, indent=True), encoding="utf-8")


def diff(old: dict[str, int], new: dict[str, int], titles: dict[str, str]) -> PriceDiff:
    drops: list[PriceChange] = []
    rises: list[PriceChange] = []
    for sku, price in new.items():
        was = old.get(sku)
        if was and price and price != was:
            change = PriceChange(sku=sku, title=titles.get(sku), was=was, now=price, delta=price - was)
            (drops if price < was else rises).append(change)
    drops.sort(key=lambda c: c.delta)
    return PriceDiff(
        drops=drops, rises=rises, added=[s for s in new if s not in old], removed=[s for s in old if s not in new]
    )


def record(prices: dict[str, int], titles: dict[str, str]) -> PriceDiff:
    """Append a ``{sku: price}`` snapshot and return the diff vs the previous."""
    history = _load()
    snapshots = history.get("snapshots", [])
    previous = snapshots[-1]["prices"] if snapshots else {}
    live = {sku: price for sku, price in prices.items() if price}
    snapshots.append({"ts": int(time.time()), "prices": live})
    history["snapshots"] = snapshots[-_MAX_SNAPSHOTS:]
    stored_titles = history.get("titles", {})
    stored_titles.update({sku: title for sku, title in titles.items() if title})
    history["titles"] = stored_titles
    _save(history)
    return diff(previous, live, stored_titles)
