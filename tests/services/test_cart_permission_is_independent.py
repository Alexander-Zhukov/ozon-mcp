"""Cart access must not authorize payments or unrelated account mutations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ozon_mcp.errors import OrdersDisabledError, OzonError, WritesDisabledError
from ozon_mcp.services import cart, checkout, favorites, orders, selections, session as session_service
from ozon_mcp.settings import OzonSettings
from support import FakeSession, page

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any


def _gates(
    monkeypatch: pytest.MonkeyPatch, *, cart_enabled: bool = False, writes: bool = False, ordering: bool = False
) -> None:
    settings = OzonSettings(enable_cart=cart_enabled, enable_writes=writes, enable_orders=ordering)
    for module in (cart, checkout, favorites, orders, selections, session_service):
        monkeypatch.setattr(module, "get_settings", lambda: settings)


@pytest.mark.parametrize(("cart_enabled", "writes"), [(True, False), (False, True)])
@pytest.mark.parametrize("quantity", [0, 2])
def test_cart_only_and_legacy_writes_allow_quantity_changes(
    monkeypatch: pytest.MonkeyPatch, session: FakeSession, *, cart_enabled: bool, writes: bool, quantity: int
) -> None:
    _gates(monkeypatch, cart_enabled=cart_enabled, writes=writes)
    session.pages["/cart"] = page(
        cartSplit={
            "cartItems": [
                {
                    "product": {"id": "123", "titleColumn": {"text": "Item"}},
                    "controls": {"quantity": {"current": quantity}},
                }
            ]
            if quantity
            else []
        }
    )
    assert cart.set_cart_quantity("123", quantity).ok is True
    assert session.performed == [("v2/addToCart", [{"id": 123, "quantity": quantity}])]


@pytest.mark.parametrize(("cart_enabled", "writes"), [(True, False), (False, True)])
def test_cart_selection_does_not_need_broad_writes(
    monkeypatch: pytest.MonkeyPatch, session: FakeSession, *, cart_enabled: bool, writes: bool
) -> None:
    _gates(monkeypatch, cart_enabled=cart_enabled, writes=writes)
    cart.select_cart_items(["123"], "add")
    assert session.posted == [
        ("/cart", {"name": "selectItems", "params": '{"mode":"MODE_SELECT_SPECIFIED","items":["123"]}'})
    ]


@pytest.mark.parametrize("ordering", [False, True])
@pytest.mark.parametrize(
    "mutate", [lambda: cart.set_cart_quantity("123", 1), lambda: cart.select_cart_items(mode="all")]
)
def test_cart_disabled_rejects_before_upstream_work(
    monkeypatch: pytest.MonkeyPatch, session: FakeSession, mutate: Callable[[], Any], *, ordering: bool
) -> None:
    _gates(monkeypatch, ordering=ordering)
    with pytest.raises(OzonError, match=r"\[cart_disabled\].*OZON_ENABLE_CART=1"):
        mutate()
    assert (session.fetched, session.performed, session.posted) == ([], [], [])


OTHER_MUTATIONS = [
    lambda: orders.pay_order("44563249-0900"),
    lambda: orders.cancel_order("44563249-0900"),
    lambda: checkout.configure_checkout(payment="СБП"),
    lambda: favorites.set_favorite("123"),
    lambda: favorites.create_list("List"),
    lambda: favorites.delete_list(1),
    lambda: favorites.set_list_membership("123", 1),
    lambda: selections.create_selection("List", "123"),
    lambda: selections.edit_selection("uuid", "List"),
    lambda: selections.set_selection_items("uuid", ["123"]),
    lambda: selections.add_to_selection("uuid", ["123"]),
    lambda: selections.remove_from_selection("uuid", ["123"]),
    lambda: selections.set_selection_public("uuid", public=True),
    lambda: selections.delete_selection("uuid"),
]


@pytest.mark.parametrize("mutate", OTHER_MUTATIONS)
@pytest.mark.parametrize("ordering", [False, True])
def test_cart_or_order_permission_never_authorizes_other_mutations(
    monkeypatch: pytest.MonkeyPatch, session: FakeSession, mutate: Callable[[], Any], *, ordering: bool
) -> None:
    _gates(monkeypatch, cart_enabled=True, ordering=ordering)
    with pytest.raises(WritesDisabledError):
        mutate()
    assert (session.fetched, session.performed, session.posted) == ([], [], [])


def test_cart_permission_never_authorizes_order_placement(
    monkeypatch: pytest.MonkeyPatch, session: FakeSession
) -> None:
    _gates(monkeypatch, cart_enabled=True)
    with pytest.raises(OrdersDisabledError):
        checkout.place_order("100 ₽")
    assert (session.fetched, session.performed, session.posted) == ([], [], [])


@pytest.mark.parametrize(
    ("cart_enabled", "writes", "expected"), [(False, False, False), (True, False, True), (False, True, True)]
)
@pytest.mark.parametrize("user", [None, "44563249"])
def test_status_reports_effective_cart_permission(
    monkeypatch: pytest.MonkeyPatch,
    session: FakeSession,
    *,
    cart_enabled: bool,
    writes: bool,
    expected: bool,
    user: str | None,
) -> None:
    _gates(monkeypatch, cart_enabled=cart_enabled, writes=writes)
    monkeypatch.setattr(session, "signed_in_user", lambda: user)
    status = session_service.session_status()
    assert status.cart_enabled is expected
    assert status.writes_enabled is writes
    assert status.orders_enabled is False


@pytest.mark.parametrize("accepted", [False, True])
def test_login_keeps_the_cart_only_permission_visible(
    monkeypatch: pytest.MonkeyPatch, session: FakeSession, *, accepted: bool
) -> None:
    _gates(monkeypatch, cart_enabled=True)
    monkeypatch.setattr(session, "complete_login", lambda _code: accepted, raising=False)
    status = session_service.submit_login_code("123456")
    assert status.signed_in is accepted
    assert status.cart_enabled is True
    assert status.writes_enabled is False
    assert status.orders_enabled is False


def test_checkout_configuration_still_works_with_broad_writes(
    monkeypatch: pytest.MonkeyPatch, session: FakeSession
) -> None:
    _gates(monkeypatch, writes=True)
    assert checkout.configure_checkout().available is False
    assert session.fetched
