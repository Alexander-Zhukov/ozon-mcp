"""Parse cart widgets into DTOs."""

from __future__ import annotations

from typing import Any

from ozon_mcp.models.cart import Cart, CartItem
from ozon_mcp.parsing.common import find_all, prices, widgets_all


def parse_cart(data: dict[str, Any]) -> Cart:
    """Cart items aggregated across all cartSplit widgets (available /
    unavailable / by-seller).
    """
    items: list[CartItem] = []
    for state in widgets_all(data, "cartSplit"):
        for entry in (state.get("cartItems") if isinstance(state, dict) else None) or []:
            product = entry.get("product") or {}
            controls = entry.get("controls") or {}
            quantity = controls.get("quantity") or {}
            texts = [t for t in find_all(product.get("titleColumn") or {}, "text") if isinstance(t, str)]
            title = max((t for t in texts if len(t) > 6), key=len, default=None)
            found = prices(product.get("priceColumn") or {})
            items.append(
                CartItem(
                    id=product.get("id"),
                    title=title,
                    price=found[0] if found else None,
                    quantity=quantity.get("current"),
                    max_quantity=quantity.get("maximum"),
                    checked=(entry.get("checkbox") or {}).get("isChecked"),
                    is_favorite=(controls.get("favoriteToggle") or {}).get("isFavorite"),
                )
            )
    return Cart(items=items, item_count=len(items))
