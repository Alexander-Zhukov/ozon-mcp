"""Console entrypoint: ``python -m ozon_mcp``.

Three transports: stdio for a client that spawns the process itself, and two
long-lived HTTP ones for a remote agent — streamable HTTP at /mcp, which is what
clients use now, and the deprecated event stream at /sse. Either way the same
port serves ``/metrics``, so one published port covers both the protocol and
scraping.
"""

import logging

import uvicorn
from starlette.routing import Route

from ozon_mcp.main import mcp
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

    # /mcp is streamable HTTP, what clients use now; /sse is the older transport
    # the spec has deprecated, kept for clients that still speak only that.
    streaming = settings.transport == "http"
    app = mcp.streamable_http_app() if streaming else mcp.sse_app()
    app.routes.append(Route(METRICS_PATH, metrics_endpoint))
    logger.info(
        "serving mcp on http://%s:%s%s (metrics at %s)",
        settings.host,
        settings.port,
        "/mcp" if streaming else "/sse",
        METRICS_PATH,
    )
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
