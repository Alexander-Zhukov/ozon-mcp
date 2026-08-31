"""parse_ru_date resolves «DD month» to the current-year ISO date."""

from __future__ import annotations

import datetime

from ozon_mcp.parsing.orders import parse_ru_date


def test_parse_ru_date_current_year() -> None:
    year = datetime.date.today().year
    assert parse_ru_date("Получен 24 августа") == f"{year}-08-24"
