"""A wishlist card states its name, its size and its id; all three are read from it.

Empty lists matter here: a list created a moment ago says "Нет подарков" instead
of a number, and requiring a number made a freshly created list invisible.
"""

from __future__ import annotations

from ozon_mcp.parsing.lists import parse_list_membership, parse_wishlists


def _cell(name: str, subtitle: str | None, link: str | None, *, member: bool = False) -> str:
    parts = [f'"title": {{"text": "{name}"}}']
    if subtitle is not None:
        parts.append(f'"subtitle": {{"text": "{subtitle}"}}')
    center = ", ".join(parts)
    common = f', "common": {{"action": {{"link": "{link}"}}}}' if link else ', "common": {}'
    right = ', "rightBlock": {"icon": {"icon": {"icon": "ic_m_check_filled"}}}' if member else ""
    return f'{{"type": "dsCell", "dsCell": {{"centerBlock": {{{center}}}{common}{right}}}}}'


def _page() -> dict[str, object]:
    return {
        "widgetStates": {
            # The "create a new one" card carries a name and no size.
            "cellList-1": '{{"cells": [{}]}}'.format(
                _cell("Новый вишлист", None, "/modal/favoritesCreate/?list_type=wishlist")
            ),
            "cellList-2": '{{"cells": [{}]}}'.format(
                _cell("Дом", "8 подарков", "/my/favorites/list?switchTab=false&list=1349700")
            ),
            "cellList-3": '{{"cells": [{}]}}'.format(
                _cell("Свежий", "Нет подарков", "/my/favorites/list?list=1360182")
            ),
        }
    }


def test_every_list_is_read_with_its_id_and_size() -> None:
    lists = parse_wishlists(_page())
    assert [(ref.name, ref.items, ref.list_id) for ref in lists] == [
        ("Дом", 8, 1349700),
        ("Свежий", 0, 1360182),
    ]
    assert {ref.kind for ref in lists} == {"wishlist"}


def test_the_create_card_is_not_a_list() -> None:
    assert "Новый вишлист" not in {ref.name for ref in parse_wishlists(_page())}


def test_membership_includes_the_lists_the_product_is_already_in() -> None:
    # Ozon takes the add action away and leaves a tick, so reading actions alone
    # returned exactly the lists the product was *not* in.
    modal = {
        "widgetStates": {
            "cellList-1": '{{"cells": [{}, {}]}}'.format(
                _cell("Дом", "9 подарков", None, member=True),
                _cell("Свежий", "Нет подарков", "favoriteListAdd"),
            )
        }
    }
    assert parse_list_membership(modal) == {"Дом": True, "Свежий": False}
