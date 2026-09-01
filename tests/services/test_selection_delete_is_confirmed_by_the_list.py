"""A refused deletion must not read as a successful one.

Ozon answers a refusal with HTTP 200, the error fields empty and the reason in a
notification bar, so the outcome is decided by re-reading the list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ozon_mcp.errors import OzonError
from ozon_mcp.services import selections
from support import page

if TYPE_CHECKING:
    from support import FakeSession

UUID = "01a05d2c-845c-7190-b203-a347bb6482e5"
OWNER = "0ad3ae61-5dfb-4064-9d4a-da8fb069b8c6"
STILL_THERE = page(
    cellList={
        "cells": [
            {
                "type": "dsCell",
                "dsCell": {
                    "centerBlock": {"title": {"text": "Расходники"}, "subtitle": {"text": "2 товара"}},
                    "common": {"action": {"link": f"https://www.ozon.ru/selections/view/{UUID}?uId={OWNER}"}},
                },
            }
        ]
    }
)
EMPTY = page(cellList={"cells": []})


def test_a_refusal_is_reported_as_a_failure(session: FakeSession, writes_on: None) -> None:
    session.pages = {"/selections/list": STILL_THERE}
    session.actions = {"deleteSelection": {"notificationBar": {"title": "Не смогли удалить подборку"}}}
    result = selections.delete_selection(UUID)
    assert result.ok is False
    assert result.detail == "Не смогли удалить подборку"


def test_a_deletion_is_confirmed_by_the_selection_being_gone(session: FakeSession, writes_on: None) -> None:
    answers = [STILL_THERE, EMPTY]
    session.pages = {"/selections/list": lambda: answers.pop(0) if answers else EMPTY}
    session.actions = {"deleteSelection": {"notificationBar": {"title": "Подборка удалена"}}}
    result = selections.delete_selection(UUID)
    assert result.ok is True
    assert result.detail == "Подборка удалена"


def test_a_uuid_that_was_never_there_is_not_a_deletion(session: FakeSession, writes_on: None) -> None:
    """Absence from the list proves nothing when it was never there."""
    session.pages = {"/selections/list": EMPTY}
    session.actions = {"deleteSelection": {"notificationBar": {"title": "Не смогли удалить подборку"}}}
    with pytest.raises(OzonError, match="no selection"):
        selections.delete_selection(UUID)
    assert session.performed == []
