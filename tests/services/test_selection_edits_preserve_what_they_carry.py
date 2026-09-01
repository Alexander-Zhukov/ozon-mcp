"""One action creates, renames and fills a selection, told apart by a placement.

Passing the create placement with a uuid does not fail — it makes a second
selection — and an edit carries the visibility, so getting either wrong changes
something nobody asked to change.
"""

from __future__ import annotations

import pytest

from ozon_mcp.errors import OzonError
from ozon_mcp.services import selections
from support import FakeSession, page

UUID = "01a05d2c-845c-7190-b203-a347bb6482e5"
OWNER = "0ad3ae61-5dfb-4064-9d4a-da8fb069b8c6"
LIST_PAGE = page(
    cellList={
        "cells": [
            {
                "type": "dsCell",
                "dsCell": {
                    "centerBlock": {"title": {"text": "Расходники"}, "subtitle": {"text": "3 товара • 0 сохранений"}},
                    "common": {"action": {"link": f"https://www.ozon.ru/selections/view/{UUID}?uId={OWNER}"}},
                },
            }
        ]
    }
)


def _form(*, public: bool, description: str = "старое описание") -> dict[str, object]:
    return page(
        webSelectionItemForm={
            "form": {
                "titleArea": {"text": "Расходники", "maxLength": 60},
                "descriptionArea": {"text": description},
                "anonymousCell": {"rightBlock": {"control": {"toggle": {"isSelected": public}}}},
            }
        }
    )


def test_visibility_comes_from_the_selection_not_from_its_status(session: FakeSession) -> None:
    session.pages = {"/selections/form": _form(public=True), "/selections/list": LIST_PAGE}
    read = selections.get_selection(UUID)
    assert read.public is True
    assert read.description == "старое описание"
    # The listed status says nothing about visibility while a review is pending.
    assert read.status == "0 сохранений"


def test_a_rename_keeps_the_description_and_the_visibility(session: FakeSession, writes_on: None) -> None:
    session.pages = {"/selections/form": _form(public=True), "/selections/list": LIST_PAGE}
    session.actions = {"submitSelectionFormWeb": {"selectionUuid": UUID}}
    selections.edit_selection(UUID, "Новое имя")
    _, body = session.performed[0]
    assert body["placement"] == "update_fields"
    assert body["content"] == {"title": "Новое имя", "description": "старое описание", "isPublic": "true"}


def test_publishing_an_already_public_selection_does_nothing(session: FakeSession, writes_on: None) -> None:
    session.pages = {"/selections/form": _form(public=True), "/selections/list": LIST_PAGE}
    selections.set_selection_public(UUID, public=True)
    assert session.performed == []


def test_publishing_a_private_one_presses_the_toggle_once(session: FakeSession, writes_on: None) -> None:
    session.pages = {"/selections/form": _form(public=False), "/selections/list": LIST_PAGE}
    session.actions = {"setSelectionPublicStatus": {}}
    selections.set_selection_public(UUID, public=True)
    assert [name for name, _ in session.performed] == ["setSelectionPublicStatus"]


def test_setting_the_items_replaces_the_whole_list(session: FakeSession, writes_on: None) -> None:
    session.pages = {"/selections/form": _form(public=False), "/selections/list": LIST_PAGE}
    session.actions = {"submitSelectionFormWeb": {"selectionUuid": UUID}}
    selections.set_selection_items(UUID, ["1", "2"])
    _, body = session.performed[0]
    assert body["placement"] == "update_items"
    assert body["productIds"] == ["1", "2"]


def test_a_refused_creation_raises_rather_than_returning_a_ghost(session: FakeSession, writes_on: None) -> None:
    session.actions = {"submitSelectionFormWeb": {"error": "Пустое название вишлиста"}}
    with pytest.raises(OzonError) as raised:
        selections.create_selection("", "3077454533")
    assert "Пустое название вишлиста" in str(raised.value)
