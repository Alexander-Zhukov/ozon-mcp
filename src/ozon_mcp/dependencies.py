"""Dependency-injection factories (no bare module-level singletons)."""

from __future__ import annotations

from functools import cache

from ozon_mcp.session.transport import OzonSession


@cache
def get_session() -> OzonSession:
    """The process-wide OZON session; disposed via ``get_session.cache_clear()``."""
    return OzonSession()
