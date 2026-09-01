"""The points amount hides in the link or in the label, never the same way."""

from __future__ import annotations

from ozon_mcp.parsing.checkout import parse_points


def _widget(link: str | None, label: str) -> dict[str, object]:
    tab: dict[str, object] = {"title": {"text": label}}
    if link:
        tab["common"] = {"action": {"link": link}}
    return {"tabs": {"tabs": [{"title": {"text": "Не списывать"}}, tab], "selectedTabIndex": 0}}


def test_amount_from_the_link() -> None:
    options = parse_points(_widget("/gocheckout?points_applied=100.00&set_payment=0", "Списать 100"))
    assert [o.amount for o in options] == [None, 100]


def test_amount_from_the_label_when_no_link() -> None:
    options = parse_points(_widget(None, "Списать 250"))
    assert options[1].amount == 250


def test_no_tabs_no_options() -> None:
    assert parse_points({}) == []
