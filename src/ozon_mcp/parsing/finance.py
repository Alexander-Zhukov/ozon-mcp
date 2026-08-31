"""Parse finance widgets into DTOs."""

from __future__ import annotations

import json
import re
from typing import Any

from ozon_mcp.models.finance import (
    Finances,
    Points,
    PointType,
    SellerBonus,
    SellerBonuses,
)
from ozon_mcp.parsing.common import PRICE_RE, PRICE_WITH_KOPECKS_RE, find_all, widget


def parse_finance(data: dict[str, Any]) -> Finances:
    """Ozon Card balance + total points, from /my/main (actionCards + menu)."""
    cards = json.dumps(widget(data, "actionCards") or {}, ensure_ascii=False)
    balance = PRICE_WITH_KOPECKS_RE.findall(cards) or PRICE_RE.findall(cards)
    all_widgets = json.dumps(data.get("widgetStates") or {}, ensure_ascii=False)
    points = re.search(r"Баллы и бонусы.{0,250}?(\d[\d\s  ]{2,}\d)", all_widgets)
    return Finances(
        ozon_card_balance=balance[0] if balance else None, points=re.sub(r"\D", "", points.group(1)) if points else None
    )


def parse_points(data: dict[str, Any]) -> Points:
    """Points by type + burning + per-store seller bonuses, from /my/points."""
    header = widget(data, "premiumBalanceHeader") or {}
    by_type = [
        PointType(type=item.get("type"), name=item.get("text"), amount=item.get("pointsAmount"))
        for item in (header.get("items") or [])
        if isinstance(item, dict)
    ]
    burning = [
        t
        for t in find_all(widget(data, "premiumAccountBurningPoints") or {}, "text")
        if isinstance(t, str) and re.search(r"сгор|бонус|балл", t)
    ][:6]
    seller = widget(data, "premiumSellerPointsBalance") or {}
    sellers: list[SellerBonus] = []
    for item in (seller.get("items") if isinstance(seller, dict) else None) or []:
        if not isinstance(item, dict):
            continue
        name = item.get("title")
        if isinstance(name, dict):
            name = name.get("text") or next(iter(find_all(name, "text")), None)
        if name:
            sellers.append(SellerBonus(seller=name, amount=item.get("pointsAmount") or item.get("amount")))
    return Points(
        by_type=by_type, burning=burning, seller_bonuses=SellerBonuses(total=seller.get("totalAmount"), items=sellers)
    )
