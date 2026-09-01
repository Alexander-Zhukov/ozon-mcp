"""Ozon Card balance and points."""

from ozon_mcp.dependencies import run_blocking
from ozon_mcp.mcp_server import mcp
from ozon_mcp.models.finance import Finances, Points
from ozon_mcp.services import finance


@mcp.tool()
async def get_finances() -> Finances:
    """Ozon Card balance and the total points. This balance is what a card
    payment draws on, so it is what decides whether pay_order() will need a
    top-up. Breakdown by point type → get_points().
    """
    return await run_blocking(finance.get_finances)


@mcp.tool()
async def get_points() -> Points:
    """Points by type (Ozon points, miles, WOW points, stars) with amounts,
    burning points, and per-store seller bonuses.
    """
    return await run_blocking(finance.get_points)
