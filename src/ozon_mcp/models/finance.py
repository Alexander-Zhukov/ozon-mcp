"""Finance DTOs: card balance, points, seller bonuses."""

from __future__ import annotations

from ozon_mcp.models.base import OzonModel


class Finances(OzonModel):
    ozon_card_balance: str | None = None
    points: str | None = None


class PointType(OzonModel):
    """One point kind (Баллы Ozon / Мили / ВАУ-баллы / Звёзды)."""

    type: str | None = None
    name: str | None = None
    amount: str | None = None


class SellerBonus(OzonModel):
    seller: str
    amount: str | None = None


class SellerBonuses(OzonModel):
    total: int | None = None
    items: list[SellerBonus] = []


class Points(OzonModel):
    by_type: list[PointType] = []
    burning: list[str] = []
    seller_bonuses: SellerBonuses = SellerBonuses()
