"""Console entrypoint: ``python -m ozon_mcp`` (runs the MCP over stdio)."""

from __future__ import annotations

import logging

from ozon_mcp.server import mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    for noisy in ("httpx", "httpcore", "curl_cffi"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    mcp.run()


if __name__ == "__main__":
    main()
