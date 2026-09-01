"""The favorites price watch compares against the previous call, not a schedule.

The comparison is only as old as the last snapshot, so the first call has
nothing to say and every later one speaks against what it was handed before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ozon_mcp.services import monitoring
from ozon_mcp.settings import get_settings

if TYPE_CHECKING:
    from pathlib import Path

TITLES = {"1": "Первый", "2": "Второй"}


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "price_history.json"
    monkeypatch.setattr(get_settings(), "monitor_store", path)
    return path


def test_the_first_run_has_nothing_to_compare_with(store: Path) -> None:
    first = monitoring.record({"1": 100}, TITLES)
    assert first.drops == []
    assert first.rises == []
    assert store.exists()


def test_a_drop_and_a_rise_are_told_apart(store: Path) -> None:
    monitoring.record({"1": 100, "2": 100}, TITLES)
    changed = monitoring.record({"1": 80, "2": 150}, TITLES)
    assert [(change.sku, change.was, change.now, change.delta) for change in changed.drops] == [("1", 100, 80, -20)]
    assert [(change.sku, change.was, change.now, change.delta) for change in changed.rises] == [("2", 100, 150, 50)]
    # The title travels with the snapshot, so a diff can be read without a lookup.
    assert changed.drops[0].title == "Первый"


def test_an_unchanged_price_is_not_a_change(store: Path) -> None:
    monitoring.record({"1": 100}, TITLES)
    same = monitoring.record({"1": 100}, TITLES)
    assert same.drops == []
    assert same.rises == []


def test_a_price_that_vanished_is_not_a_drop_to_zero(store: Path) -> None:
    monitoring.record({"1": 100}, TITLES)
    gone = monitoring.record({}, TITLES)
    assert gone.drops == []
    assert gone.rises == []
