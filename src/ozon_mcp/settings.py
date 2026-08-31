"""Runtime configuration (pydantic-settings). Everything tunable is here;
fixed values live in ``constants``.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class OzonSettings(BaseSettings):
    """Session, transport and feature flags, read from ``OZON_*`` env vars."""

    model_config = SettingsConfigDict(env_prefix="OZON_", extra="ignore")

    state_path: Path = Path("/data/state.json")
    """Saved Playwright storageState with the authenticated session."""

    impersonate: str = "chrome124"
    """curl_cffi TLS-impersonation profile for direct HTTP requests."""

    enable_writes: bool = False
    """Allow account-mutating tools (cart / favorites / lists)."""

    monitor_store: Path = Path("/data/price_history.json")
    """Where favorites price-monitoring snapshots are persisted."""

    idle_seconds: int = 600
    """Close the idle browser after this long; HTTP session stays alive."""

    transport: Literal["stdio", "sse"] = "stdio"
    """stdio for a local client spawning the process; sse to serve over HTTP."""

    # Binds inside the container; what is actually reachable is set by the port mapping.
    host: str = "0.0.0.0"
    """Bind address used by the sse transport."""

    port: int = 8084
    """Port serving both the MCP endpoint (/sse) and /metrics."""


@cache
def get_settings() -> OzonSettings:
    return OzonSettings()
