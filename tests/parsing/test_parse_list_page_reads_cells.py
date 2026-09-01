"""A list card states its name, its count and its id; all three are read from it."""

from __future__ import annotations

from ozon_mcp.parsing.lists import parse_list_page


def _cell(name: str, subtitle: str, link: str | None) -> str:
    common = f', "common": {{"action": {{"link": "{link}"}}}}' if link else ""
    return (
        f'{{"type": "dsCell", "dsCell": {{"centerBlock": {{"title": {{"text": "{name}"}},'
        f' "subtitle": {{"text": "{subtitle}"}}}}{common}}}}}'
    )


def _page() -> dict[str, object]:
    return {
        "widgetStates": {
            # The "create a new one" card has a name and no count.
            "cellList-1": '{{"cells": [{}]}}'.format(
                _cell("Новый вишлист", "", "/modal/favoritesCreate/?list_type=wishlist")
            ),
            "cellList-2": '{{"cells": [{}]}}'.format(
                _cell("Дом", "8 подарков", "/my/favorites/list?switchTab=false&list=1349700")
            ),
            "cellList-3": '{{"cells": [{}]}}'.format(_cell("Ремонт", "12 товаров", "/my/favorites/list?list=1350100")),
        }
    }


def test_wishlists_and_collections_are_told_apart_by_the_unit() -> None:
    wishlists = parse_list_page(_page(), wishlists=True)
    assert [(ref.name, ref.items, ref.list_id) for ref in wishlists] == [("Дом", 8, 1349700)]

    collections = parse_list_page(_page(), wishlists=False)
    assert [(ref.name, ref.items, ref.list_id) for ref in collections] == [("Ремонт", 12, 1350100)]


def test_the_create_card_is_not_a_list() -> None:
    names = {ref.name for ref in parse_list_page(_page(), wishlists=True)}
    assert "Новый вишлист" not in names


def test_a_card_without_a_link_still_reads() -> None:
    page = {"widgetStates": {"cellList-1": '{{"cells": [{}]}}'.format(_cell("Дом", "8 подарков", None))}}
    ref = parse_list_page(page, wishlists=True)[0]
    assert (ref.name, ref.items, ref.list_id) == ("Дом", 8, None)
