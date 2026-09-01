"""Runtime configuration (pydantic-settings). Everything tunable is here;
fixed values live in ``constants``.
"""

from functools import cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class OzonSettings(BaseSettings):
    """Session, transport and feature flags, read from ``OZON_*`` env vars."""

    model_config = SettingsConfigDict(env_prefix="OZON_", extra="ignore")

    profile_dir: Path = Path("/data/profile")
    """Persistent Chromium profile holding the session, including OzonID state
    that a storageState snapshot cannot carry (IndexedDB, device trust)."""

    profile_backup: Path = Path("/data/profile.backup")
    """Copy of a known-good profile, restored if the live one gets logged out."""

    state_path: Path = Path("/data/state.json")
    """Legacy storageState, imported once to seed a brand-new profile."""

    impersonate: str = "chrome124"
    """curl_cffi TLS-impersonation profile for direct HTTP requests."""

    enable_writes: bool = False
    """Allow account-mutating tools (cart / favorites / lists)."""

    enable_orders: bool = False
    """Allow place_order. Separate from enable_writes: this one spends money."""

    monitor_store: Path = Path("/data/price_history.json")
    """Where favorites price-monitoring snapshots are persisted."""

    request_timeout: float = 30.0
    """Seconds to wait for one HTTP call to Ozon."""

    request_attempts: int = 3
    """How many times one call is attempted before it is reported as failed."""

    retry_backoff_seconds: float = 1.0
    """Base wait between attempts; doubled per attempt and jittered."""

    retry_cap_seconds: float = 20.0
    """Longest this server waits before a retry, including a Retry-After Ozon
    asked for — an hour-long Retry-After must not hang a tool call."""

    browser_timeout: float = 60.0
    """Seconds to wait for a browser navigation or a login step."""

    idle_seconds: int = 600
    """Close the idle browser after this long; HTTP session stays alive."""

    transport: Literal["stdio", "http", "sse"] = "stdio"
    """How clients reach the server.

    ``stdio`` for a client that spawns the process. ``http`` serves streamable
    HTTP at /mcp, which is what MCP clients use now. ``sse`` serves the older
    event-stream transport at /sse; it still works and the spec has deprecated
    it, so prefer ``http`` for anything new."""

    # Binds inside the container; what is actually reachable is set by the port mapping.
    host: str = "0.0.0.0"
    """Bind address used by the http and sse transports."""

    port: int = 8084
    """Port serving both the MCP endpoint (/mcp or /sse) and /metrics."""

    allowed_hosts: list[str] = []
    """``Host`` headers the HTTP transports accept, empty meaning any.

    MCP can refuse a request whose Host it does not recognise — protection
    against DNS rebinding — and the check is an exact match, so a server reached
    at anything other than a listed name answers 421 "Invalid Host header".
    Left empty the check stays off, which is the useful default here: the
    transport has no authentication of its own, so the boundary is who can reach
    the port, and a server told to bind 0.0.0.0 is meant to be reached from
    elsewhere. List the names in use ("mcp.example:*" matches any port) when the
    port is exposed more widely.
    """


@cache
def get_settings() -> OzonSettings:
    return OzonSettings()
