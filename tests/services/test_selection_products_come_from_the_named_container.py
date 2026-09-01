"""A selection's products are read from its own container, not from the page.

The page carries a count and no products, and its paginator points at the
recommendations container — following that would report products the selection
does not hold. The container is therefore named, and asked for with the page id
the shell was just built with.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ozon_mcp.services import selections
from support import page

if TYPE_CHECKING:
    from support import FakeSession

UUID = "01a05d2c-845c-7190-b203-a347bb6482e5"
OWNER = "0ad3ae61-5dfb-4064-9d4a-da8fb069b8c6"
START = "db6781cc810273fd423ae763429bdd43"
LIST_PAGE = page(
    cellList={
        "cells": [
            {
                "type": "dsCell",
                "dsCell": {
                    "centerBlock": {"title": {"text": "Расходники"}, "subtitle": {"text": "2 товара • 0 сохранений"}},
                    "common": {"action": {"link": f"https://www.ozon.ru/selections/view/{UUID}?uId={OWNER}"}},
                },
            }
        ]
    }
)
SHELL = page(
    paginator={
        "nextPage": (
            f"/selections/view/{UUID}?layout_container=selection_items_recom_container_desktop"
            f"&layout_page_index=2&start_page_id={START}&uId={OWNER}"
        )
    }
)


def _grid(*skus: str) -> dict[str, Any]:
    return page(tileGridDesktop={"items": [{"sku": sku, "tileLocation": f"/product/{sku}/"} for sku in skus]})


def _wired(session: FakeSession, items: dict[str, Any]) -> None:
    """Answers keyed the way the service asks: named container first."""
    session.pages = {
        "layout_container=selection_items_next_container": items,
        "/selections/view": SHELL,
        "/selections/list": LIST_PAGE,
    }


def test_the_products_are_the_ones_in_the_named_container(session: FakeSession) -> None:
    _wired(session, _grid("489647252", "921329480"))
    assert [tile.sku for tile in selections.selection_products(UUID)] == ["489647252", "921329480"]
    asked = [url for url in session.fetched if url.startswith("/selections/view") and "layout_container" in url]
    assert asked, "the container was never asked for"
    assert all("selection_items_next_container" in url for url in asked)
    assert all(f"start_page_id={START}" in url for url in asked)


def test_adding_keeps_what_is_already_in_the_selection(session: FakeSession, writes_on: None) -> None:
    _wired(session, _grid("489647252", "921329480"))
    session.actions = {"submitSelectionFormWeb": {"selectionUuid": UUID}}
    selections.add_to_selection(UUID, ["998239133"])
    _, body = session.performed[0]
    assert body["placement"] == "update_items"
    assert body["productIds"] == ["489647252", "921329480", "998239133"]


def test_removing_sends_what_should_remain(session: FakeSession, writes_on: None) -> None:
    _wired(session, _grid("489647252", "921329480"))
    session.actions = {"submitSelectionFormWeb": {"selectionUuid": UUID}}
    selections.remove_from_selection(UUID, ["489647252"])
    _, body = session.performed[0]
    assert body["productIds"] == ["921329480"]
