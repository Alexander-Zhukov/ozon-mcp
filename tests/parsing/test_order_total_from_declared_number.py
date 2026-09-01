"""The order total is stated as a number, not only as a rendered caption."""

from __future__ import annotations

from ozon_mcp.parsing.checkout import parse_totals


def _total(*, caption: str | None, number: float | None) -> dict[str, object]:
    summary: dict[str, object] = {
        "prices": [{"left": {"title": "Товары (4)"}, "right": {"price": "20 441 ₽"}}],
        "footer": {"title": "Итого", "price": "2 152 ₽ сегодня"},
    }
    if caption:
        summary["footerPrices"] = [{"left": {"title": {"text": caption}}, "right": {"price": {"text": "6 691 ₽"}}}]
    state: dict[str, object] = {"summary": summary}
    if number is not None:
        state["totalPrice"] = number
    return state


def test_the_number_wins_over_the_caption() -> None:
    totals = parse_totals(_total(caption="Сумма всего заказа", number=6691))
    assert totals.total == "2 152 ₽ сегодня"
    assert totals.order_total == "6 691 ₽"


def test_a_reworded_caption_no_longer_loses_the_total() -> None:
    totals = parse_totals(_total(caption="Всего к оплате по заказу", number=6691))
    assert totals.order_total == "6 691 ₽"


def test_kopecks_survive() -> None:
    assert parse_totals(_total(caption=None, number=415.64)).order_total == "415,64 ₽"


def test_without_a_number_the_caption_is_still_read() -> None:
    assert parse_totals(_total(caption="Сумма всего заказа", number=None)).order_total == "6 691 ₽"
