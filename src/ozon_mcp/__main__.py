"""Console entrypoint: ``python -m ozon_mcp``.

Two transports: stdio for a client that spawns the process itself, and sse for
a long-lived HTTP service (that is how remote agents attach). Under sse the
same port also serves ``/metrics``, so one published port covers both the
protocol and scraping.
"""

from __future__ import annotations

import logging

import uvicorn
from starlette.routing import Route

from ozon_mcp.server import mcp
from ozon_mcp.settings import get_settings
from ozon_mcp.utils.observability import METRICS_PATH, metrics_endpoint

logger = logging.getLogger("ozon_mcp")


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    for noisy in ("httpx", "httpcore", "curl_cffi"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main() -> None:
    _configure_logging()
    settings = get_settings()
    if settings.transport == "stdio":
        mcp.run()
        return

    app = mcp.sse_app()
    app.routes.append(Route(METRICS_PATH, metrics_endpoint))
    logger.info("serving mcp on http://%s:%s/sse (metrics at %s)", settings.host, settings.port, METRICS_PATH)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
