"""The cart arrives four items at a time, behind more than one paginator.

Ozon shuffles them between identical requests, so the walk tries each and keeps
going until it has as many items as the cart says it holds. Without that the
same call answered 38 items or 4.
"""

from __future__ import annotations

import pytest

from ozon_mcp.errors import WritesDisabledError
from ozon_mcp.services import cart
from ozon_mcp.utils.serde import dumps
from support import FakeSession, page


def _split(*ids: str) -> dict[str, object]:
    """One cartSplit widget, shaped as Ozon serves it."""
    return {
        "header": {"text": "Доступны для заказа"},
        "cartItems": [
            {
                "product": {
                    "id": sku,
                    "titleColumn": {"text": f"Товар номер {sku}"},
                    "priceColumn": {"price": "100 ₽"},
                },
                "controls": {"quantity": {"current": 1, "maximum": 5}},
                "checkbox": {"isChecked": True},
            }
            for sku in ids
        ],
    }


def _cart_page(ids: list[str], *, declared: int, paginators: list[str]) -> dict[str, object]:
    served = page(cartSplit=_split(*ids))
    served["widgetStates"]["header-1-default-1"] = dumps({
        "tabs": [{"name": "Избранное", "count": 0}, {"name": "Корзина", "count": declared, "quantity": declared}]
    }).replace('"declared"', str(declared))
    for index, url in enumerate(paginators):
        served["widgetStates"][f"paginator-{index}-default-1"] = f'{{"nextPage": "{url}", "size": 4}}'
    return served


SIDE = "/cart?layout_container=recoms_cart&layout_page_index=2"
OWN = "/cart?layout_container=SplitInCartPaginator&layout_page_index=1"


def test_the_walk_continues_until_the_cart_is_whole(session: FakeSession) -> None:
    session.pages = {
        OWN: _cart_page(["3", "4"], declared=4, paginators=[]),
        "/cart": _cart_page(["1", "2"], declared=4, paginators=[SIDE, OWN]),
    }
    whole = cart.get_cart()
    assert whole.total_items == 4
    assert whole.item_count == 4
    assert [item.id for item in whole.items] == ["1", "2", "3", "4"]


def test_a_recommendation_paginator_is_never_followed(session: FakeSession) -> None:
    session.pages = {"/cart": _cart_page(["1"], declared=1, paginators=[SIDE])}
    cart.get_cart()
    assert SIDE not in session.fetched


def test_a_write_without_the_gate_is_refused_before_anything_is_sent(session: FakeSession) -> None:
    with pytest.raises(WritesDisabledError):
        cart.set_cart_quantity("1", 1)
    assert session.performed == []


def test_a_quantity_that_did_not_take_is_reported(session: FakeSession, writes_on: None) -> None:
    session.pages = {"/cart": _cart_page(["1"], declared=1, paginators=[])}
    outcome = cart.set_cart_quantity("999", 2)
    assert outcome.ok is False
    assert "999" in (outcome.detail or "")


def test_selecting_items_says_what_it_asked_for(session: FakeSession, writes_on: None) -> None:
    session.pages = {"/cart": _cart_page(["1"], declared=1, paginators=[])}
    cart.select_cart_items(["1", "2"], "only")
    path, body = session.posted[0]
    assert path == "/cart"
    assert body["name"] == "selectItems"
    # "only" is Ozon's MODE_SELECT_SPECIFIED: order exactly these.
    assert "MODE_SELECT_SPECIFIED" in body["params"]
    assert '"1","2"' in body["params"].replace(" ", "")
