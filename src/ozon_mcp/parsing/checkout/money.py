"""The money on the checkout: points to spend and the totals.

Two figures matter and they are not interchangeable: what Ozon charges today,
which is 0 ₽ on a deferred order, and what the order costs.
"""

import re
from typing import Any, Final

from ozon_mcp.models.checkout import PointsOption, TotalRow, Totals
from ozon_mcp.parsing.checkout.atoms import action_link, plain, text
from ozon_mcp.utils.money import KOPECKS, format_money

_POINTS_RE: Final = re.compile(r"points_applied=([\d.]+)")


_DIGITS_RE: Final = re.compile(r"\d+")


def parse_points(state: Any) -> list[PointsOption]:
    options: list[PointsOption] = []
    tabs = state.get("tabs") if isinstance(state, dict) else None
    entries = tabs.get("tabs") if isinstance(tabs, dict) else None
    selected_index = tabs.get("selectedTabIndex") if isinstance(tabs, dict) else None
    for index, tab in enumerate(entries or []):
        if not isinstance(tab, dict):
            continue
        label = text(tab.get("title")) or text(tab)
        common = tab.get("common") if isinstance(tab.get("common"), dict) else {}
        link = action_link(common)
        # The amount is in the link when Ozon offers one ("points_applied=100.00")
        # and only in the label otherwise ("Списать 100"); the two patterns
        # capture differently, so they are read apart rather than together.
        from_link = _POINTS_RE.search(link)
        from_label = _DIGITS_RE.search(label or "") if label else None
        amount = float(from_link.group(1)) if from_link else (float(from_label.group(0)) if from_label else None)
        options.append(
            PointsOption(
                label=label,
                amount=int(amount) if amount is not None else None,
                selected=index == selected_index,
                apply_link=link or None,
            )
        )
    return options


def parse_totals(state: Any) -> Totals:
    summary = state.get("summary") if isinstance(state, dict) else None
    summary = summary if isinstance(summary, dict) else {}
    rows: list[TotalRow] = []
    for row in summary.get("prices") or []:
        if not isinstance(row, dict):
            continue
        left, right = row.get("left") or {}, row.get("right") or {}
        title = plain(text(left.get("title")) or text(left))
        value = plain(text(right.get("price")) or text(right))
        if title or value:
            rows.append(TotalRow(title=title, value=value))
    footer_raw = summary.get("footer")
    footer: dict[str, Any] = footer_raw if isinstance(footer_raw, dict) else {}
    note = None
    order_total = None
    for row in summary.get("footerPrices") or []:
        if not isinstance(row, dict):
            continue
        left, right = row.get("left") or {}, row.get("right") or {}
        title = text(left.get("title"))
        price = plain(text(right.get("price")))
        note = " ".join(filter(None, (title, text(left.get("subtitle")), price)))
        # Ozon labels the whole-order figure separately from today's charge.
        if title and "всего заказа" in title.lower():
            order_total = price
    today = plain(text(footer.get("price")))
    # The same figure is stated as a number beside the rendered rows; preferring
    # it keeps the order total out of a caption Ozon is free to reword.
    declared = state.get("totalPrice") if isinstance(state, dict) else None
    if isinstance(declared, (int, float)) and not isinstance(declared, bool):
        order_total = format_money(round(declared * KOPECKS))
    return Totals(
        rows=rows,
        total=today,
        # With nothing deferred the two coincide, and Ozon prints only one.
        order_total=order_total or today,
        note=note or None,
    )
