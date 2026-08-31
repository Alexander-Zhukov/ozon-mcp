"""An unticked cart must read as unavailable, with the fix named."""

from __future__ import annotations

import json

from ozon_mcp.parsing.checkout import parse_checkout


def test_parse_checkout_reports_empty_selection() -> None:
    # Ozon still renders the checkout shell when nothing is selected.
    data = {"widgetStates": {"total-1-checkout-2": json.dumps({"summary": {}})}}
    checkout = parse_checkout(data)
    assert checkout.available is False
    assert checkout.reason is not None
    assert "selected" in checkout.reason


def test_parse_checkout_reports_missing_page() -> None:
    assert parse_checkout({"widgetStates": {}}).available is False
