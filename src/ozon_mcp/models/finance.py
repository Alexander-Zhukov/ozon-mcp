"""Finance DTOs: card balance, points, seller bonuses."""

from __future__ import annotations

from pydantic import field_validator

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
    """Bonus points a particular store granted.

    Ozon sends the amount as a number here and as a formatted string elsewhere,
    so it is coerced to text rather than rejected.
    """

    seller: str
    amount: str | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def _as_text(cls, value: object) -> object:
        return str(value) if isinstance(value, (int, float)) else value


class SellerBonuses(OzonModel):
    total: int | None = None
    items: list[SellerBonus] = []


class Points(OzonModel):
    by_type: list[PointType] = []
    burning: list[str] = []
    seller_bonuses: SellerBonuses = SellerBonuses()
