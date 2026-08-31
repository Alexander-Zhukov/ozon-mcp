"""A «DD month» that would land in the future rolls back one year."""

from __future__ import annotations

import datetime

from ozon_mcp.parsing.orders import parse_ru_date


def test_parse_ru_date_future_rolls_back() -> None:
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    months = [
        "",
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ]
    text = f"Получен {tomorrow.day} {months[tomorrow.month]}"
    parsed = parse_ru_date(text)
    assert parsed is not None
    assert datetime.date.fromisoformat(parsed) <= today
