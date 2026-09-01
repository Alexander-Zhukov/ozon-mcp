"""Finance services: card balance and points."""

from ozon_mcp.dependencies import get_session
from ozon_mcp.models.finance import Finances, Points
from ozon_mcp.parsing.finance import parse_finance, parse_points


def get_finances() -> Finances:
    return parse_finance(get_session().fetch("/my/main"))


def get_points() -> Points:
    return parse_points(get_session().fetch("/my/points"))
