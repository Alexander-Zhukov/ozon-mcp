"""The returns list continues by index, because its container offers no cursor.

Going by the cursor stopped at the first three of thirty-six.
"""

from __future__ import annotations

from ozon_mcp.services import orders
from support import FakeSession, page


def _returns(*numbers: str) -> dict[str, object]:
    return page(
        returnList={
            "items": [
                {
                    "header": {"newTitle": {"text": "Заявка от 15 июня"}},
                    "status": {"badge": {"text": "Деньги отправлены"}},
                    "total": {"amountDetailing": [{"textRight": "100 ₽"}], "itemPhotos": []},
                    "common": {"action": {"link": f"/my/returnDetails?returnNumber={number}"}},
                }
                for number in numbers
            ]
        }
    )


def test_the_walk_goes_on_while_pages_have_returns(session: FakeSession) -> None:
    session.pages = {
        "layout_page_index=2": _returns("R37", "R36"),
        "layout_page_index=3": _returns("R35"),
        "layout_page_index=4": page(),
    }
    found = orders.list_returns()
    assert [entry.number for entry in found] == ["R37", "R36", "R35"]


def test_the_limit_stops_the_walk_early(session: FakeSession) -> None:
    session.pages = {"layout_page_index=2": _returns("R37", "R36"), "layout_page_index=3": _returns("R35")}
    assert len(orders.list_returns(limit=2)) == 2
    assert not any("layout_page_index=3" in path for path in session.fetched)


def test_no_returns_reads_as_none(session: FakeSession) -> None:
    session.pages = {"/my/returns": page()}
    assert orders.list_returns() == []
