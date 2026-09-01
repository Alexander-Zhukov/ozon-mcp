"""Parse finance widgets into DTOs."""

import re
from typing import Any, Final

from ozon_mcp.models.finance import (
    Finances,
    Points,
    PointType,
    SellerBonus,
    SellerBonuses,
)
from ozon_mcp.parsing.common import find_all, widget

_BALANCE_ACTION: Final = "BankBalance"
_POINTS_LINK: Final = "/my/points"


def _atom(node: Any) -> str | None:
    """Text of a value that may be a bare string or a ``{"text": …}`` atom."""
    if isinstance(node, str):
        return str(node).strip() or None
    if isinstance(node, dict):
        text = node.get("text")
        if isinstance(text, str):
            return str(text).strip() or None
        if isinstance(text, dict):
            return _atom(text)
    return None


def _card_balance(data: dict[str, Any]) -> str | None:
    """The Ozon Card balance, taken from the card that states it.

    ``actionCards`` is a row of tiles and any of them may carry a price — a
    cashback teaser, a credit-card offer. Taking the first money-looking string
    in the widget therefore reads whichever tile Ozon happens to put first. The
    balance tile names itself in its tracking action (``…_BankBalanceCard``),
    and that is what is matched.
    """
    cards = widget(data, "actionCards") or {}
    for card in (cards.get("cards") if isinstance(cards, dict) else None) or []:
        if not isinstance(card, dict):
            continue
        tracking = card.get("trackingInfo") if isinstance(card.get("trackingInfo"), dict) else {}
        actions = [str(entry.get("actionType") or "") for entry in tracking.values() if isinstance(entry, dict)]
        if any(_BALANCE_ACTION in action for action in actions):
            return _atom(card.get("subtitle"))
    return None


def _points_total(data: dict[str, Any]) -> str | None:
    """The points balance from the menu entry that links to the points page.

    Ozon hangs the number on that entry as a notification badge. Anchoring on
    the link instead of the caption keeps this out of a text window that used to
    be searched across every widget on the page.
    """
    menu = widget(data, "menu") or {}
    for section in (menu.get("sections") if isinstance(menu, dict) else None) or []:
        for item in (section.get("items") if isinstance(section, dict) else None) or []:
            if not isinstance(item, dict):
                continue
            action = item.get("action") if isinstance(item.get("action"), dict) else {}
            if str(action.get("link") or "").rstrip("/") != _POINTS_LINK:
                continue
            badge = item.get("notification") if isinstance(item.get("notification"), dict) else {}
            digits = re.sub(r"\D", "", _atom(badge.get("text")) or "")
            return digits or None
    return None


def parse_finance(data: dict[str, Any]) -> Finances:
    """Ozon Card balance + total points, from /my/main (actionCards + menu)."""
    return Finances(ozon_card_balance=_card_balance(data), points=_points_total(data))


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
