"""Finance services: card balance and points."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ozon_mcp.dependencies import get_session
from ozon_mcp.parsing.finance import parse_finance, parse_points

if TYPE_CHECKING:
    from ozon_mcp.models.finance import Finances, Points


def get_finances() -> Finances:
    return parse_finance(get_session().fetch("/my/main"))


def get_points() -> Points:
    return parse_points(get_session().fetch("/my/points"))
