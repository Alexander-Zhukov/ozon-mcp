"""Prometheus instrumentation, self-contained.

Signals are taken at the transport seam rather than per tool: what actually
breaks in production is the Ozon side (antibot re-challenge, token expiry,
upstream 4xx/5xx), and that all funnels through one request path. Process-level
metrics come from prometheus_client's default collectors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response

if TYPE_CHECKING:
    from starlette.requests import Request

METRICS_PATH: Final = "/metrics"

UPSTREAM_REQUESTS: Final = Counter(
    "ozon_mcp_upstream_requests_total",
    "Requests to Ozon, by backend and outcome.",
    ["backend", "outcome"],
)

UPSTREAM_LATENCY: Final = Histogram(
    "ozon_mcp_upstream_request_seconds",
    "Latency of requests to Ozon.",
    ["backend"],
)

SESSION_BOOTSTRAPS: Final = Counter(
    "ozon_mcp_session_bootstraps_total",
    "Browser bootstraps performed to clear the antibot and harvest a session.",
    ["reason"],
)

BROWSER_ACTIVE: Final = Gauge(
    "ozon_mcp_browser_active",
    "1 while a Chromium instance is held open, 0 when only HTTP is live.",
)


def metrics_endpoint(_request: Request) -> Response:
    """Scrape endpoint; sync so Starlette runs the blocking encode off the loop."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
