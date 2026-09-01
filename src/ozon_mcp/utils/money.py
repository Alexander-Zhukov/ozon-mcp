"""Reading and writing the money amounts Ozon puts in its widgets.

Ozon states amounts two ways — rendered for people ("2 152 ₽", "415,64 ₽",
with thin and non-breaking spaces as the thousands separator) and as an integer
number of kopecks in action parameters. Anything that has to compare or subtract
them goes through kopecks, because the rendered form is not arithmetic.
"""

from __future__ import annotations

import re
from typing import Final

KOPECKS: Final = 100
_NOT_MONEY_RE: Final = re.compile(r"[^\d,]")
_SPACES: Final = (" ", " ", " ", " ")


def to_kopecks(text: str | None) -> int | None:
    """Kopecks in a rendered amount, or None when there is no number in it."""
    stripped = text or ""
    for space in _SPACES:
        stripped = stripped.replace(space, "")
    digits = _NOT_MONEY_RE.sub("", stripped)
    if not digits:
        return None
    whole, _, cents = digits.partition(",")
    return int(whole or 0) * KOPECKS + int((cents + "00")[:2])


def format_money(kopecks: int | None) -> str | None:
    """Kopecks rendered the way Ozon renders them, kopecks dropped when zero."""
    if kopecks is None:
        return None
    whole, cents = divmod(abs(kopecks), KOPECKS)
    sign = "-" if kopecks < 0 else ""
    grouped = f"{whole:,}".replace(",", " ")
    return f"{sign}{grouped} ₽" if not cents else f"{sign}{grouped},{cents:02d} ₽"
