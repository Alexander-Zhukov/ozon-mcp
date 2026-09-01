"""A page paginates per block, and the blocks are not the same list.

Taking "the first paginator" walked into recommendations and stopped, which
reads exactly like the end of a list: 39 favorites came back as 20, twelve of
them not favorites. And because Ozon shuffles the paginators between identical
requests, the same cart call answered 38 items or 4.
"""

from __future__ import annotations

import json

from ozon_mcp.parsing.common import continues_this_list, declared_count, declared_counter, next_pages

FAVORITES_OWN = "/my/favorites?layout_container=default&layout_page_index=2&page=112623456"
FAVORITES_RECOMS = "/my/favorites?layout_container=recoms_pagination_favorites_web&layout_page_index=2"
CART_OWN = "/cart?layout_container=SplitInCartPaginator&layout_page_index=1&pos=0"
CART_CURSOR = "/cart?layout_page_index=2&paginator_token=11722823"


def test_recommendation_blocks_are_not_this_list() -> None:
    assert continues_this_list(FAVORITES_RECOMS) is False
    assert continues_this_list(FAVORITES_OWN) is True
    # The cart's own items are rendered as splits, so its container stays.
    assert continues_this_list(CART_OWN) is True
    assert continues_this_list(CART_CURSOR) is True


def _page(*paginators: str, page_info: str | None = None, cursor: str | None = None) -> dict[str, object]:
    states = {f"paginator-{index}": json.dumps({"nextPage": url, "size": 10}) for index, url in enumerate(paginators)}
    data: dict[str, object] = {"widgetStates": states}
    if page_info:
        data["pageInfo"] = {"url": page_info}
    if cursor:
        data["cursor"] = f"?page={cursor}"
    return data


def test_the_choice_does_not_depend_on_the_order_ozon_sent() -> None:
    one = next_pages(_page(CART_OWN, CART_CURSOR))
    other = next_pages(_page(CART_CURSOR, CART_OWN))
    assert one == other
    assert len(one) == 2


def test_recommendations_are_dropped_from_the_candidates() -> None:
    assert next_pages(_page(FAVORITES_RECOMS, FAVORITES_OWN)) == [FAVORITES_OWN]


def test_a_rebuilt_cursor_is_offered_last() -> None:
    # Favorites advertise no paginator past the first page; the cursor is a
    # token in the payload, and dropping that fallback stopped the walk at 16.
    data = _page(page_info="/my/favorites?layout_page_index=2&page=111111111", cursor="222222222")
    assert next_pages(data) == ["/my/favorites?layout_page_index=3&page=222222222"]

    both = _page(FAVORITES_OWN, page_info="/my/favorites?layout_page_index=2&page=111111111", cursor="222222222")
    assert next_pages(both)[0] == FAVORITES_OWN
    assert len(next_pages(both)) == 2


def test_a_list_states_its_own_size() -> None:
    header = {"widgetStates": {"header-1": json.dumps({"tabs": [{"name": "Корзина", "count": 38, "quantity": 58}]})}}
    assert declared_count(header, tab="Корзина") == 38
    assert declared_count(header, tab="Избранное") is None
    assert declared_count({}, tab="Корзина") is None


def test_a_badge_counter_is_read() -> None:
    page = {"widgetStates": {"favoriteCounter-1": json.dumps({"iconHeader": {"counter": {"text": "39"}}})}}
    assert declared_counter(page, "favoriteCounter") == 39
    assert declared_counter({}, "favoriteCounter") is None
