"""With several destinations, retargeting must name the shipment.

Verified by construction rather than live: the account's current order groups
both shipments under one address, so the ambiguous case cannot be reproduced
against Ozon on demand.
"""

from __future__ import annotations

import pytest

from ozon_mcp.errors import OzonError
from ozon_mcp.models.checkout import Checkout, Delivery
from ozon_mcp.services.checkout import _target_delivery


def _checkout(*deliveries: Delivery) -> Checkout:
    return Checkout(available=True, deliveries=list(deliveries))


def test_target_delivery_requires_split_key() -> None:
    first = Delivery(address="Выборг", split_keys=["FBS-1-S1"])
    second = Delivery(address="Москва", split_keys=["FBS-2-S2"])

    # One destination: unambiguous, no split_key needed.
    assert _target_delivery(_checkout(first), None) is first

    # Several: refuse rather than move the wrong parcel.
    with pytest.raises(OzonError, match="several destinations"):
        _target_delivery(_checkout(first, second), None)

    assert _target_delivery(_checkout(first, second), "FBS-2-S2") is second

    with pytest.raises(OzonError, match="no shipment"):
        _target_delivery(_checkout(first, second), "FBS-9-S9")

    with pytest.raises(OzonError, match="no destination"):
        _target_delivery(_checkout(), None)
