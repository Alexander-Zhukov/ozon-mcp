"""Fixtures shared by the suite.

Each service module holds its own reference to ``get_session``, so the fixture
rebinds it there; patching the definition alone would leave every already
imported name pointing at the real thing.
"""

from __future__ import annotations

import pytest

from ozon_mcp.services import (
    cart,
    catalog,
    checkout,
    favorites,
    finance,
    monitoring,
    orders,
    selections,
    session as session_service,
)
from ozon_mcp.settings import get_settings
from support import FakeSession

_SERVICE_MODULES = (cart, catalog, checkout, favorites, finance, monitoring, orders, selections, session_service)


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> FakeSession:
    fake = FakeSession()
    for module in _SERVICE_MODULES:
        if hasattr(module, "get_session"):
            monkeypatch.setattr(module, "get_session", lambda: fake)
    return fake


@pytest.fixture
def writes_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Open the mutation gates for a test that exercises a write."""
    settings = get_settings()
    monkeypatch.setattr(settings, "enable_writes", True)
    monkeypatch.setattr(settings, "enable_orders", True)
