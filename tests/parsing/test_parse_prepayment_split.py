"""Ozon names the prepaid items itself, behind the «Есть предоплата» row."""

from __future__ import annotations

from ozon_mcp.parsing.checkout import parse_prepayment_split, prepayment_link


def _section(title: str, *lines: tuple[str, str]) -> str:
    items = ", ".join(
        f'{{"mainColumn": [{{"textAtom": {{"text": "{name}"}}}}], "price": {{"price": "{price}"}}}}'
        for name, price in lines
    )
    return f'{{"title": {{"text": "{title}"}}, "vertical": {{"splits": [{{"items": [{items}]}}]}}}}'


def _modal(now_title: str = "К оплате сейчас", later_title: str = "К оплате после получения") -> dict[str, object]:
    return {
        "widgetStates": {
            "splitDetailWebV2-1": _section(later_title, ("Таблетница", "121 ₽"), ("Салфетки", "656 ₽")),
            "splitDetailWebV2-2": _section(now_title, ("Брюки бойфренды", "2 152 ₽")),
            "buttonWidget-3": '{"webButton": {"text": "Понятно"}}',
        }
    }


def test_the_two_groups_are_told_apart_by_title() -> None:
    now, later = parse_prepayment_split(_modal())
    assert [item.title for item in now] == ["Брюки бойфренды"]
    assert [item.title for item in later] == ["Таблетница", "Салфетки"]
    assert [item.price for item in later] == ["121 ₽", "656 ₽"]


def test_a_reworded_section_is_taken_by_elimination() -> None:
    # Two sections, one still recognisable: the other one is the remainder.
    now, later = parse_prepayment_split(_modal(now_title="Списываем сразу"))
    assert [item.title for item in later] == ["Таблетница", "Салфетки"]
    assert [item.title for item in now] == ["Брюки бойфренды"]


def test_the_row_is_a_control_not_a_caption() -> None:
    # Ozon hangs the action on the chevron in rightBlock, not on the row itself.
    payment = {
        "items": [
            {
                "centerBlock": {"title": {"text": "Есть предоплата 2 152 ₽"}},
                "rightBlock": {
                    "common": {
                        "action": {"behavior": "BEHAVIOR_TYPE_COMPOSER_NESTED_PAGE", "link": "/modal/prepayment"}
                    },
                    "icon": {"icon": {"icon": "ic_m_chevron_right_filled"}},
                },
            }
        ]
    }
    assert prepayment_link(payment) == "/modal/prepayment"
    assert prepayment_link({"items": [{"centerBlock": {"title": {"text": "Способ оплаты"}}}]}) is None
