"""A selection's cell carries both ids, its size and Ozon's status wording.

The link is the only place the owner id appears, and reading a selection without
it answers "она удалена" — so a cell without that link is not a selection.
"""

from __future__ import annotations

from ozon_mcp.parsing.selections import parse_selections

UUID = "01a05d2c-845c-7190-b203-a347bb6482e5"
OWNER = "0ad3ae61-5dfb-4064-9d4a-da8fb069b8c6"


def _cell(title: str, subtitle: str | None, link: str) -> str:
    center = f'"title": {{"text": "{title}"}}'
    if subtitle is not None:
        center += f', "subtitle": {{"text": "{subtitle}"}}'
    return (
        f'{{"type": "dsCell", "dsCell": {{"centerBlock": {{{center}}},'
        ' "leftBlock": {"icon": {"backgroundImage": "https://ir.ozone.ru/cover.jpg"}},'
        f' "common": {{"action": {{"link": "{link}"}}}}}}}}'
    )


def _page() -> dict[str, object]:
    return {
        "widgetStates": {
            "cellList-1": '{{"cells": [{}, {}, {}]}}'.format(
                # The create cell has an action that is not a selection link.
                _cell("Создать подборку", None, "selectionFormRedirect"),
                _cell(
                    "Расходники", "3 товара • 0 сохранений", f"https://www.ozon.ru/selections/view/{UUID}?uId={OWNER}"
                ),
                _cell(
                    "Личное",
                    "Нет товаров • Личная подборка",
                    f"https://www.ozon.ru/selections/view/{UUID[:-1]}f?uId={OWNER}",
                ),
            )
        }
    }


def test_both_ids_come_from_the_link() -> None:
    first = parse_selections(_page())[0]
    assert first.uuid == UUID
    assert first.owner_id == OWNER
    assert first.name == "Расходники"
    assert first.cover == "https://ir.ozone.ru/cover.jpg"


def test_size_and_status_are_split_out_of_one_line() -> None:
    selections = parse_selections(_page())
    assert [(s.items, s.status) for s in selections] == [(3, "0 сохранений"), (0, "Личная подборка")]


def test_the_create_cell_is_not_a_selection() -> None:
    assert "Создать подборку" not in {s.name for s in parse_selections(_page())}


def test_a_page_without_the_container_is_empty_not_an_error() -> None:
    assert parse_selections({}) == []
