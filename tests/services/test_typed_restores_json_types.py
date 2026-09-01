"""Ozon flattens its own params to text; the cancel step needs them back."""

from __future__ import annotations

from ozon_mcp.services.orders import _typed


def test_typed_restores_json_types() -> None:
    typed = _typed({
        "Paid": "False",
        "IsLegal": "True",
        "PaymentTypeId": "1634",
        "OrderNumber": "44563249-0865",
        "PostingIds": "[48284296961]",
    })
    assert typed["Paid"] is False
    assert typed["IsLegal"] is True
    assert typed["PaymentTypeId"] == 1634
    # Not everything numeric-looking is a number: ids and lists stay text.
    assert typed["OrderNumber"] == "44563249-0865"
    assert typed["PostingIds"] == "[48284296961]"
