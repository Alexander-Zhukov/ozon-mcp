"""Returns are not on the returns page: the page carries the returns FAQ.

Reading it and taking its titles reported «Почему товар недоступен для возврата?»
as a return, and on an account with 36 returns it reported none of them.
"""

from __future__ import annotations

import json

from ozon_mcp.parsing.returns import parse_returns

NUMBER = "44563249-R37"


def _container() -> dict[str, object]:
    item = {
        "header": {"newTitle": {"text": "Заявка от 15 июня"}},
        "status": {
            "badge": {"text": "Деньги отправлены"},
            "description": {
                "text": 'Вернули их&nbsp;на&nbsp;ваш&nbsp;счёт. <a href="https://finance.ozon.ru/chat">поддержку</a>'
            },
        },
        "total": {
            "amountDetailing": [{"textLeft": "Сумма", "textRight": "5 654,00 ₽"}],
            "itemPhotos": [
                {
                    "hint": "Сервиз обеденный 16 предм. на 4 перс.",
                    "itemImage": {
                        "productMedia": {"common": {"action": {"link": "/product/1901653162"}}},
                    },
                }
            ],
        },
        "common": {"action": {"link": f"/my/returnDetails?returnNumber={NUMBER}"}},
    }
    return {"widgetStates": {"returnList-1": json.dumps({"items": [item]}, ensure_ascii=False)}}


def test_a_return_is_read_with_everything_it_states() -> None:
    entry = parse_returns(_container())[0]
    assert entry.number == NUMBER
    assert entry.title == "Заявка от 15 июня"
    assert entry.date == "2026-06-15"
    assert entry.status == "Деньги отправлены"
    assert entry.amount == "5 654,00 ₽"
    assert entry.products[0].sku == "1901653162"
    assert entry.products[0].title == "Сервиз обеденный 16 предм. на 4 перс."


def test_the_status_sentence_is_plain_text() -> None:
    # Ozon writes it as HTML with non-breaking spaces and a support link.
    entry = parse_returns(_container())[0]
    assert entry.detail == "Вернули их на ваш счёт. поддержку"


def test_a_page_without_returns_is_empty_not_an_error() -> None:
    assert parse_returns({}) == []
    assert (
        parse_returns({"widgetStates": {"returnCreationFaq-1": '{"items": [{"header": {"text": "Почему?"}}]}'}}) == []
    )
